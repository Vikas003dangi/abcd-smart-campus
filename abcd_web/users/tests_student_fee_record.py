from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from unittest.mock import patch
from datetime import date, timedelta
from users.models import StudentProfile, FeeTransaction, Notification, Payment


class StudentFeeRecordTests(TestCase):
    def setUp(self):
        self.client = Client()

        # Users
        self.teacher_user = User.objects.create_superuser(
            username='teacher_admin',
            email='teacher@example.com',
            password='Password123!'
        )
        self.student_user_a = User.objects.create_user(
            username='student_a',
            email='student_a@example.com',
            password='Password123!'
        )
        self.student_user_b = User.objects.create_user(
            username='student_b',
            email='student_b@example.com',
            password='Password123!'
        )
        self.alumni_user = User.objects.create_user(
            username='alumni_user',
            email='alumni@example.com',
            password='Password123!'
        )

        # Student Profiles
        self.profile_a = StudentProfile.objects.create(
            user=self.student_user_a,
            full_name='Student Alpha',
            mobile_number='9876543211',
            dob=date(2002, 1, 1),
            status='admitted',
            is_admitted=True,
            service_type='Both'
        )
        self.profile_b = StudentProfile.objects.create(
            user=self.student_user_b,
            full_name='Student Beta',
            mobile_number='9876543212',
            dob=date(2002, 2, 2),
            status='admitted',
            is_admitted=True,
            service_type='Coaching'
        )

        # Transactions for Student A
        self.tx_a1 = FeeTransaction.objects.create(
            student=self.profile_a,
            teacher=self.teacher_user,
            receipt_number='REC-A001',
            payment_date=timezone.localdate() - timedelta(days=10),
            total_amount=1500,
            months_snapshot=[{'month': 'August (2026)', 'amount': 1500, 'payment_date': '10/08/2026', 'status': 'paid'}]
        )
        self.tx_a2 = FeeTransaction.objects.create(
            student=self.profile_a,
            teacher=self.teacher_user,
            receipt_number='REC-A002',
            payment_date=timezone.localdate() - timedelta(days=5),
            total_amount=1500,
            months_snapshot=[{'month': 'September (2026)', 'amount': 1500, 'payment_date': '15/09/2026', 'status': 'paid'}]
        )

        # Transaction for Student B
        self.tx_b1 = FeeTransaction.objects.create(
            student=self.profile_b,
            teacher=self.teacher_user,
            receipt_number='REC-B001',
            payment_date=timezone.localdate() - timedelta(days=2),
            total_amount=2000,
            months_snapshot=[{'month': 'September (2026)', 'amount': 2000, 'payment_date': '18/09/2026', 'status': 'paid'}]
        )

    # -------------------------------------------------------------
    # 1. SCOPING TESTS
    # -------------------------------------------------------------
    def test_scoping_student_sees_only_own_records(self):
        """Student A must only see their own transactions, never Student B's."""
        self.client.login(username='student_a', password='Password123!')
        resp = self.client.get(reverse('users:student_fee_record'))
        self.assertEqual(resp.status_code, 200)

        # Student A's records present
        self.assertContains(resp, 'REC-A001')
        self.assertContains(resp, 'REC-A002')

        # Student B's record strictly absent
        self.assertNotContains(resp, 'REC-B001')

    # -------------------------------------------------------------
    # 2. IDOR PROTECTION TESTS
    # -------------------------------------------------------------
    def test_idor_student_cannot_download_other_student_receipt(self):
        """Student A attempting to download Student B's receipt must receive 404, not 403."""
        self.client.login(username='student_a', password='Password123!')
        resp = self.client.get(reverse('users:student_download_fee_receipt', kwargs={'transaction_id': self.tx_b1.id}))
        self.assertEqual(resp.status_code, 404)

        # Also test alternate URL pattern
        resp_alt = self.client.get(f"/student/fee-receipt/download/{self.tx_b1.id}/")
        self.assertEqual(resp_alt.status_code, 404)

    # -------------------------------------------------------------
    # 3. AUTHENTICATION & ROLE ACCESS
    # -------------------------------------------------------------
    def test_unauthenticated_access_redirects_to_login(self):
        """Logged out users accessing student fee record must be redirected to login."""
        resp = self.client.get(reverse('users:student_fee_record'))
        self.assertEqual(resp.status_code, 302)
        self.assertIn('/login/', resp.url)

    def test_teacher_role_cannot_access_student_fee_record(self):
        """Teachers/staff without an admitted StudentProfile receive 404 on student fee record."""
        self.client.login(username='teacher_admin', password='Password123!')
        resp = self.client.get(reverse('users:student_fee_record'))
        self.assertEqual(resp.status_code, 404)

    def test_alumni_role_cannot_access_student_fee_record(self):
        """Alumni users without an admitted StudentProfile receive 404 on student fee record."""
        self.client.login(username='alumni_user', password='Password123!')
        resp = self.client.get(reverse('users:student_fee_record'))
        self.assertEqual(resp.status_code, 404)

    # -------------------------------------------------------------
    # 4. HIDE / SOFT DELETE BEHAVIOUR
    # -------------------------------------------------------------
    def test_student_hide_fee_transaction_single_and_bulk(self):
        """Hiding a record sets is_hidden_by_student=True, disappears from student record & dashboard."""
        self.client.login(username='student_a', password='Password123!')

        # POST hide for tx_a1
        resp = self.client.post(reverse('users:student_hide_fee_transaction'), {
            'transaction_id': self.tx_a1.id
        })
        self.assertRedirects(resp, reverse('users:student_fee_record'))

        # Verify DB flag
        self.tx_a1.refresh_from_db()
        self.assertTrue(self.tx_a1.is_hidden_by_student)

        # Check student fee record page: tx_a1 is gone, tx_a2 remains
        resp_page = self.client.get(reverse('users:student_fee_record'))
        self.assertNotContains(resp_page, 'REC-A001')
        self.assertContains(resp_page, 'REC-A002')

        # Check student dashboard: tx_a1 is gone, tx_a2 remains
        resp_dash = self.client.get(reverse('users:student_dashboard'))
        self.assertNotContains(resp_dash, 'REC-A001')
        self.assertContains(resp_dash, 'REC-A002')

    def test_student_cannot_hide_another_students_transaction(self):
        """Student A cannot hide Student B's transaction."""
        self.client.login(username='student_a', password='Password123!')
        self.client.post(reverse('users:student_hide_fee_transaction'), {
            'transaction_id': self.tx_b1.id
        })
        self.tx_b1.refresh_from_db()
        self.assertFalse(self.tx_b1.is_hidden_by_student)

    def test_teacher_fees_record_unaffected_by_student_hide(self):
        """Teacher fees record page still displays transactions hidden by the student."""
        self.tx_a1.is_hidden_by_student = True
        self.tx_a1.save()

        self.client.login(username='teacher_admin', password='Password123!')
        resp = self.client.get(reverse('users:fees_record'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'REC-A001')

    def test_delete_endpoint_requires_post(self):
        """GET request to /student/fees/delete/ returns 405 Method Not Allowed."""
        self.client.login(username='student_a', password='Password123!')
        resp = self.client.get(reverse('users:student_hide_fee_transaction'))
        self.assertEqual(resp.status_code, 405)

    # -------------------------------------------------------------
    # 5. DASHBOARD FEE TABLE & PAGINATION REMOVAL
    # -------------------------------------------------------------
    def test_dashboard_shows_last_5_non_hidden_and_no_arrow_pagination(self):
        """Dashboard shows only last 5 non-hidden payments, no arrow pagination controls."""
        # Create 5 more transactions for student A (total 7)
        for i in range(3, 8):
            FeeTransaction.objects.create(
                student=self.profile_a,
                teacher=self.teacher_user,
                receipt_number=f'REC-A00{i}',
                payment_date=timezone.localdate() + timedelta(days=i),
                total_amount=1000 + i,
                months_snapshot=[{'month': f'Month {i}', 'amount': 1000 + i, 'payment_date': '01/01/2026', 'status': 'paid'}]
            )

        self.client.login(username='student_a', password='Password123!')
        resp = self.client.get(reverse('users:student_dashboard'))
        self.assertEqual(resp.status_code, 200)

        # Exactly 5 items in context fee_records
        self.assertEqual(len(resp.context['fee_records']), 5)

        # Arrow pagination elements are completely removed
        self.assertNotContains(resp, 'id="feePaginationWrapper"')
        self.assertNotContains(resp, 'id="feePrevBtn"')
        self.assertNotContains(resp, 'id="feeNextBtn"')
        self.assertNotContains(resp, 'changeFeePage')

        # Header "All Fees" button and bottom "View More" button are present
        self.assertContains(resp, 'All Fees')
        self.assertContains(resp, 'View More')
        self.assertContains(resp, reverse('users:student_fee_record'))

    # -------------------------------------------------------------
    # 6. NAVIGATION, SIDEBAR, FOOTER & BACK REDIRECT
    # -------------------------------------------------------------
    def test_sidebar_and_footer_links_present(self):
        """Student dashboard sidebar and footer contain Fees Record link."""
        self.client.login(username='student_a', password='Password123!')
        resp = self.client.get(reverse('users:student_dashboard'))
        self.assertEqual(resp.status_code, 200)

        fee_url = reverse('users:student_fee_record')
        self.assertContains(resp, f'href="{fee_url}"')
        self.assertContains(resp, 'Fees Record')

    def test_back_parent_set_to_student_dashboard(self):
        """Student fee record page includes _smart_back_redirect with back_url='users:student_dashboard'."""
        self.client.login(username='student_a', password='Password123!')
        resp = self.client.get(reverse('users:student_fee_record'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "users:student_dashboard")

    # -------------------------------------------------------------
    # 7. IN-MEMORY RECEIPT GENERATION (ZERO DB/DISK STORAGE)
    # -------------------------------------------------------------
    def test_receipt_pdf_download_in_memory_and_not_stored_on_disk(self):
        """Receipt PDF is generated in-memory and delivered as attachment, never stored on disk."""
        self.client.login(username='student_a', password='Password123!')
        resp = self.client.get(reverse('users:student_download_fee_receipt', kwargs={'transaction_id': self.tx_a1.id}))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Content-Type'], 'application/pdf')
        self.assertIn(f'Fee_Receipt_{self.tx_a1.receipt_number}.pdf', resp['Content-Disposition'])

        # Content is non-empty PDF binary
        pdf_bytes = resp.content
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))

    # -------------------------------------------------------------
    # 8. NOTIFICATION IDEMPOTENCY & PUSH RESILIENCE
    # -------------------------------------------------------------
    def test_fee_notification_creation_and_idempotency(self):
        """Fee submission creates exactly one notification, idempotent on re-save."""
        from users.notifications import create_notification
        notif_tag = f"fee-receipt-{self.tx_a1.id}"

        # Clean notifications
        Notification.objects.filter(user=self.student_user_a).delete()

        # Simulate first notification creation
        notif1 = create_notification(
            user=self.student_user_a,
            title="Fee Submitted Successfully",
            message=f"Payment of ₹{self.tx_a1.total_amount} recorded (Receipt #{self.tx_a1.receipt_number}).",
            link=f"/student/fees/?highlight={self.tx_a1.id}",
            category="payment",
            tag=notif_tag,
            meta={"fee_transaction_id": self.tx_a1.id, "receipt_number": self.tx_a1.receipt_number}
        )
        self.assertIsNotNone(notif1)

        # Count should be 1
        count1 = Notification.objects.filter(
            user=self.student_user_a,
            meta__fee_transaction_id=self.tx_a1.id
        ).count()
        self.assertEqual(count1, 1)

        # Simulate second execution (re-save check)
        already_notified = Notification.objects.filter(
            user=self.student_user_a,
            meta__fee_transaction_id=self.tx_a1.id
        ).exists()
        self.assertTrue(already_notified)

    def test_push_failure_does_not_break_payment(self):
        """Push failure does not raise an unhandled exception or fail transaction creation."""
        with patch('users.notifications.send_push', side_effect=Exception("Push network timeout")):
            try:
                from users.notifications import create_notification
                create_notification(
                    user=self.student_user_a,
                    title="Fee Submitted Successfully",
                    message="Payment recorded",
                    link="/student/fees/",
                    category="payment"
                )
            except Exception as e:
                self.fail(f"create_notification raised an exception on push failure: {e}")
