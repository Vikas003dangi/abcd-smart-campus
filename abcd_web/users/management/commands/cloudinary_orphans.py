import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from django.core.management.base import BaseCommand
from django.conf import settings
from users.models import (
    StudentProfile, StudentAchievement, TeacherProfile, GroupChatSession,
    Complaint, Course, StudyMaterial, BroadcastMessage, BroadcastAttachment,
    Message, GroupMessage, TodoTask
)

logger = logging.getLogger(__name__)


def normalize_cloudinary_ref(ref):
    """
    Normalizes a Cloudinary public ID or file path to ensure robust matching:
    - Replaces backslashes with forward slashes
    - Strips leading/trailing whitespace and slashes
    - Strips common prefixes ('media/', 'image/upload/', etc.)
    """
    if not ref:
        return ""
    s = str(ref).strip().replace('\\', '/')
    for prefix in ['media/', 'image/upload/', 'raw/upload/', 'video/upload/']:
        if s.startswith(prefix):
            s = s[len(prefix):]
    return s.strip('/')


def get_active_db_identifiers():
    """
    Collects all active media references across all database models that store files in Cloudinary.
    Returns a set of normalized identifiers (with and without file extension).
    """
    active = set()

    def add_ref(val):
        if not val:
            return
        # If it's a FieldFile, extract .name
        name = getattr(val, 'name', None) or str(val)
        norm = normalize_cloudinary_ref(name)
        if norm:
            active.add(norm.lower())
            root, ext = os.path.splitext(norm)
            if root:
                active.add(root.lower())

    # 1. StudentProfile
    for val in StudentProfile.objects.exclude(photo='').values_list('photo', flat=True):
        add_ref(val)

    # 2. StudentAchievement
    for val in StudentAchievement.objects.exclude(photo='').values_list('photo', flat=True):
        add_ref(val)

    # 3. TeacherProfile
    for val in TeacherProfile.objects.exclude(photo='').values_list('photo', flat=True):
        add_ref(val)

    # 4. GroupChatSession
    for val in GroupChatSession.objects.exclude(photo='').values_list('photo', flat=True):
        add_ref(val)

    # 5. Complaint
    for c in Complaint.objects.all():
        add_ref(c.image1)
        add_ref(c.image2)
        add_ref(c.image3)

    # 6. Course
    for val in Course.objects.exclude(thumbnail='').values_list('thumbnail', flat=True):
        add_ref(val)

    # 7. StudyMaterial
    for mat in StudyMaterial.objects.all():
        add_ref(mat.file)
        add_ref(mat.thumbnail)

    # 8. BroadcastMessage & BroadcastAttachment
    for bm in BroadcastMessage.objects.all():
        add_ref(bm.attachment)
        add_ref(bm.banner_image)
    for val in BroadcastAttachment.objects.exclude(file='').values_list('file', flat=True):
        add_ref(val)

    # 9. Messages
    for val in Message.objects.exclude(file='').values_list('file', flat=True):
        add_ref(val)
    for val in GroupMessage.objects.exclude(file='').values_list('file', flat=True):
        add_ref(val)

    # 10. TodoTask (sticky notes metadata)
    for task in TodoTask.objects.all():
        if isinstance(task.metadata, dict):
            c_ids = task.metadata.get('cloudinary_ids', [])
            if isinstance(c_ids, list):
                for cid in c_ids:
                    add_ref(cid)

    return active


