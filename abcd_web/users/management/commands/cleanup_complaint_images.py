import logging
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.db import transaction
from users.models import Complaint

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Delete images of resolved complaints older than 5 days with dry-run and safety features."

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate the cleanup without actually deleting any image files or updating records.',
        )

    def handle(self, *args, **kwargs):
        start_time = time.time()
        is_dry_run = kwargs.get('dry_run', False)
        now = timezone.now()
        
        if is_dry_run:
            logger.info("DRY RUN MODE ENABLED: No files will be deleted and no records will be updated.")

        logger.info(f"COMMAND START: cleanup_complaint_images started at {now}")

        # Protect recent data: Define the 5-day cutoff
        cutoff_5d = now - timedelta(days=5)
        logger.info(f"Targeting resolved complaints with resolved_at <= {cutoff_5d}")

        # Filter resolved complaints with resolved_at older than or equal to 5 days
        q = Complaint.objects.filter(
            status=Complaint.STATUS_RESOLVED,
            resolved_at__isnull=False,
            resolved_at__lte=cutoff_5d
        )

        # Count how many complaints have images
        # We only want to process complaints that actually have at least one image attached
        target_complaints = []
        for complaint in q:
            if complaint.image1 or complaint.image2 or complaint.image3:
                target_complaints.append(complaint)

        total_complaints = len(target_complaints)
        logger.info(f"Found {total_complaints} resolved complaints (5d+) with attached images to clean up.")

        cleaned_count = 0
        file_delete_count = 0
        failed_count = 0

        # Run with transaction safety
        with transaction.atomic():
            for c in target_complaints:
                try:
                    images_to_delete = []
                    if c.image1:
                        images_to_delete.append(('image1', c.image1))
                    if c.image2:
                        images_to_delete.append(('image2', c.image2))
                    if c.image3:
                        images_to_delete.append(('image3', c.image3))

                    c_modified = False
                    for field_name, img_field in images_to_delete:
                        if is_dry_run:
                            logger.info(f"DRY RUN: Would delete file {img_field.name} for Complaint ID {c.id}")
                            file_delete_count += 1
                            c_modified = True
                        else:
                            try:
                                # delete(save=False) removes the file on disk and clears the attribute on the model instance
                                img_field.delete(save=False)
                                file_delete_count += 1
                                c_modified = True
                            except Exception as e:
                                logger.warning(f"FILE DELETE ERROR: Could not delete {field_name} for complaint {c.id}: {str(e)}")

                    if c_modified:
                        if not is_dry_run:
                            c.save(update_fields=['image1', 'image2', 'image3', 'updated_at'])
                        cleaned_count += 1

                except Exception as e:
                    logger.error(f"FAILURE: Error cleaning up images for complaint {c.id}: {str(e)}", exc_info=True)
                    failed_count += 1

        duration = time.time() - start_time
        status_prefix = "DRY RUN COMPLETE" if is_dry_run else "COMMAND END"
        logger.info(
            f"{status_prefix}: cleanup_complaint_images completed in {duration:.2f}s. "
            f"Complaints {'would be ' if is_dry_run else ''}cleaned: {cleaned_count}, "
            f"Files {'would be ' if is_dry_run else ''}deleted: {file_delete_count}, "
            f"Failed: {failed_count}"
        )
