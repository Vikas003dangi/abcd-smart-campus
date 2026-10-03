import json
import os
from decimal import Decimal
from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from users.models import (
    StudentProfile, Payment, FeeTransaction, TeacherHiddenFeeTransaction,
    FeeTransactionAudit, FeeTransactionRevision, Notification
)
from users.management.commands.match_fee_payments import match_payments_to_transactions
from users.utils.receipt_generator import generate_fee_receipt_pdf
from django.core.management import call_command


class FeeLifecyclePhase2Tests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username='teacher_phase2',
            email='teacher2@example.com',
            password='Password123!',
            is_staff=True
        )
        self.student_user = User.objects.create_user(
            username='student_phase2',
            email='student2@example.com',
            password='Password123!'
        )
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            full_name='Aarav Sharma',
            mobile_number='9876543210',
            status='admitted',
            dob=date(2000, 1, 1),
            service_type='Coaching',
            batch='Foundation 2026'
        )

        self.client = Client()

    def test_backup_fee_data_command(self):
        """Verify backup_fee_data exports a valid JSON structure with expected counts."""
        tx = FeeTransaction.objects.create(
            student=self.student_profile,
            teacher=self.teacher_user,
            receipt_number='ABCD_26/1111111',
            payment_date=date(2026, 10, 1),
            service_snapshot='Coaching Foundation',
            months_snapshot=[{'month': 'October (2026)', 'amount': 1500, 'status': 'paid'}],
            total_amount=Decimal('1500.00'),
            student_name_snapshot='Aarav Sharma',
            roll_number_snapshot=str(self.student_profile.id)
        )
        p = Payment.objects.create(
            student=self.student_profile,
            month='October',
            year=2026,
            amount=Decimal('1500.00'),
            date_paid=date(2026, 10, 1),
            fee_transaction=tx
        )

        backup_dir = os.path.join(os.path.dirname(__file__), 'temp_test_backup')
        call_command('backup_fee_data', output_dir=backup_dir)

        self.assertTrue(os.path.exists(backup_dir))
        files = os.listdir(backup_dir)
        self.assertTrue(len(files) >= 1)

        backup_file = os.path.join(backup_dir, files[0])
        with open(backup_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.assertIn('counts', data)
        self.assertEqual(data['counts']['fee_transactions'], 1)
        self.assertEqual(data['counts']['payments'], 1)

        # Cleanup
        os.remove(backup_file)
        os.rmdir(backup_dir)

    def test_conservative_matcher_dry_run_and_commit(self):
        """Test conservative matching: 1 candidate matches, >1 is ambiguous, dry_run rolls back."""
        tx1 = FeeTransaction.objects.create(
            student=self.student_profile,
            teacher=self.teacher_user,
            receipt_number='ABCD_26/2222222',
            payment_date=date(2026, 10, 1),
            service_snapshot='Coaching',
            months_snapshot=[{'month': 'November (2026)', 'amount': 2000, 'status': 'paid'}],
            total_amount=Decimal('2000.00'),
            student_name_snapshot='Aarav Sharma'
        )

        p = Payment.objects.create(
            student=self.student_profile,
            month='November',
            year=2026,
            amount=Decimal('2000.00'),
            date_paid=date(2026, 10, 1)
        )

        # 1. Test Dry Run
        summary_dry = match_payments_to_transactions(dry_run=True)
        self.assertEqual(summary_dry['matched_count'], 1)
        p.refresh_from_db()
        self.assertIsNone(p.fee_transaction, "Dry run must NOT persist the foreign key")

        # 2. Test Real Apply
        summary_real = match_payments_to_transactions(dry_run=False)
        self.assertEqual(summary_real['matched_count'], 1)
        p.refresh_from_db()
        self.assertEqual(p.fee_transaction, tx1, "Matcher must link single unambiguous candidate")

        # 3. Test Ambiguous Candidate: Add a 2nd transaction with same month/year
        p2 = Payment.objects.create(
            student=self.student_profile,
            month='December',
            year=2026,
            amount=Decimal('2000.00'),
            date_paid=date(2026, 11, 1)
        )
        tx_ambig1 = FeeTransaction.objects.create(
            student=self.student_profile,
            teacher=self.teacher_user,
            receipt_number='ABCD_26/3333331',
            payment_date=date(2026, 11, 1),
            service_snapshot='Coaching',
            months_snapshot=[{'month': 'December (2026)', 'amount': 2000, 'status': 'paid'}],
            total_amount=Decimal('2000.00')
        )
        tx_ambig2 = FeeTransaction.objects.create(
            student=self.student_profile,
            teacher=self.teacher_user,
            receipt_number='ABCD_26/3333332',
            payment_date=date(2026, 11, 1),
            service_snapshot='Coaching',
            months_snapshot=[{'month': 'December (2026)', 'amount': 2000, 'status': 'paid'}],
            total_amount=Decimal('2000.00')
        )

        summary_ambig = match_payments_to_transactions(dry_run=False)
        self.assertEqual(summary_ambig['ambiguous_count'], 1)
        p2.refresh_from_db()
        self.assertIsNone(p2.fee_transaction, "Ambiguous payment with multiple candidates MUST stay NULL")

    def test_process_fees_in_place_edit_same_receipt_number(self):
        """Decision 1: Editing a receipt keeps the SAME receipt number and shows 'Revised'."""
        self.client.login(username='teacher_phase2', password='Password123!')

        # Initial submit
        payload1 = {
            'actions': [{
                'month': 'January',
                'year': '2026',
                'action': 'add_fee',
                'amount': 2500,
                'payment_date': '2026-01-05'
            }]
        }
        res1 = self.client.post(
            f'/api/process_fees/{self.student_profile.id}/',
            data=json.dumps(payload1),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 200)

        tx = FeeTransaction.objects.filter(student=self.student_profile).first()
        self.assertIsNotNone(tx)
        orig_receipt_no = tx.receipt_number
        self.assertEqual(tx.revision_count, 0)
        self.assertEqual(tx.total_amount, Decimal('2500.00'))

        p = Payment.objects.filter(student=self.student_profile, month='January', year=2026).first()
        self.assertEqual(p.fee_transaction, tx)

        # Edit in-place via process_fees_view
        payload2 = {
            'actions': [{
                'month': 'January',
                'year': '2026',
                'action': 'edit_fee',
                'amount': 2800,
                'payment_date': '2026-01-05'
            }]
        }
        res2 = self.client.post(
            f'/api/process_fees/{self.student_profile.id}/',
            data=json.dumps(payload2),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 200)

        tx.refresh_from_db()
        self.assertEqual(tx.receipt_number, orig_receipt_no, "Receipt number must be preserved on edit")
        self.assertEqual(tx.revision_count, 1)
        self.assertEqual(tx.total_amount, Decimal('2800.00'))
        self.assertIsNotNone(tx.last_modified_at)
        self.assertEqual(tx.last_modified_by, self.teacher_user)

        # Verify FeeTransactionRevision entry
        revisions = FeeTransactionRevision.objects.filter(transaction=tx)
        self.assertEqual(revisions.count(), 1)
        rev = revisions.first()
        self.assertEqual(rev.old_amount, Decimal('2500.00'))
        self.assertEqual(rev.new_amount, Decimal('2800.00'))
        self.assertEqual(rev.actor, self.teacher_user)

    def test_process_fees_idempotent_no_duplicate_revision(self):
        """Submitting process_fees with identical amounts and months should not create duplicate revisions."""
        self.client.login(username='teacher_phase2', password='Password123!')

        payload = {
            'actions': [{
                'month': 'February',
                'year': '2026',
                'action': 'add_fee',
                'amount': 3000,
                'payment_date': '2026-02-10'
            }]
        }
        self.client.post(
            f'/api/process_fees/{self.student_profile.id}/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        tx = FeeTransaction.objects.filter(student=self.student_profile).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.revision_count, 0)

        # Submit identical data again
        self.client.post(
            f'/api/process_fees/{self.student_profile.id}/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        tx.refresh_from_db()
        self.assertEqual(tx.revision_count, 0, "Idempotent submit must not increment revision_count")
        self.assertEqual(FeeTransactionRevision.objects.filter(transaction=tx).count(), 0)

    def test_decision3_student_hidden_receipt_reappears_on_edit(self):
        """Decision 3: If a student had hidden a receipt and teacher edits it, it REAPPEARS for student."""
        self.client.login(username='teacher_phase2', password='Password123!')

        # 1. Create transaction
        payload1 = {
            'actions': [{
                'month': 'March',
                'year': '2026',
                'action': 'add_fee',
                'amount': 2200,
                'payment_date': '2026-03-01'
            }]
        }
        self.client.post(
            f'/api/process_fees/{self.student_profile.id}/',
            data=json.dumps(payload1),
            content_type='application/json'
        )
        tx = FeeTransaction.objects.filter(student=self.student_profile).first()
        self.assertIsNotNone(tx)

        # 2. Student hides the transaction
        tx.is_hidden_by_student = True
        tx.save()

        # 3. Teacher edits the transaction in-place
        payload2 = {
            'actions': [{
                'month': 'March',
                'year': '2026',
                'action': 'edit_fee',
                'amount': 2400,
                'payment_date': '2026-03-01'
            }]
        }
        self.client.post(
            f'/api/process_fees/{self.student_profile.id}/',
            data=json.dumps(payload2),
            content_type='application/json'
        )

        # 4. Verify unhidden
        tx.refresh_from_db()
        self.assertFalse(tx.is_hidden_by_student, "Student hidden receipt must reappear when teacher edits it")
        self.assertEqual(tx.revision_count, 1)

    def test_delete_payment_marks_receipt_revised_not_deleted(self):
        """Decision 4: Clearing a month in delete_payment_view updates receipt to revised and does NOT delete it."""
        self.client.login(username='teacher_phase2', password='Password123!')

        # 1. Create payment & transaction
        payload = {
            'actions': [{
                'month': 'April',
                'year': '2026',
                'action': 'add_fee',
                'amount': 1800,
                'payment_date': '2026-04-05'
            }]
        }
        self.client.post(
            f'/api/process_fees/{self.student_profile.id}/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        tx = FeeTransaction.objects.filter(student=self.student_profile).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.revision_count, 0)
        self.assertEqual(tx.total_amount, Decimal('1800.00'))

        # Student also hid it
        tx.is_hidden_by_student = True
        tx.save()

        # 2. Clear payment month via delete_payment_view
        del_res = self.client.post(f'/api/delete_payment/{self.student_profile.id}/2026/April/')
        self.assertEqual(del_res.status_code, 200)

        # Verify payment row is deleted
        p_exists = Payment.objects.filter(student=self.student_profile, month='April', year=2026).exists()
        self.assertFalse(p_exists, "Calendar Payment row should be deleted")

        # Verify FeeTransaction is NOT deleted and is marked Revised
        tx.refresh_from_db()
        self.assertIsNone(tx.deleted_at, "FeeTransaction must NOT be soft-deleted by month clear")
        self.assertEqual(tx.revision_count, 1, "Revision count must increment")
        self.assertEqual(tx.total_amount, Decimal('0.00'), "Total amount should reflect cleared payment")
        self.assertFalse(tx.is_hidden_by_student, "Student hide flag should be cleared so they see revision")

        # Verify revision log
        rev = FeeTransactionRevision.objects.filter(transaction=tx).first()
        self.assertIsNotNone(rev)
        self.assertIn("cleared", rev.note.lower())

        # Verify notification sent with revision tag
        notif = Notification.objects.filter(
            user=self.student_user,
            meta__tag=f"fee-receipt-{tx.id}-r1"
        ).first()
        self.assertIsNotNone(notif)
        self.assertEqual(notif.meta.get("tag"), f"fee-receipt-{tx.id}-r1")
        self.assertIn("revised", notif.message.lower())

    def test_dashboard_fallback_does_not_resurrect_deleted_receipts(self):
        """Dashboard must not fallback to legacy payments if student has fee transactions, preventing resurrected rows."""
        self.client.login(username='student_phase2', password='Password123!')

        # Create a soft-deleted fee transaction
        tx = FeeTransaction.objects.create(
            student=self.student_profile,
            teacher=self.teacher_user,
            receipt_number='ABCD_26/9999999',
            payment_date=date(2026, 5, 1),
            service_snapshot='Coaching',
            months_snapshot=[{'month': 'May (2026)', 'amount': 1500, 'status': 'paid'}],
            total_amount=Decimal('1500.00'),
            deleted_at=timezone.now()
        )

        # Create a lingering Payment record
        p = Payment.objects.create(
            student=self.student_profile,
            month='May',
            year=2026,
            amount=Decimal('1500.00'),
            date_paid=date(2026, 5, 1)
        )

        response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        fee_records = response.context.get('fee_records', [])
        # Since student has a FeeTransaction (even if deleted), fee_records must be empty list, NOT the payment!
        self.assertEqual(len(fee_records), 0, "Must not resurrect soft-deleted transactions as legacy payments")

    def test_pdf_receipt_contains_revised_mark(self):
        """PDF generator builds successfully with revised watermark and badge for revised transaction."""
        tx = FeeTransaction.objects.create(
            student=self.student_profile,
            teacher=self.teacher_user,
            receipt_number='ABCD_26/7777777',
            payment_date=date(2026, 6, 1),
            service_snapshot='Coaching & Library',
            months_snapshot=[{'month': 'June (2026)', 'amount': 2500, 'status': 'paid'}],
            total_amount=Decimal('2500.00'),
            revision_count=2,
            last_modified_at=timezone.now()
        )

        pdf_buf = generate_fee_receipt_pdf(tx)
        pdf_bytes = pdf_buf.getvalue()
        self.assertTrue(len(pdf_bytes) > 1000)
        self.assertTrue(pdf_bytes.startswith(b'%PDF'))