class Command(BaseCommand):
    help = "Audit and clean up orphaned files in Cloudinary not referenced in any database table."

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Actually execute deletion of orphaned Cloudinary files (default is dry-run).'
        )
        parser.add_argument(
            '--confirm',
            type=str,
            default='',
            help='Confirmation phrase required for --apply. Must be "DELETE".'
        )
        parser.add_argument(
            '--min-age-hours',
            type=int,
            default=24,
            help='Minimum age in hours for an asset before it can be considered orphaned (grace period). Default: 24.'
        )
        parser.add_argument(
            '--max-delete',
            type=int,
            default=100,
            help='Maximum number of orphaned files to delete in a single run (hard capped at 100). Default: 100.'
        )

    def handle(self, *args, **options):
        apply_mode = options.get('apply', False)
        confirm_str = options.get('confirm', '').strip()
        min_age_hours = max(1, options.get('min_age_hours', 24))
        max_delete = min(100, max(1, options.get('max_delete', 100)))

        self.stdout.write(self.style.MIGRATE_HEADING("=== Cloudinary Orphan Asset Cleanup ==="))
        self.stdout.write(f"Mode: {'APPLY (Live Deletion)' if apply_mode else 'DRY RUN (Simulated)'}")
        self.stdout.write(f"Grace period: {min_age_hours} hours | Max deletions per run: {max_delete}")

        # Check Cloudinary configuration
        cloud_name = getattr(settings, 'CLOUDINARY_CLOUD_NAME', '')
        api_key = getattr(settings, 'CLOUDINARY_API_KEY', '')
        api_secret = getattr(settings, 'CLOUDINARY_API_SECRET', '')

        if not (cloud_name and api_key and api_secret):
            self.stdout.write(self.style.WARNING(
                "Cloudinary credentials are not configured in settings. Skipping remote scan safely."
            ))
            return

        try:
            import cloudinary
            import cloudinary.api
            import cloudinary.uploader
        except ImportError:
            self.stdout.write(self.style.ERROR("cloudinary Python package is not installed."))
            return

        # 1. Gather active DB files
        self.stdout.write("Scanning database for active file references...")
        active_identifiers = get_active_db_identifiers()
        self.stdout.write(f"Found {len(active_identifiers)} active media references in database.")

        # 2. Fetch remote assets from Cloudinary
        self.stdout.write("Querying Cloudinary assets...")
        orphans = []
        skipped_recent = 0
        total_scanned = 0
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=min_age_hours)

        try:
            # Query uploaded resources across types (image, raw, video)
            for resource_type in ['image', 'raw', 'video']:
                result = cloudinary.api.resources(
                    type="upload",
                    resource_type=resource_type,
                    max_results=500
                )
                resources = result.get('resources', [])
                total_scanned += len(resources)

                for res in resources:
                    public_id = res.get('public_id', '')
                    norm_id = normalize_cloudinary_ref(public_id).lower()
                    root_id, _ = os.path.splitext(norm_id)

                    # Check grace period (created_at)
                    created_at_str = res.get('created_at', '')
                    if created_at_str:
                        try:
                            # Cloudinary timestamps: "2026-09-30T10:20:30Z"
                            created_dt = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                            if created_dt > cutoff_time:
                                skipped_recent += 1
                                continue
                        except Exception:
                            pass

                    # Check if referenced in database
                    is_active = (norm_id in active_identifiers) or (root_id in active_identifiers)
                    if not is_active:
                        orphans.append({
                            'public_id': public_id,
                            'resource_type': resource_type,
                            'format': res.get('format', ''),
                            'bytes': res.get('bytes', 0),
                            'created_at': created_at_str,
                        })

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error querying Cloudinary API: {str(e)}"))
            logger.warning(f"Cloudinary API query failed: {e}")
            return

        self.stdout.write(f"Cloudinary assets scanned: {total_scanned}")
        self.stdout.write(f"Recent assets skipped (< {min_age_hours}h): {skipped_recent}")
        self.stdout.write(f"Orphaned assets identified: {len(orphans)}")

        if not orphans:
            self.stdout.write(self.style.SUCCESS("No orphaned assets found. Cloudinary storage is clean!"))
            return

        # List first 10 orphans
        self.stdout.write("\nSample identified orphan assets:")
        for o in orphans[:10]:
            self.stdout.write(f" - [{o['resource_type']}] {o['public_id']} ({o['bytes']} bytes, created: {o['created_at']})")
        if len(orphans) > 10:
            self.stdout.write(f" ... and {len(orphans) - 10} more.")

        # 3. Handle Deletion or Dry Run
        if not apply_mode:
            self.stdout.write(self.style.NOTICE(
                f"\nDRY RUN COMPLETE: {len(orphans)} orphaned file(s) would be deleted.\n"
                f"To delete up to {max_delete} file(s), run:\n"
                f"  python manage.py cloudinary_orphans --apply --confirm=DELETE"
            ))
            return

        # Confirmation check for --apply
        if confirm_str != "DELETE":
            if sys.stdin.isatty():
                response = input("Type 'DELETE' to confirm deletion of orphaned assets: ").strip()
                if response != "DELETE":
                    self.stdout.write(self.style.ERROR("Confirmation failed. Aborting."))
                    return
            else:
                self.stdout.write(self.style.ERROR("Confirmation failed: --confirm=DELETE required when running non-interactively."))
                return

        to_delete = orphans[:max_delete]
        deleted_count = 0
        failed_count = 0

        self.stdout.write(f"\nDeleting {len(to_delete)} orphaned assets from Cloudinary...")
        for item in to_delete:
            try:
                res = cloudinary.uploader.destroy(item['public_id'], resource_type=item['resource_type'])
                if res.get('result') in ['ok', 'not found']:
                    deleted_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                logger.error(f"Failed to delete Cloudinary orphan {item['public_id']}: {e}")
                failed_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully deleted {deleted_count} orphaned asset(s) from Cloudinary. "
            f"Failed: {failed_count}."
        ))
