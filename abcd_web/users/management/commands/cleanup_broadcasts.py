import logging
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from users.models import BroadcastMessage

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Delete broadcast history older than 20 days with dry-run and safety features"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate the cleanup without actually deleting any records or files.',
        )

    def handle(self, *args, **kwargs):
        start_time = time.time()
        is_dry_run = kwargs.get('dry_run', False)
        
        # 6. PROTECT RECENT DATA: Enforced via 20-day cutoff
        cutoff = timezone.now() - timedelta(days=20)
        
        if is_dry_run:
            logger.info("DRY RUN MODE ENABLED: No records or files will be deleted.")

        logger.info(f"COMMAND START: cleanup_broadcasts started. Cutoff: {cutoff}")

        # 1. NEVER DELETE ACTIVE DATA: Filter only older than cutoff
        old_broadcasts = BroadcastMessage.objects.filter(created_at__lt=cutoff)
        total_found = old_broadcasts.count()
        
        delete_count = 0
        file_delete_count = 0
        failed_count = 0
        
        # 4. TRANSACTION SAFETY: Group database deletions
        with transaction.atomic():
            for b in old_broadcasts:
                try:
                    # 3. SAFE FILE DELETION
                    
                    # A. Multi-file attachments (BroadcastAttachment model)
                    for att_record in b.attachments.all():
                        if att_record.file:
                            if is_dry_run:
                                logger.info(f"DRY RUN: Would delete multi-file {att_record.file.name} for Broadcast ID {b.id}")
                                file_delete_count += 1
                            else:
                                try:
                                    att_record.file.delete(save=False)
                                    file_delete_count += 1
                                except Exception as e:
                                    logger.warning(f"FILE DELETE ERROR: Could not delete multi-file for broadcast {b.id}: {str(e)}")

                    # B. Legacy single attachment cleanup
                    if b.attachment:
                        if is_dry_run:
                            logger.info(f"DRY RUN: Would delete legacy file {b.attachment.name} for Broadcast ID {b.id}")
                            file_delete_count += 1
                        else:
                            try:
                                # Delete file from storage
                                b.attachment.delete(save=False)
                                file_delete_count += 1
                            except Exception as e:
                                logger.warning(f"FILE DELETE ERROR: Could not delete legacy attachment for broadcast {b.id}: {str(e)}")
                    
                    if is_dry_run:
                        logger.info(f"DRY RUN: Would delete Broadcast record ID {b.id} (Subject: {b.subject})")
                        delete_count += 1
                    else:
                        b.delete()
                        delete_count += 1

                except Exception:
                    logger.error(f"FAILURE: Error processing broadcast {b.id}", exc_info=True)
                    failed_count += 1
            
        duration = time.time() - start_time
        status_prefix = "DRY RUN COMPLETE" if is_dry_run else "COMMAND END"
        logger.info(
            f"{status_prefix}: cleanup_broadcasts completed in {duration:.2f}s. "
            f"Records {'would be ' if is_dry_run else ''}deleted: {delete_count}, "
            f"Files {'would be ' if is_dry_run else ''}deleted: {file_delete_count}, "
            f"Failed: {failed_count}"
        )
