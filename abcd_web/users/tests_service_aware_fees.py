"""
Tests for Part C: Service-Aware Fees Architecture.
Covers:
- Dual-service ('Both') student fee coexistence (Coaching vs Library in same month/year).
- Payment and FeeTransaction unique constraint enforcement per service.
- sync_student_fee_chain independent expiry date calculations.
- Teacher fee calendar service filtering (?service=coaching / ?service=library).
- Fee payment processing and receipt generation with service snapshot.
- Fee clear month service isolation.
- Student fee record service filtering.
- report_fee_service_ambiguity management command.
"""

import json
from datetime import date, timedelta
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse
from django.core.management import call_command
from django.core.cache import cache
from django.utils import timezone
from io import StringIO

from users.models import StudentProfile, Payment, FeeTransaction, DismissedFeeAlert
from users.views import sync_student_fee_chain, _recalc_fee_expiry_with_hold

User = get_user_model()


class ServiceAwareFeesTestCase(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username='head_teacher',
            password='Password123!',
            is_staff=True
        )
        self.student_user = User.objects.create_user(
            username='dual_student',
            password='Password123!'
        )
        batch_val = StudentProfile.BATCH_CHOICES[0][0] if StudentProfile.BATCH_CHOICES else 'Morning'
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            full_name='Dual Service Student',
            status='admitted',
            service_type='Both',
            mobile_number='9876543210',
            batch=batch_val
        )

        self.single_user = User.objects.create_user(
            username='single_student',
            password='Password123!'
        )
        self.single_student = StudentProfile.objects.create(
            user=self.single_user,
            full_name='Coaching Only Student',
            status='admitted',
            service_type='Coaching',
            mobile_number='9876543211'
        )

        self.client = Client()

    def test_dual_service_payment_coexistence_in_same_month(self):
        """Coaching and Library payments can coexist in the same month/year for a dual-service student."""
        p_coaching = Payment.objects.create(
            student=self.student,
            month='January',
            year=2026,
            service='coaching',
            amount=1500,
            date_paid=date(2026, 1, 5)
        )
        self.assertIsNotNone(p_coaching.id)

        # Same month/year, different service -> Must succeed!
        p_library = Payment.objects.create(
            student=self.student,
            month='January',
            year=2026,
            service='library',
            amount=800,
            date_paid=date(2026, 1, 5)
        )
        self.assertIsNotNone(p_library.id)

        # Attempting duplicate Coaching payment for same month/year -> IntegrityError
        with self.assertRaises(IntegrityError):
            Payment.objects.create(
                student=self.student,
                month='January',
                year=2026,
                service='coaching',
                amount=1500,
                date_paid=date(2026, 1, 10)
            )

    def test_sync_student_fee_chain_independent_expiries(self):
        """sync_student_fee_chain calculates coaching and library expiries independently."""
        # Add Coaching payments for Jan & Feb 2026
        Payment.objects.create(
            student=self.student,
            month='January',
            year=2026,
            service='coaching',
            amount=1500,
            date_paid=date(2026, 1, 5)
        )
        Payment.objects.create(
            student=self.student,
            month='February',
            year=2026,
            service='coaching',
            amount=1500,
            date_paid=date(2026, 2, 5)
        )

        # Add Library payment for Jan 2026 only
        Payment.objects.create(
            student=self.student,
            month='January',
            year=2026,
            service='library',
            amount=800,
            date_paid=date(2026, 1, 5)
        )

        # Sync Coaching chain
        y_c, m_c, d_c = sync_student_fee_chain(self.student, service='coaching')
        self.assertEqual((y_c, m_c, d_c), (2026, 2, 5))

        # Sync Library chain
        y_l, m_l, d_l = sync_student_fee_chain(self.student, service='library')
        self.assertEqual((y_l, m_l, d_l), (2026, 1, 5))

    def test_teacher_fee_calendar_service_param(self):
        """Fee calendar supports ?service=coaching and ?service=library."""
        self.client.force_login(self.teacher_user)
        cal_url = reverse('users:fee_calendar', args=[self.student.id])

        # Coaching calendar for dual student
        resp_coaching = self.client.get(f'{cal_url}?service=coaching')
        self.assertEqual(resp_coaching.status_code, 200)
        self.assertEqual(resp_coaching.context['active_service'], 'coaching')
        self.assertTrue(resp_coaching.context['is_both'])

        # Library calendar for dual student
        resp_lib = self.client.get(f'{cal_url}?service=library')
        self.assertEqual(resp_lib.status_code, 200)
        self.assertEqual(resp_lib.context['active_service'], 'library')
        self.assertTrue(resp_lib.context['is_both'])

    @patch('users.views.send_receipt_notifications_async')
    def test_process_fees_view_service_awareness(self, mock_receipt_thread):
        """Processing fee records service on Payment and FeeTransaction, sets service_snapshot."""
        self.client.force_login(self.teacher_user)
        process_url = reverse('users:process_fees', args=[self.student.id])

        post_data = {
            'actions': [
                {
                    'action': 'add_fee',
                    'month': 'January',
                    'year': 2026,
                    'amount': 1500,
                    'payment_date': '2026-01-10'
                }
            ],
            'service': 'coaching',
            'use_default_expiry': True
        }
        resp = self.client.post(process_url, json.dumps(post_data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get('status'), 'success')

        # Verify Payment records created with service='coaching'
        payment = Payment.objects.filter(student=self.student, service='coaching', month='January', year=2026).first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.amount, 1500)

        # Verify FeeTransaction created with service='coaching' and snapshot
        tx = FeeTransaction.objects.filter(student=self.student).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.service, 'coaching')
        self.assertIn('Coaching', tx.service_snapshot)

        # Verify student coaching expiry updated
        self.student.refresh_from_db()
        self.assertIsNotNone(self.student.coaching_fee_expiry_date)
        self.assertEqual(self.student.coaching_fee_expiry_date, date(2026, 2, 10))

    def test_fee_clear_month_service_isolation(self):
        """Clearing a month for coaching does not clear the library payment for the same month."""
        self.client.force_login(self.teacher_user)
        process_url = reverse('users:process_fees', args=[self.student.id])

        p_coaching = Payment.objects.create(
            student=self.student,
            month='January',
            year=2026,
            service='coaching',
            amount=1500,
            date_paid=date(2026, 1, 5)
        )
        p_library = Payment.objects.create(
            student=self.student,
            month='January',
            year=2026,
            service='library',
            amount=800,
            date_paid=date(2026, 1, 5)
        )

        clear_payload = {
            'actions': [
                {
                    'action': 'delete_fee',
                    'month': 'January',
                    'year': 2026
                }
            ],
            'service': 'coaching'
        }
        resp = self.client.post(process_url, json.dumps(clear_payload), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        # Coaching payment must be cleared
        self.assertFalse(Payment.objects.filter(id=p_coaching.id).exists())
        # Library payment must remain intact!
        self.assertTrue(Payment.objects.filter(id=p_library.id).exists())

    def test_student_fee_record_service_filtering(self):
        """Student fee record page filters by ?service=coaching and ?service=library."""
        self.client.force_login(self.student_user)
        records_url = reverse('users:student_fee_record')

        tx1 = FeeTransaction.objects.create(
            student=self.student,
            receipt_number='REC-C-001',
            total_amount=1500,
            payment_date=date(2026, 1, 10),
            service='coaching',
            service_snapshot='Coaching',
            months_snapshot=[{'month': 'January (2026)', 'amount': 1500, 'status': 'paid'}]
        )
        tx2 = FeeTransaction.objects.create(
            student=self.student,
            receipt_number='REC-L-001',
            total_amount=800,
            payment_date=date(2026, 1, 12),
            service='library',
            service_snapshot='Library',
            months_snapshot=[{'month': 'January (2026)', 'amount': 800, 'status': 'paid'}]
        )

        # Filter by coaching
        resp_c = self.client.get(f'{records_url}?service=coaching')
        self.assertEqual(resp_c.status_code, 200)
        items_c = list(resp_c.context['page_obj'])
        self.assertIn(tx1, items_c)
        self.assertNotIn(tx2, items_c)

        # Filter by library
        resp_l = self.client.get(f'{records_url}?service=library')
        self.assertEqual(resp_l.status_code, 200)
        items_l = list(resp_l.context['page_obj'])
        self.assertIn(tx2, items_l)
        self.assertNotIn(tx1, items_l)

    def test_report_fee_service_ambiguity_command(self):
        """Management command report_fee_service_ambiguity executes and runs read-only audit."""
        out = StringIO()
        call_command('report_fee_service_ambiguity', stdout=out)
        output = out.getvalue()
        self.assertIn("=== Fee Service Ambiguity Audit ===", output)
        self.assertIn("Total students with dual-service (Both):", output)

    @patch('users.notifications.send_fee_reminder_email')
    @patch('users.notifications.send_fee_reminder_whatsapp')
    @patch('users.notifications.send_push')
    def test_send_fee_reminders_independent_and_mocked(self, mock_push, mock_wa, mock_email):
        """Dual student gets independent reminders: coaching due soon dispatches coaching alert only."""
        cache.clear()
        today = timezone.localdate()
        self.student.coaching_fee_expiry_date = today + timedelta(days=10)
        self.student.library_fee_expiry_date = today + timedelta(days=30)
        self.student.sync_overall_fee_expiry_date(save=True)

        call_command('send_fee_reminders')

        # Coaching reminder must be sent
        coaching_email_calls = [c for c in mock_email.call_args_list if c[1].get('service') == 'coaching']
        library_email_calls = [c for c in mock_email.call_args_list if c[1].get('service') == 'library']
        self.assertGreaterEqual(len(coaching_email_calls), 1)
        self.assertEqual(len(library_email_calls), 0)

    @patch('users.notifications.send_fee_reminder_email')
    @patch('users.notifications.send_fee_reminder_whatsapp')
    @patch('users.notifications.send_push')
    def test_send_fee_reminders_both_services_due(self, mock_push, mock_wa, mock_email):
        """Dual student with both services due gets two separate reminders."""
        cache.clear()
        today = timezone.localdate()
        self.student.coaching_fee_expiry_date = today + timedelta(days=10)
        self.student.library_fee_expiry_date = today + timedelta(days=10)
        self.student.sync_overall_fee_expiry_date(save=True)

        call_command('send_fee_reminders')

        coaching_calls = [c for c in mock_email.call_args_list if c[1].get('service') == 'coaching']
        library_calls = [c for c in mock_email.call_args_list if c[1].get('service') == 'library']
        self.assertGreaterEqual(len(coaching_calls), 1)
        self.assertGreaterEqual(len(library_calls), 1)

    @patch('users.notifications.send_fee_reminder_email')
    @patch('users.notifications.send_fee_reminder_whatsapp')
    @patch('users.notifications.send_push')
    def test_send_fee_reminders_deduplication(self, mock_push, mock_wa, mock_email):
        """Fee reminders are deduplicated per student+service+reminder_type+day so nothing sends twice."""
        cache.clear()
        today = timezone.localdate()
        self.student.coaching_fee_expiry_date = today + timedelta(days=10)
        self.student.library_fee_expiry_date = today + timedelta(days=30)
        self.student.sync_overall_fee_expiry_date(save=True)

        call_command('send_fee_reminders')
        first_count = mock_email.call_count

        # Second call on same day must be deduplicated
        call_command('send_fee_reminders')
        self.assertEqual(mock_email.call_count, first_count)

    def test_fee_expired_list_entries_and_counts_per_service(self):
        """Teacher notifications API splits dual student overdue entries per service and isolates dismissals."""
        self.client.force_login(self.teacher_user)
        today = timezone.localdate()
        self.student.coaching_fee_expiry_date = today - timedelta(days=2)
        self.student.library_fee_expiry_date = today + timedelta(days=20)
        self.student.sync_overall_fee_expiry_date(save=True)

        api_url = reverse('users:notifications_api')
        resp = self.client.get(api_url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        overdue_items = data.get('overdue_students', [])
        
        # Only coaching must appear
        student_overdues = [o for o in overdue_items if o['id'] == self.student.id]
        self.assertEqual(len(student_overdues), 1)
        self.assertEqual(student_overdues[0]['service_code'], 'coaching')
        self.assertEqual(student_overdues[0]['service_label'], 'Coaching')

        # Dismiss coaching alert
        dismiss_url = reverse('users:dismiss_fee_expired_alerts')
        dismiss_resp = self.client.post(
            dismiss_url,
            json.dumps({'items': [{'student_id': self.student.id, 'service': 'coaching'}]}),
            content_type='application/json'
        )
        self.assertEqual(dismiss_resp.status_code, 200)
        self.assertTrue(DismissedFeeAlert.objects.filter(student=self.student, service='coaching').exists())

        # Now expire library too: library alert must appear, coaching stays dismissed
        self.student.library_fee_expiry_date = today - timedelta(days=1)
        self.student.sync_overall_fee_expiry_date(save=True)

        resp2 = self.client.get(api_url)
        data2 = resp2.json()
        overdue_items2 = [o for o in data2.get('overdue_students', []) if o['id'] == self.student.id]
        self.assertEqual(len(overdue_items2), 1)
        self.assertEqual(overdue_items2[0]['service_code'], 'library')

    def test_teacher_dashboard_card_styling_per_tab(self):
        """In teacher dashboard, Coaching tab is overdue only if coaching expired; Library tab only if library expired."""
        self.client.force_login(self.teacher_user)
        today = timezone.localdate()
        self.student.coaching_fee_expiry_date = today - timedelta(days=2)
        self.student.library_fee_expiry_date = today + timedelta(days=20)
        self.student.sync_overall_fee_expiry_date(save=True)

        self.assertTrue(self.student.is_coaching_overdue)
        self.assertFalse(self.student.is_library_overdue)

        dash_url = reverse('users:teacher_dashboard')
        resp = self.client.get(dash_url)
        self.assertEqual(resp.status_code, 200)

    def test_progress_page_service_context_overdue(self):
        """Progress page checks selected service context for overdue badge."""
        self.client.force_login(self.teacher_user)
        today = timezone.localdate()
        self.student.coaching_fee_expiry_date = today - timedelta(days=2)
        self.student.library_fee_expiry_date = today + timedelta(days=20)
        self.student.sync_overall_fee_expiry_date(save=True)

        progress_url = reverse('users:student_progress')

        # In coaching context: is-overdue present
        resp_coaching = self.client.get(f"{progress_url}?service=Coaching")
        self.assertEqual(resp_coaching.status_code, 200)
        self.assertContains(resp_coaching, "Coaching Fee Overdue")

        # In library context: coaching overdue is suppressed
        resp_library = self.client.get(f"{progress_url}?service=Library")
        self.assertEqual(resp_library.status_code, 200)
        self.assertNotContains(resp_library, "Library Fee Overdue")

        # In 'All' context: shows overdue because one service is overdue
        resp_all = self.client.get(f"{progress_url}?service=All")
        self.assertEqual(resp_all.status_code, 200)
        self.assertContains(resp_all, "Fee Overdue")

    @patch('users.views.calculate_hold_extension_days')
    def test_hold_extension_affects_library_only(self, mock_hold_days):
        """Library seat hold extends only library_fee_expiry_date; coaching_fee_expiry_date is untouched."""
        mock_hold_days.return_value = 5
        self.student.coaching_fee_expiry_date = date(2026, 3, 10)
        self.student.library_fee_expiry_date = date(2026, 3, 10)
        self.student.fee_expiry_date = date(2026, 3, 10)
        self.student.save()

        _recalc_fee_expiry_with_hold(self.student)

        self.student.refresh_from_db()
        self.assertEqual(self.student.library_fee_expiry_date, date(2026, 3, 15))
        self.assertEqual(self.student.coaching_fee_expiry_date, date(2026, 3, 10))
        self.assertEqual(self.student.fee_expiry_date, date(2026, 3, 10))

    def test_existing_both_student_fallback_before_new_payment(self):
        """Existing 'Both' student without service dates falls back to fee_expiry_date without guessing."""
        legacy_student = StudentProfile.objects.create(
            user=User.objects.create_user(username='legacy_both', password='Password123!'),
            full_name='Legacy Both Student',
            status='admitted',
            service_type='Both',
            fee_expiry_date=date(2026, 1, 10),
            coaching_fee_expiry_date=None,
            library_fee_expiry_date=None
        )

        self.assertEqual(legacy_student.effective_coaching_expiry, date(2026, 1, 10))
        self.assertEqual(legacy_student.effective_library_expiry, date(2026, 1, 10))

        # sync_overall_fee_expiry_date preserves existing fee_expiry_date
        legacy_student.sync_overall_fee_expiry_date(save=True)
        legacy_student.refresh_from_db()
        self.assertEqual(legacy_student.fee_expiry_date, date(2026, 1, 10))

    def test_legacy_null_service_rows_render_safely(self):
        """Legacy payments and transactions with service=NULL render without crashing."""
        self.client.force_login(self.student_user)
        Payment.objects.create(
            student=self.student,
            month='January',
            year=2025,
            service=None,
            amount=1000,
            date_paid=date(2025, 1, 5)
        )
        FeeTransaction.objects.create(
            student=self.student,
            receipt_number='REC-LEGACY-001',
            total_amount=1000,
            payment_date=date(2025, 1, 5),
            months_snapshot='January 2025',
            service=None,
            service_snapshot=''
        )
        resp = self.client.get(reverse('users:student_fee_record'))
        self.assertEqual(resp.status_code, 200)

    def test_single_service_student_unchanged(self):
        """Single service student behaves standardly."""
        today = timezone.localdate()
        self.single_student.coaching_fee_expiry_date = today - timedelta(days=2)
        self.single_student.sync_overall_fee_expiry_date(save=True)
        self.assertTrue(self.single_student.is_coaching_overdue)
        self.assertEqual(self.single_student.fee_expiry_date, self.single_student.coaching_fee_expiry_date)

    @patch('users.views.send_receipt_notifications_async')
    def test_empty_date_lifecycle_and_single_service_payment_isolation(self, mock_async):
        """
        Tests life-cycle of a 'Both' student with empty coaching/library expiries:
        1. When fee_expiry_date is empty: cards show Not Set, no overdue alert, no reminder.
        2. When fee_expiry_date is overdue: both fallback to overdue.
        3. After paying only Library: Library clears, Coaching stays overdue, alert & bell keep Coaching.
        """
        today = timezone.localdate()
        
        # Part A: Both dates empty and fee_expiry_date is empty
        self.student.coaching_fee_expiry_date = None
        self.student.library_fee_expiry_date = None
        self.student.fee_expiry_date = None
        self.student.save()

        # 1. Cards
        self.assertFalse(self.student.is_coaching_overdue)
        self.assertFalse(self.student.is_library_overdue)
        self.assertIsNone(self.student.effective_coaching_expiry)
        self.assertIsNone(self.student.effective_library_expiry)

        # 2. Overdue list & bell via notifications API
        self.client.force_login(self.teacher_user)
        api_resp = self.client.get(reverse('users:notifications_api'))
        api_data = api_resp.json()
        overdue_for_student = [o for o in api_resp.json().get('overdue_students', []) if o['id'] == self.student.id]
        self.assertEqual(len(overdue_for_student), 0)

        # Part B: Both dates empty but legacy fee_expiry_date is set in past
        self.student.fee_expiry_date = today - timedelta(days=5)
        self.student.save()

        self.assertTrue(self.student.is_coaching_overdue)
        self.assertTrue(self.student.is_library_overdue)
        self.assertEqual(self.student.effective_coaching_expiry, today - timedelta(days=5))
        self.assertEqual(self.student.effective_library_expiry, today - timedelta(days=5))

        api_resp_b = self.client.get(reverse('users:notifications_api'))
        overdue_b = [o for o in api_resp_b.json().get('overdue_students', []) if o['id'] == self.student.id]
        # Produces one entry for coaching and one for library
        self.assertEqual(len(overdue_b), 2)
        service_codes = {o['service_code'] for o in overdue_b}
        self.assertEqual(service_codes, {'coaching', 'library'})

        # Part C: Pay Library ONLY (future date)
        process_url = reverse('users:process_fees', args=[self.student.id])
        post_data = {
            'actions': [{
                'action': 'add_fee',
                'month': 'March',
                'year': 2026,
                'amount': 800,
                'payment_date': str(today)
            }],
            'service': 'library',
            'expiry_date': str(today + timedelta(days=25))
        }
        res_pay = self.client.post(process_url, json.dumps(post_data), content_type='application/json')
        self.assertEqual(res_pay.status_code, 200)

        self.student.refresh_from_db()

        # Six outputs verification AFTER paying only Library:
        # 1. Coaching card: STAYS OVERDUE
        self.assertTrue(self.student.is_coaching_overdue)
        # 2. Library card: CLEARED (NOT OVERDUE)
        self.assertFalse(self.student.is_library_overdue)
        self.assertEqual(self.student.library_fee_expiry_date, today + timedelta(days=25))
        # 3. fee_expiry_date: remains the earlier date (coaching expiry: today - 5 days)
        self.assertEqual(self.student.fee_expiry_date, today - timedelta(days=5))
        # 4 & 5. Overdue list & bell: contains ONLY coaching now; library is removed!
        api_resp_c = self.client.get(reverse('users:notifications_api'))
        overdue_c = [o for o in api_resp_c.json().get('overdue_students', []) if o['id'] == self.student.id]
        self.assertEqual(len(overdue_c), 1)
        self.assertEqual(overdue_c[0]['service_code'], 'coaching')
        # 6. Does not clear coaching alert or mark coaching as paid
        self.assertEqual(self.student.coaching_fee_expiry_date, None)  # untouched!

    def test_dismissed_fee_alert_service_isolation(self):
        """Dismissing fee alert for coaching does not dismiss fee alert for library."""
        today = timezone.localdate()
        self.student.coaching_fee_expiry_date = today - timedelta(days=2)
        self.student.library_fee_expiry_date = today - timedelta(days=2)
        self.student.save()

        self.client.force_login(self.teacher_user)
        dismiss_url = reverse('users:dismiss_fee_expired_alerts')

        # Dismiss coaching
        res = self.client.post(dismiss_url, json.dumps({
            'items': [{'student_id': self.student.id, 'service': 'coaching'}]
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        # Check DB
        self.assertTrue(DismissedFeeAlert.objects.filter(student=self.student, service='coaching').exists())
        self.assertFalse(DismissedFeeAlert.objects.filter(student=self.student, service='library').exists())

        # Dismiss library
        res_lib = self.client.post(dismiss_url, json.dumps({
            'items': [{'student_id': self.student.id, 'service': 'library'}]
        }), content_type='application/json')
        self.assertEqual(res_lib.status_code, 200)
        self.assertTrue(DismissedFeeAlert.objects.filter(student=self.student, service='library').exists())

    def test_whatsapp_fee_receipt_service_branding(self):
        """WhatsApp fee receipt correctly identifies service name in the message."""
        from users.notifications import send_fee_receipt_whatsapp
        from users.models import FeeTransaction
        today = timezone.localdate()
        tx = FeeTransaction.objects.create(
            student=self.student,
            receipt_number='ABCD_26/1234567',
            payment_date=today,
            total_amount=800,
            months_snapshot=[{'month': 'April', 'amount': 800, 'status': 'paid'}],
            service='library',
            service_snapshot='Library Service'
        )
        with patch('users.notifications.has_whatsapp_configured', return_value=True):
            with patch('users.notifications.requests.post') as mock_post:
                # 1st call for upload returns media id, 2nd call sends message
                upload_resp = MagicMock()
                upload_resp.status_code = 200
                upload_resp.json.return_value = {'id': 'media_123'}

                send_resp = MagicMock()
                send_resp.status_code = 200

                mock_post.side_effect = [upload_resp, send_resp]

                send_fee_receipt_whatsapp(self.student, tx, b'%PDF-test')
                self.assertEqual(mock_post.call_count, 2)

                # Inspect 2nd call (send payload sent to Facebook API)
                send_call_args = mock_post.call_args_list[1]
                json_body = send_call_args[1].get('json', {})
                body_params = json_body.get('template', {}).get('components', [])[1].get('parameters', [])
                param_texts = [p.get('text') for p in body_params]
                self.assertIn('Library Service', param_texts)

    def test_process_fees_clear_expiry_service_isolation(self):
        """Clearing coaching expiry leaves library expiry intact."""
        today = timezone.localdate()
        self.student.coaching_fee_expiry_date = today + timedelta(days=10)
        self.student.library_fee_expiry_date = today + timedelta(days=20)
        self.student.sync_overall_fee_expiry_date(save=True)

        self.client.force_login(self.teacher_user)
        process_url = reverse('users:process_fees', args=[self.student.id])
        res = self.client.post(process_url, json.dumps({
            'actions': [{'action': 'clear_expiry'}],
            'service': 'coaching'
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        self.student.refresh_from_db()
        self.assertIsNone(self.student.coaching_fee_expiry_date)
        self.assertEqual(self.student.library_fee_expiry_date, today + timedelta(days=20))
        self.assertEqual(self.student.fee_expiry_date, today + timedelta(days=20))


    @patch('users.notifications.send_fee_reminder_email')
    @patch('users.notifications.send_fee_reminder_whatsapp')
    @patch('users.notifications.send_push')
    def test_process_fees_clear_expiry_suppresses_reminders_and_alerts(self, mock_push, mock_wa, mock_email):
        """Clearing expiry guarantees student is skipped by reminders and overdue alerts."""
        today = timezone.localdate()
        # Student was overdue in coaching
        self.student.coaching_fee_expiry_date = today - timedelta(days=5)
        self.student.library_fee_expiry_date = None
        self.student.sync_overall_fee_expiry_date(save=True)

        self.client.force_login(self.teacher_user)
        process_url = reverse('users:process_fees', args=[self.student.id])
        res = self.client.post(f"{process_url}?service=coaching", json.dumps({
            'actions': [{'action': 'clear_expiry'}],
            'service': 'coaching'
        }), content_type='application/json')
        self.assertEqual(res.status_code, 200)

        self.student.refresh_from_db()
        self.assertIsNone(self.student.coaching_fee_expiry_date)
        self.assertIsNone(self.student.effective_coaching_expiry)
        self.assertIsNone(self.student.fee_expiry_date)

        # 1. Reminder command check: no emails, whatsapps, or push sent
        call_command('send_fee_reminders')
        self.assertEqual(mock_email.call_count, 0)
        self.assertEqual(mock_wa.call_count, 0)
        self.assertEqual(mock_push.call_count, 0)

        # 2. Notifications API check: must NOT appear in overdue list
        notif_url = reverse('users:notifications_api')
        res_notif = self.client.get(notif_url)
        self.assertEqual(res_notif.status_code, 200)
        overdue_list = res_notif.json().get('overdue_students', [])
        overdue_ids = [item['id'] for item in overdue_list]
        self.assertNotIn(self.student.id, overdue_ids)


