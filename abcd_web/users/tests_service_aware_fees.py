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
from datetime import date
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse
from django.core.management import call_command
from io import StringIO

from users.models import StudentProfile, Payment, FeeTransaction
from users.views import sync_student_fee_chain

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
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            full_name='Dual Service Student',
            status='admitted',
            service_type='Both',
            mobile_number='9876543210'
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

    def test_process_fees_view_service_awareness(self):
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
        """Management command report_fee_service_ambiguity executes and runs audit."""
        out = StringIO()
        call_command('report_fee_service_ambiguity', stdout=out)
        output = out.getvalue()
        self.assertIn("=== Fee Service Ambiguity Audit ===", output)
        self.assertIn("Total students with dual-service (Both):", output)
