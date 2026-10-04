"""
Management command to audit and report service ambiguity in Fee Payments and Transactions.

Part C4 Requirement:
Detects and reports records where `service` ('coaching' vs 'library') is ambiguous,
particularly for dual-service ('Both') students.
Provides optional `--fix` flag to safely auto-backfill service attributes based on
`service_snapshot` and student profile defaults.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from users.models import StudentProfile, Payment, FeeTransaction
from users.views import sync_student_fee_chain


class Command(BaseCommand):
    help = "Audit and report service ambiguity in Fee Payments and Fee Transactions."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Safely backfill empty service fields where unambiguous context exists.',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Print detailed student-by-student reports.',
        )

    def handle(self, *args, **options):
        fix = options['fix']
        verbose = options['verbose']

        self.stdout.write(self.style.MIGRATE_HEADING("=== Fee Service Ambiguity Audit ==="))

        both_students = StudentProfile.objects.filter(service_type='Both')
        total_both = both_students.count()
        self.stdout.write(f"Total students with dual-service (Both): {total_both}")

        # Payments Audit
        total_payments = Payment.objects.count()
        payments_coaching = Payment.objects.filter(service='coaching').count()
        payments_library = Payment.objects.filter(service='library').count()
        payments_empty = Payment.objects.filter(Q(service__isnull=True) | Q(service='')).count()

        self.stdout.write("\n--- Payments Breakdown ---")
        self.stdout.write(f"Total Payments: {total_payments}")
        self.stdout.write(f"  - Coaching: {payments_coaching}")
        self.stdout.write(f"  - Library: {payments_library}")
        self.stdout.write(f"  - Empty / Legacy: {payments_empty}")

        # Fee Transactions Audit
        total_tx = FeeTransaction.objects.count()
        tx_coaching = FeeTransaction.objects.filter(service='coaching').count()
        tx_library = FeeTransaction.objects.filter(service='library').count()
        tx_empty = FeeTransaction.objects.filter(Q(service__isnull=True) | Q(service='')).count()

        self.stdout.write("\n--- Fee Transactions Breakdown ---")
        self.stdout.write(f"Total Transactions: {total_tx}")
        self.stdout.write(f"  - Coaching: {tx_coaching}")
        self.stdout.write(f"  - Library: {tx_library}")
        self.stdout.write(f"  - Empty / Legacy: {tx_empty}")

        # Ambiguity in 'Both' Students
        ambiguous_both_payments = 0
        ambiguous_both_tx = 0
        students_with_ambiguity = []

        for student in both_students:
            s_payments_empty = Payment.objects.filter(
                student=student
            ).filter(Q(service__isnull=True) | Q(service=''))

            s_tx_empty = FeeTransaction.objects.filter(
                student=student
            ).filter(Q(service__isnull=True) | Q(service=''))

            p_empty_cnt = s_payments_empty.count()
            tx_empty_cnt = s_tx_empty.count()

            if p_empty_cnt > 0 or tx_empty_cnt > 0:
                ambiguous_both_payments += p_empty_cnt
                ambiguous_both_tx += tx_empty_cnt
                students_with_ambiguity.append((student, p_empty_cnt, tx_empty_cnt))
                if verbose:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Student {student.full_name} (ID {student.id}): "
                            f"{p_empty_cnt} empty payments, {tx_empty_cnt} empty transactions."
                        )
                    )

        self.stdout.write("\n--- Dual-Service Ambiguity ---")
        self.stdout.write(f"Dual-service students with unassigned records: {len(students_with_ambiguity)}")
        self.stdout.write(f"Unassigned Payments for dual-service students: {ambiguous_both_payments}")
        self.stdout.write(f"Unassigned Transactions for dual-service students: {ambiguous_both_tx}")

        # Expiry Audit for Dual-Service
        missing_coaching_exp = both_students.filter(coaching_fee_expiry_date__isnull=True).count()
        missing_library_exp = both_students.filter(library_fee_expiry_date__isnull=True).count()
        self.stdout.write(f"Dual-service students missing coaching expiry: {missing_coaching_exp}")
        self.stdout.write(f"Dual-service students missing library expiry: {missing_library_exp}")

        if fix:
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Applying Safe Auto-Backfill (--fix) ==="))
            fixed_tx = 0
            fixed_payments = 0

            # 1. Backfill FeeTransaction where service_snapshot clearly specifies
            for tx in FeeTransaction.objects.filter(Q(service__isnull=True) | Q(service='')):
                snap = (tx.service_snapshot or '').lower()
                resolved = None
                if 'coaching' in snap and 'library' not in snap:
                    resolved = 'coaching'
                elif 'library' in snap and 'coaching' not in snap:
                    resolved = 'library'
                elif tx.student and tx.student.service_type in ['Coaching', 'Library']:
                    resolved = tx.student.service_type.lower()

                if resolved:
                    tx.service = resolved
                    tx.save(update_fields=['service'])
                    fixed_tx += 1

            # 2. Backfill Payment where service is blank
            for p in Payment.objects.filter(Q(service__isnull=True) | Q(service='')):
                resolved = None
                # Check student's service_type if single
                if p.student and p.student.service_type in ['Coaching', 'Library']:
                    resolved = p.student.service_type.lower()
                elif p.student and p.student.service_type == 'Both':
                    # Check linked fee transactions in same month/year
                    matching_tx = FeeTransaction.objects.filter(
                        student=p.student,
                        month=p.month,
                        year=p.year
                    ).exclude(Q(service__isnull=True) | Q(service='')).first()
                    if matching_tx:
                        resolved = matching_tx.service
                    else:
                        snap_tx = FeeTransaction.objects.filter(
                            student=p.student,
                            month=p.month,
                            year=p.year
                        ).first()
                        if snap_tx and snap_tx.service_snapshot:
                            snap = snap_tx.service_snapshot.lower()
                            if 'coaching' in snap and 'library' not in snap:
                                resolved = 'coaching'
                            elif 'library' in snap and 'coaching' not in snap:
                                resolved = 'library'

                if resolved:
                    p.service = resolved
                    p.save(update_fields=['service'])
                    fixed_payments += 1

            self.stdout.write(self.style.SUCCESS(f"Successfully backfilled {fixed_tx} transactions and {fixed_payments} payments."))

            # 3. Resync affected dual-service chains
            resynced = 0
            for student, _, _ in students_with_ambiguity:
                sync_student_fee_chain(student, service='coaching')
                sync_student_fee_chain(student, service='library')
                resynced += 1

            self.stdout.write(self.style.SUCCESS(f"Resynced fee chains for {resynced} dual-service students."))
        else:
            self.stdout.write(self.style.NOTICE("\nRun with --fix to automatically backfill unambiguous records."))
