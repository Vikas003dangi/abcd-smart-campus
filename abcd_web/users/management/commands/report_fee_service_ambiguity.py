"""
Management command to audit and report service ambiguity in Fee Payments and Transactions.

Part C4 Requirement:
Detects and reports records where `service` ('coaching' vs 'library') is unassigned,
particularly for dual-service ('Both') students.
STRICTLY READ-ONLY: Never rewrites or guesses legacy data.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from users.models import StudentProfile, Payment, FeeTransaction


class Command(BaseCommand):
    help = "Audit and report service ambiguity in Fee Payments and Fee Transactions (strictly read-only)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Dry-run inspect potential resolutions without modifying any database records.',
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
            self.stdout.write(self.style.MIGRATE_HEADING("\n=== Dry-Run Ambiguity Analysis (--fix flag) ==="))
            self.stdout.write(
                self.style.WARNING(
                    "NOTICE: Automatic data rewriting is permanently disabled by policy.\n"
                    "Legacy fee rows remain intact with NULL/blank service and continue rendering safely.\n"
                    "No database modifications were made."
                )
            )
            inspect_tx = 0
            inspect_payments = 0

            for tx in FeeTransaction.objects.filter(Q(service__isnull=True) | Q(service='')):
                snap = (tx.service_snapshot or '').lower()
                if 'coaching' in snap and 'library' not in snap:
                    inspect_tx += 1
                elif 'library' in snap and 'coaching' not in snap:
                    inspect_tx += 1
                elif tx.student and tx.student.service_type in ['Coaching', 'Library']:
                    inspect_tx += 1

            for p in Payment.objects.filter(Q(service__isnull=True) | Q(service='')):
                if p.student and p.student.service_type in ['Coaching', 'Library']:
                    inspect_payments += 1

            self.stdout.write(
                f"\nPotential unambiguous legacy rows identified (read-only): "
                f"{inspect_tx} transactions, {inspect_payments} payments.\n"
                f"Status: Preserved without changes."
            )
        else:
            self.stdout.write(
                self.style.NOTICE(
                    "\nAll legacy records are preserved as-is. Run with --verbose for student details."
                )
            )
