from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import date, timedelta
from decimal import Decimal
import json

from unittest.mock import patch

from users.models import (
    StudentProfile,
    FeeTransaction,
    TeacherHiddenFeeTransaction,
    FeeTransactionAudit,
    Notification,
    Payment,
)
from users.utils.receipt_generator import generate_fee_receipt_pdf


class FeeLifecyclePhase1Tests(TestCase):
    def setUp(self):
        self.email_patcher = patch('users.email_service.send_html_email', return_value=True)
        self.email_patcher.start()
        self.addCleanup(self.email_patcher.stop)

        self.client = Client()

        # Teachers
        self.teacher_1 = User.objects.create_superuser(
            username='teacher_one',
            email='teacher1@example.com',
            password='Password123!'
        )
        self.teacher_2 = User.objects.create_superuser(
            username='teacher_two',
            email='teacher2@example.com',
            password='Password123!'
        )

        # Students
        self.student_user_1 = User.objects.create_user(
            username='student_one',
            email='student1@example.com',
            password='Password123!'
        )
        self.student_user_2 = User.objects.create_user(
            username='student_two',
            email='student2@example.com',
            password='Password123!'
        )

        self.profile_1 = StudentProfile.objects.create(
            user=self.student_user_1,
            full_name='Rohan Sharma',
            mobile_number='9876543210',
            dob=date(2002, 5, 10),
            status='admitted',
            is_admitted=True,
            service_type='Coaching'
        )

        self.profile_2 = StudentProfile.objects.create(
            user=self.student_user_2,
            full_name='Aarav Patel',
            mobile_number='9876543211',
            dob=date(2002, 8, 15),
            status='admitted',
            is_admitted=True,
            service_type='Library'
        )

        # Fee Transactions
        self.tx_1 = FeeTransaction.objects.create(
            student=self.profile_1,
            teacher=self.teacher_1,
            receipt_number='REC-001',
            payment_date=timezone.localdate() - timedelta(days=5),
            total_amount=Decimal('1500.00'),
            service_snapshot='Coaching Full Batch',
            months_snapshot=[{'month': 'August (2026)', 'amount': 1500, 'status': 'paid'}],
            student_name_snapshot='Rohan Sharma',
            roll_number_snapshot='CS-101',
            mobile_snapshot='9876543210'
        )

        self.tx_2 = FeeTransaction.objects.create(
            student=self.profile_1,
            teacher=self.teacher_1,
            receipt_number='REC-002',
            payment_date=timezone.localdate() - timedelta(days=2),
            total_amount=Decimal('2000.00'),
            service_snapshot='Coaching Full Batch',
            months_snapshot=[{'month': 'September (2026)', 'amount': 2000, 'status': 'paid'}],
            student_name_snapshot='Rohan Sharma',
            roll_number_snapshot='CS-101',
            mobile_snapshot='9876543210'
        )

        self.tx_3 = FeeTransaction.objects.create(
            student=self.profile_2,
            teacher=self.teacher_2,
            receipt_number='REC-003',
            payment_date=timezone.localdate() - timedelta(days=1),
            total_amount=Decimal('1200.00'),
            service_snapshot='Library Seat',
            months_snapshot=[{'month': 'September (2026)', 'amount': 1200, 'status': 'paid'}],
            student_name_snapshot='Aarav Patel',
            roll_number_snapshot='CS-102',
            mobile_snapshot='9876543211'
        )

    # -----------------------------------------------------------------
    # 1. TEACHER DELETE FOR ME ONLY (HIDE FOR TEACHER ONLY)
    # -----------------------------------------------------------------
    def test_teacher_delete_for_me_only(self):
        """Hiding a receipt for Teacher 1 hides it ONLY for Teacher 1; Teacher 2 still sees it."""
        self.client.login(username='teacher_one', password='Password123!')

        # POST hide_for_me via bulk_delete_fees_action
        resp = self.client.post(reverse('users:bulk_delete_fees'), {
            'action_type': 'hide_for_me',
            'transaction_ids[]': [self.tx_1.id]
        })
        self.assertEqual(resp.status_code, 302)

        # Verified in DB: TeacherHiddenFeeTransaction created for teacher 1
        self.assertTrue(TeacherHiddenFeeTransaction.objects.filter(teacher=self.teacher_1, transaction=self.tx_1).exists())
        self.assertFalse(TeacherHiddenFeeTransaction.objects.filter(teacher=self.teacher_2, transaction=self.tx_1).exists())

        # FeeTransaction row is NOT deleted or soft-deleted
        self.tx_1.refresh_from_db()
        self.assertIsNone(self.tx_1.deleted_at)

        # Teacher 1 fees_record active tab does NOT contain REC-001
        resp_t1 = self.client.get(reverse('users:fees_record'))
        self.assertNotContains(resp_t1, 'REC-001')
        self.assertContains(resp_t1, 'REC-002')

        # Teacher 1 hidden tab DOES contain REC-001
        resp_t1_hidden = self.client.get(reverse('users:fees_record') + '?tab=hidden')
        self.assertContains(resp_t1_hidden, 'REC-001')

        # Teacher 2 fees_record STILL sees REC-001
        self.client.login(username='teacher_two', password='Password123!')
        resp_t2 = self.client.get(reverse('users:fees_record'))
        self.assertContains(resp_t2, 'REC-001')

        # Student view is UNCHANGED: Student 1 still sees REC-001
        self.client.login(username='student_one', password='Password123!')
        resp_s1 = self.client.get(reverse('users:student_fee_record'))
        self.assertContains(resp_s1, 'REC-001')

    def test_teacher_totals_unchanged_by_hide_for_me(self):
        """Accounting totals and live stats remain unaffected when a teacher hides a receipt for themselves."""
        self.client.login(username='teacher_one', password='Password123!')

        # Total before hide
        resp_before = self.client.get(reverse('users:fees_record'))
        total_before = resp_before.context.get('total_amount_collected')

        # Hide tx_1
        self.client.post(reverse('users:bulk_delete_fees'), {
            'action_type': 'hide_for_me',
            'transaction_ids[]': [self.tx_1.id]
        })

        # Total after hide
        resp_after = self.client.get(reverse('users:fees_record'))
        total_after = resp_after.context.get('total_amount_collected')

        self.assertEqual(total_before, total_after)

    def test_teacher_restore_hidden_receipt(self):
        """Teacher can restore a previously hidden receipt back to active view."""
        # Hide for teacher 1
        TeacherHiddenFeeTransaction.objects.create(teacher=self.teacher_1, transaction=self.tx_1)

        self.client.login(username='teacher_one', password='Password123!')
        resp = self.client.post(reverse('users:teacher_restore_fees'), {
            'transaction_ids[]': [self.tx_1.id]
        })
        self.assertRedirects(resp, reverse('users:fees_record') + '?tab=hidden')

        # DB record removed
        self.assertFalse(TeacherHiddenFeeTransaction.objects.filter(teacher=self.teacher_1, transaction=self.tx_1).exists())

        # Now visible again in active tab
        resp_active = self.client.get(reverse('users:fees_record'))
        self.assertContains(resp_active, 'REC-001')

    def test_teacher_cannot_restore_another_teachers_hidden_record(self):
        """Teacher 2 cannot unhide/restore a record that Teacher 1 hid."""
        TeacherHiddenFeeTransaction.objects.create(teacher=self.teacher_1, transaction=self.tx_1)

        self.client.login(username='teacher_two', password='Password123!')
        self.client.post(reverse('users:teacher_restore_fees'), {
            'transaction_ids[]': [self.tx_1.id]
        })

        # Teacher 1's hide row is STILL intact
        self.assertTrue(TeacherHiddenFeeTransaction.objects.filter(teacher=self.teacher_1, transaction=self.tx_1).exists())

    # -----------------------------------------------------------------
    # 2. DELETE FOR EVERYONE (SOFT DELETE & AUDIT)
    # -----------------------------------------------------------------
    def test_delete_for_everyone_soft_deletes_and_audits(self):
        """'Delete for everyone' sets deleted_at, creates FeeTransactionAudit, and cleans notification."""
        # Create an in-app notification linked to tx_1
        notif = Notification.objects.create(
            user=self.student_user_1,
            title="Fee Paid",
            message="Receipt REC-001 generated",
            meta={'fee_transaction_id': self.tx_1.id}
        )

        self.client.login(username='teacher_one', password='Password123!')
        resp = self.client.post(reverse('users:bulk_delete_fees'), {
            'action_type': 'delete_for_everyone',
            'transaction_ids[]': [self.tx_1.id],
            'reason': 'Duplicate entry error'
        })
        self.assertEqual(resp.status_code, 302)

        # 1. Soft-delete check
        self.tx_1.refresh_from_db()
        self.assertIsNotNone(self.tx_1.deleted_at)
        self.assertEqual(self.tx_1.deleted_by, self.teacher_1)

        # 2. Audit row created
        audit = FeeTransactionAudit.objects.filter(transaction_id=self.tx_1.id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.receipt_number, 'REC-001')
        self.assertEqual(audit.action, 'delete_for_everyone')
        self.assertEqual(audit.actor, self.teacher_1)
        self.assertEqual(audit.amount, Decimal('1500.00'))
        self.assertEqual(audit.student_name, 'Rohan Sharma')
        self.assertEqual(audit.roll_number, 'CS-101')
        self.assertEqual(audit.reason, 'Duplicate entry error')

        # 3. Notification cleaned
        self.assertFalse(Notification.objects.filter(id=notif.id).exists())

        # 4. Record disappeared from Teacher view
        resp_teacher = self.client.get(reverse('users:fees_record'))
        self.assertNotContains(resp_teacher, 'REC-001')

        # 5. Record disappeared from Student view & dashboard
        self.client.login(username='student_one', password='Password123!')
        resp_student = self.client.get(reverse('users:student_fee_record'))
        self.assertNotContains(resp_student, 'REC-001')

        resp_dash = self.client.get(reverse('users:student_dashboard'))
        self.assertNotContains(resp_dash, 'REC-001')

        # 6. Cannot be restored from UI
        self.client.login(username='teacher_one', password='Password123!')
        resp_restore = self.client.post(reverse('users:teacher_restore_fees'), {
            'transaction_ids[]': [self.tx_1.id]
        })
        self.tx_1.refresh_from_db()
        self.assertIsNotNone(self.tx_1.deleted_at)

        # 7. Direct receipt download returns 404 for teacher
        resp_dl_teacher = self.client.get(reverse('users:download_fee_receipt', kwargs={'transaction_id': self.tx_1.id}))
        self.assertEqual(resp_dl_teacher.status_code, 404)

        # And returns 404 for student
        self.client.login(username='student_one', password='Password123!')
        resp_dl_student = self.client.get(reverse('users:student_download_fee_receipt', kwargs={'transaction_id': self.tx_1.id}))
        self.assertEqual(resp_dl_student.status_code, 404)

    # -----------------------------------------------------------------
    # 3. STUDENT HIDE AND RESTORE
    # -----------------------------------------------------------------
    def test_student_hide_and_restore(self):
        """Student can hide receipts from their view, see them in Hidden tab, and restore them."""
        self.client.login(username='student_one', password='Password123!')

        # Hide tx_2 via JSON/AJAX
        resp_hide = self.client.post(
            reverse('users:student_hide_fee_transaction'),
            data=json.dumps({'transaction_ids': [self.tx_2.id]}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_hide.status_code, 200)
        self.assertEqual(resp_hide.json()['status'], 'success')

        self.tx_2.refresh_from_db()
        self.assertTrue(self.tx_2.is_hidden_by_student)

        # Active tab does not show REC-002
        resp_active = self.client.get(reverse('users:student_fee_record'))
        self.assertNotContains(resp_active, 'REC-002')

        # Hidden tab shows REC-002
        resp_hidden = self.client.get(reverse('users:student_fee_record') + '?tab=hidden')
        self.assertContains(resp_hidden, 'REC-002')

        # Restore tx_2 via AJAX
        resp_restore = self.client.post(
            reverse('users:student_restore_fee_transaction'),
            data=json.dumps({'transaction_ids': [self.tx_2.id]}),
            content_type='application/json',
            HTTP_X_REQUESTED_WITH='XMLHttpRequest'
        )
        self.assertEqual(resp_restore.status_code, 200)
        self.assertEqual(resp_restore.json()['status'], 'success')

        self.tx_2.refresh_from_db()
        self.assertFalse(self.tx_2.is_hidden_by_student)

        # Active tab shows REC-002 again
        resp_active_again = self.client.get(reverse('users:student_fee_record'))
        self.assertContains(resp_active_again, 'REC-002')

    def test_student_idor_cannot_restore_other_students_receipt(self):
        """Student 1 cannot restore Student 2's receipt."""
        self.tx_3.is_hidden_by_student = True
        self.tx_3.save()

        self.client.login(username='student_one', password='Password123!')
        self.client.post(reverse('users:student_restore_fee_transaction'), {
            'transaction_id': self.tx_3.id
        })

        self.tx_3.refresh_from_db()
        # Remains hidden for student 2
        self.assertTrue(self.tx_3.is_hidden_by_student)

    # -----------------------------------------------------------------
    # 4. PROFILE DELETION PRESERVES FEE HISTORY
    # -----------------------------------------------------------------
    def test_student_profile_deletion_preserves_fee_history_with_snapshots(self):
        """When a student profile is deleted by a teacher, fee records remain and show 'Former student'."""
        self.client.login(username='teacher_one', password='Password123!')

        # Delete student 1 profile via delete_student_view
        resp = self.client.post(reverse('users:delete_student', kwargs={'student_id': self.profile_1.id}), {
            'delete_scope': 'admission'
        })
        self.assertEqual(resp.status_code, 302)

        # StudentProfile is deleted
        self.assertFalse(StudentProfile.objects.filter(pk=self.profile_1.pk).exists())

        # FeeTransaction row STILL exists, student is None, snapshot intact
        self.tx_1.refresh_from_db()
        self.assertIsNone(self.tx_1.student)
        self.assertEqual(self.tx_1.student_name_snapshot, 'Rohan Sharma')
        self.assertEqual(self.tx_1.roll_number_snapshot, 'CS-101')
        self.assertEqual(self.tx_1.student_display_name, 'Former student: Rohan Sharma (Roll CS-101)')

        # Teacher page renders successfully without 500
        resp_fees = self.client.get(reverse('users:fees_record'))
        self.assertEqual(resp_fees.status_code, 200)
        self.assertContains(resp_fees, 'Former student: Rohan Sharma')
        self.assertContains(resp_fees, 'REC-001')

        # PDF receipt still generates cleanly with student=None
        pdf_buffer = generate_fee_receipt_pdf(self.tx_1)
        self.assertTrue(pdf_buffer.getvalue().startswith(b'%PDF'))

    # -----------------------------------------------------------------
    # 5. ORPHAN NOTIFICATIONS CLEANED ON STUDENT DELETION
    # -----------------------------------------------------------------
    def test_student_profile_deletion_cleans_notifications(self):
        """Deleting student profile removes that student's notification records to avoid 404 links."""
        notif = Notification.objects.create(
            user=self.student_user_2,
            title="Fee Reminder",
            message="Please pay fees"
        )

        self.client.login(username='teacher_one', password='Password123!')
        self.client.post(reverse('users:delete_student', kwargs={'student_id': self.profile_2.id}), {
            'delete_scope': 'admission'
        })

        self.assertFalse(Notification.objects.filter(id=notif.id).exists())

    # -----------------------------------------------------------------
    # 6. HTTP METHOD SECURITY & CSRF PROTECTION
    # -----------------------------------------------------------------
    def test_endpoints_reject_get_requests(self):
        """All destructive fee actions require POST and reject GET with 405."""
        self.client.login(username='teacher_one', password='Password123!')

        resp1 = self.client.get(reverse('users:bulk_delete_fees'))
        self.assertEqual(resp1.status_code, 405)

        resp2 = self.client.get(reverse('users:teacher_restore_fees'))
        self.assertEqual(resp2.status_code, 405)

        self.client.login(username='student_one', password='Password123!')

        resp3 = self.client.get(reverse('users:student_hide_fee_transaction'))
        self.assertEqual(resp3.status_code, 405)

        resp4 = self.client.get(reverse('users:student_restore_fee_transaction'))
        self.assertEqual(resp4.status_code, 405)
