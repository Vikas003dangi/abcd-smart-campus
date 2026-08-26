import logging
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
from django.urls import reverse
from users.models import VisitorIntent, Seat, StudentProfile
from users.email_service import send_html_email
from users.utils import get_reminder_subject, INTENT_DELAYS

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Hardened visitor intent and seat availability reminder processor with standardized logging"

    def handle(self, *args, **options):
        start_time = time.time()
        logger.info("COMMAND START: process_visitor_reminders started.")
        
        now = timezone.now()
        relevance_window = now - timedelta(days=30) 

        stats = {
            "sent": 0,
            "skipped": 0,
            "failed": 0,
            "expired": 0,
        }

        # 1. PROCESS GENERAL INTENT REMINDERS
        general_intents = VisitorIntent.objects.filter(
            reminder_sent=False,
            resolved=False,
            intent_scope="general"
        ).select_related('user')

        for intent in general_intents:
            try:
                # Expiration check
                if intent.created_at < relevance_window:
                    intent.resolved = True
                    intent.save(update_fields=["resolved"])
                    stats["expired"] += 1
                    continue

                delay = INTENT_DELAYS.get(intent.intent_type)
                if not delay or intent.created_at + delay > now:
                    stats["skipped"] += 1
                    continue

                if StudentProfile.objects.filter(user=intent.user, status="admitted").exists():
                    intent.resolved = True
                    intent.save(update_fields=["resolved"])
                    stats["skipped"] += 1
                    continue

                subject = get_reminder_subject(intent)
                send_html_email(
                    subject=subject,
                    to_email=intent.user.email,
                    template="emails/visitor_reminder.html",
                    context={
                        "intent": intent,
                        "dashboard_url": settings.SITE_URL,
                        "action_url": f"{settings.SITE_URL}{reverse('users:admission_form')}",
                        "action_text": "Continue with ABCD",
                    },
                    fail_silently=False,
                )

                intent.mark_reminder_sent()
                stats["sent"] += 1
                logger.info(f"SENT: General reminder to {intent.user.email} for {intent.intent_type}")

            except Exception as e:
                logger.error(f"FAILURE: General intent ID {intent.id} failed: {str(e)}", exc_info=True)
                stats["failed"] += 1

        # 2. PROCESS SEAT AVAILABILITY REMINDERS
        SEAT_REMINDER_DELAY = timedelta(days=3)
        available_seats = Seat.objects.filter(
            status="available",
            available_since__isnull=False,
            available_since__lte=now - SEAT_REMINDER_DELAY
        )

        for seat in available_seats:
            specific_intents = VisitorIntent.objects.filter(
                intent_type="selected_library_seat",
                intent_scope="specific",
                reminder_sent=False,
                resolved=False,
                metadata__seat_number=str(seat.seat_number),
                metadata__floor=seat.floor
            ).select_related('user')

            for intent in specific_intents:
                try:
                    if StudentProfile.objects.filter(user=intent.user, status="admitted").exists():
                        intent.resolved = True
                        intent.save(update_fields=["resolved"])
                        stats["skipped"] += 1
                        continue

                    subject = "Your preferred library seat is now available"
                    send_html_email(
                        subject=subject,
                        to_email=intent.user.email,
                        template="emails/visitor_reminder.html",
                        context={
                            "intent": intent,
                            "seat": seat,
                            "dashboard_url": settings.SITE_URL,
                            "action_url": f"{settings.SITE_URL}{reverse('users:admission_form')}",
                            "action_text": "Confirm Your Seat",
                        },
                        fail_silently=False,
                    )

                    intent.mark_reminder_sent()
                    stats["sent"] += 1
                    logger.info(f"SENT: Seat availability reminder to {intent.user.email} for Seat {seat.seat_number}")

                except Exception as e:
                    logger.error(f"FAILURE: Seat availability intent ID {intent.id} failed: {str(e)}", exc_info=True)
                    stats["failed"] += 1

        duration = time.time() - start_time
        logger.info(
            f"COMMAND END: process_visitor_reminders completed in {duration:.2f}s. "
            f"Sent: {stats['sent']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}, Expired: {stats['expired']}"
        )