import re
from django.core.management.base import BaseCommand
from django.db import transaction
from users.models import Payment, FeeTransaction


def _month_year_in_snapshot(month, year, months_snapshot):
    """
    Checks if month and year are present in a FeeTransaction's months_snapshot list.
    Handles formats:
      - "September (2026)"
      - "(26) September"
      - "(2026) September"
      - "September 2026"
      - "September"
    """
    if not isinstance(months_snapshot, list):
        return False

    month_lower = str(month).strip().lower()
    year_str = str(year).strip()
    year_short = year_str[-2:]

    for item in months_snapshot:
        if not isinstance(item, dict):
            continue
        raw_m = str(item.get('month') or '').strip().lower()

        # Check if month name is in the string
        if month_lower not in raw_m:
            continue

        # Check if year is present (either 4 digits or 2 digits)
        if year_str in raw_m or f"({year_short})" in raw_m or f"/{year_short}" in raw_m:
            return True

        # If no year was explicitly in the month string but month name matches exactly
        if raw_m == month_lower:
            return True

    return False


def match_payments_to_transactions(dry_run=True, stdout=None):
    """
    Conservative matcher that links existing Payment records to FeeTransaction records.
    Returns a dictionary summary of matching stats.
    """
    unlinked_payments = Payment.objects.filter(
        student__isnull=False,
        fee_transaction__isnull=True
    ).select_related('student')

    total_checked = unlinked_payments.count()
    matched_count = 0
    unmatched_count = 0
    ambiguous_count = 0

    report_lines = []

    for p in unlinked_payments:
        # Candidate search
        candidates = FeeTransaction.objects.filter(
            student_id=p.student_id,
            deleted_at__isnull=True
        )

        matched_candidates = []
        for tx in candidates:
            if _month_year_in_snapshot(p.month, p.year, tx.months_snapshot):
                matched_candidates.append(tx)

        if len(matched_candidates) == 1:
            chosen_tx = matched_candidates[0]
            matched_count += 1
            report_lines.append(
                f"[MATCH] Payment #{p.id} ({p.student.full_name} - {p.month} {p.year}) -> Tx #{chosen_tx.id} ({chosen_tx.receipt_number})"
            )
            if not dry_run:
                p.fee_transaction = chosen_tx
                p.save(update_fields=['fee_transaction'])
        elif len(matched_candidates) > 1:
            ambiguous_count += 1
            report_lines.append(
                f"[AMBIGUOUS] Payment #{p.id} ({p.student.full_name} - {p.month} {p.year}) has {len(matched_candidates)} candidate transactions. Left NULL."
            )
        else:
            unmatched_count += 1

    summary = {
        'total_checked': total_checked,
        'matched_count': matched_count,
        'unmatched_count': unmatched_count,
        'ambiguous_count': ambiguous_count,
        'dry_run': dry_run,
        'report_lines': report_lines,
    }

    return summary


class Command(BaseCommand):
    help = "Conservatively matches and links unlinked Payment records to their corresponding FeeTransaction records."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run the matcher without committing changes to the database'
        )
        parser.add_argument(
            '--report',
            action='store_true',
            help='Print detailed match and ambiguous lines'
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        show_report = options['report']

        self.stdout.write(f"Starting Payment to FeeTransaction conservative matcher (dry_run={dry_run})...")

        with transaction.atomic():
            summary = match_payments_to_transactions(dry_run=dry_run, stdout=self.stdout)
            if dry_run:
                transaction.set_rollback(True)

        if show_report:
            for line in summary['report_lines']:
                self.stdout.write(line)

        self.stdout.write(self.style.SUCCESS(
            f"Matcher complete.\n"
            f"  Total Checked: {summary['total_checked']}\n"
            f"  Matched: {summary['matched_count']}\n"
            f"  Ambiguous (skipped): {summary['ambiguous_count']}\n"
            f"  Unmatched: {summary['unmatched_count']}\n"
            f"  Mode: {'DRY RUN (no database writes)' if dry_run else 'APPLIED TO DATABASE'}"
        ))
