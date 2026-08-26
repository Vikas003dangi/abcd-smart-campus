import logging
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from users.models import Notification

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Delete read notifications older than 5/30 days with dry-run and safety features."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate the cleanup without actually deleting any records.',
        )

    def handle(self, *args, **kwargs):
        start_time = time.time()
        is_dry_run = kwargs.get('dry_run', False)
        now = timezone.now()
        
        if is_dry_run:
            logger.info("DRY RUN MODE ENABLED: No records will be deleted.")

        logger.info(f"COMMAND START: cleanup_notifications started at {now}")

        # 6. PROTECT RECENT DATA: Define cutoffs
        cutoff_5d = now - timedelta(days=5)
        cutoff_30d = now - timedelta(days=30)

        # 1. NEVER DELETE ACTIVE DATA: Filtering for read notifications only
        # Target Query 1: Read notifications with read_at >= 5 days old (Exclude staff)
        q1 = Notification.objects.filter(
            user__is_staff=False,
            is_read=True,
            read_at__isnull=False,
            read_at__lte=cutoff_5d
        )

        # Target Query 2: Legacy read notifications (read_at is null) >= 30 days old (Exclude staff)
        q2 = Notification.objects.filter(
            user__is_staff=False,
            is_read=True,
            read_at__isnull=True,
            created_at__lte=cutoff_30d
        )

        try:
            if is_dry_run:
                c1 = q1.count()
                c2 = q2.count()
                logger.info(f"DRY RUN: Would delete {c1} read notifications (5d+) and {c2} legacy read notifications (30d+).")
                deleted_by_read_at = c1
                deleted_fallback = c2
            else:
                # 4. TRANSACTION SAFETY
                with transaction.atomic():
                    deleted_by_read_at, _ = q1.delete()
                    deleted_fallback, _ = q2.delete()

            total = deleted_by_read_at + deleted_fallback
            status_text = "WOULD BE DELETED (DRY RUN)" if is_dry_run else "DELETED"
            logger.info(
                f"SUCCESS: Notification cleanup preview/complete. "
                f"{status_text} - Read(5d+): {deleted_by_read_at}, Legacy(30d+): {deleted_fallback}, Total: {total}"
            )
        except Exception:
            logger.error("FAILURE: Notification cleanup encountered a fatal error.", exc_info=True)

        duration = time.time() - start_time
        status_prefix = "DRY RUN COMPLETE" if is_dry_run else "COMMAND END"
        logger.info(f"{status_prefix}: cleanup_notifications completed in {duration:.2f}s.")
