import os
import logging
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Q
from users.models import BroadcastMessage, StudentProfile, Notification, BroadcastAttachment, StudentAchievement
from users.email_service import send_html_email

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Hardened scheduled broadcast execution system with standardized logging"

    def handle(self, *args, **kwargs):
        start_time = time.time()
        logger.info("COMMAND START: run_scheduled_broadcasts started processing.")

        # 1. PROCESS ONLY VALID RECORDS
        candidates = BroadcastMessage.objects.filter(
            status="scheduled",
            send_at__lte=timezone.now(),
            is_draft=False
        ).order_by('send_at')

        total_found = candidates.count()
        if total_found == 0:
            logger.info("COMMAND END: No due broadcasts found.")
            return

        processed_count = 0
        success_count = 0
        failed_count = 0
        skipped_count = 0

        for broadcast_id in candidates.values_list('id', flat=True):
            with transaction.atomic():
                broadcast = BroadcastMessage.objects.select_for_update(skip_locked=True).filter(
                    id=broadcast_id, 
                    status="scheduled"
                ).first()

                if not broadcast:
                    skipped_count += 1
                    continue

                processed_count += 1
                logger.info(f"PROCESSING: Broadcast ID {broadcast.id} - '{broadcast.subject}'")

                try:
                    broadcast.status = "processing"
                    broadcast.save(update_fields=["status"])

                    # Resolve recipients
                    recipient_qs = User.objects.none()
                    target_group = broadcast.target_group
                    selected_floors = broadcast.floor.split(",") if broadcast.floor else []
                    selected_batches = broadcast.batch.split(",") if broadcast.batch else []

                    if target_group == "everyone":
                        recipient_qs = User.objects.filter(Q(profile__isnull=False) | Q(achievements__isnull=False))
                    elif target_group == "all_students":
                        recipient_qs = User.objects.filter(profile__isnull=False)
                    elif target_group in ["library_students", "library"]:
                        recipient_qs = User.objects.filter(profile__service_type="Library")
                        if selected_floors:
                            recipient_qs = recipient_qs.filter(profile__seat__floor__in=selected_floors)
                    elif target_group in ["coaching_students", "coaching"]:
                        recipient_qs = User.objects.filter(profile__service_type="Coaching")
                        if selected_batches:
                            recipient_qs = recipient_qs.filter(profile__batch__in=selected_batches)
                    elif target_group == "alumni":
                        recipient_qs = User.objects.filter(achievements__isnull=False)
                    elif target_group in ["individual_selection", "individuals"]:
                        if broadcast.selected_ids:
                            recipient_qs = User.objects.filter(id__in=broadcast.selected_ids)

                    users = list(recipient_qs.filter(is_staff=False).distinct())
                    
                    if not users:
                        logger.warning(f"SKIPPED: No recipients found for Broadcast ID {broadcast.id}")
                        broadcast.status = "sent"
                        broadcast.is_sent = True
                        broadcast.save(update_fields=["status", "is_sent"])
                        success_count += 1
                        continue

                    # Attachment Safety
                    attachment_links = []
                    for att in broadcast.attachments.all():
                        attachment_links.append({
                            "name": os.path.basename(att.file.name),
                            "url": f"{settings.SITE_URL}{att.file.url}"
                        })

                    failed_ids = []
                    for user in users:
                        Notification.objects.create(
                            user=user,
                            title=broadcast.subject,
                            message=broadcast.message,
                            category="general",
                            is_read=False
                        )

                        if broadcast.send_email and user.email:
                            try:
                                send_html_email(
                                    subject=broadcast.subject,
                                    to_email=user.email,
                                    template="emails/broadcast_email.html",
                                    context={
                                        "subject": broadcast.subject,
                                        "message": broadcast.message,
                                        "teacher_name": broadcast.sender.get_full_name() or broadcast.sender.username,
                                        "dashboard_url": f"{settings.SITE_URL}/student/dashboard/",
                                        "attachment_links": attachment_links,
                                    },
                                    fail_silently=False,
                                )
                            except Exception as e:
                                logger.warning(f"EMAIL ERROR: Failed for {user.username} (ID {user.id}): {str(e)}")
                                failed_ids.append(user.id)

                    if broadcast.send_whatsapp:
                        from users.notifications import send_broadcast_whatsapp
                        whatsapp_targets = []
                        for user in users:
                            if hasattr(user, 'profile'):
                                whatsapp_targets.append(user.profile)
                            else:
                                ach = StudentAchievement.objects.filter(user=user).first()
                                if ach:
                                    whatsapp_targets.append(ach)
                        if whatsapp_targets:
                            banner_img_url = broadcast.banner_image.url if broadcast.banner_image else None
                            send_broadcast_whatsapp(whatsapp_targets, broadcast.subject, broadcast.message, banner_image_url=banner_img_url, buttons=broadcast.banner_buttons)

                    broadcast.status = "sent"
                    broadcast.is_sent = True
                    broadcast.failed_user_ids = failed_ids
                    broadcast.save(update_fields=["status", "is_sent", "failed_user_ids"])
                    
                    success_count += 1
                    logger.info(f"SUCCESS: Broadcast ID {broadcast.id} sent to {len(users)} users.")

                except Exception as e:
                    logger.error(f"FATAL ERROR: Processing Broadcast ID {broadcast.id} failed.", exc_info=True)
                    broadcast.status = "failed"
                    broadcast.is_sent = False
                    broadcast.save(update_fields=["status", "is_sent"])
                    failed_count += 1

        duration = time.time() - start_time
        logger.info(
            f"COMMAND END: run_scheduled_broadcasts completed in {duration:.2f}s. "
            f"Found: {total_found}, Processed: {processed_count}, Success: {success_count}, Failed: {failed_count}, Skipped: {skipped_count}"
        )
