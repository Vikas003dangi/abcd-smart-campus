import datetime
import logging
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.urls import reverse
from users.models import StudentProfile, Notification
from users import notifications

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Sends fee reminders strictly driven by student.fee_expiry_date with standardized logging.'

    def handle(self, *args, **options):
        start_time = time.time()
        today = timezone.localtime(timezone.now()).date()
        logger.info(f"COMMAND START: send_fee_reminders started for {today}.")
        
        students = StudentProfile.objects.filter(status='admitted').select_related('user', 'seat')
        
        from django.contrib.auth import get_user_model
        User = get_user_model()
        staff_users = list(User.objects.filter(is_staff=True, is_active=True))
        
        total_checked = students.count()
        sent_count = 0
        skipped_count = 0
        already_reminded_count = 0
        failed_count = 0
        
        for student in students:
            try:
                result = self.process_student_reminder(student, today, staff_users)
                
                if result == "sent":
                    sent_count += 1
                elif result == "already_reminded":
                    already_reminded_count += 1
                elif result == "skipped":
                    skipped_count += 1
                elif result == "failed":
                    failed_count += 1
            except Exception:
                logger.error(f"FATAL ERROR: Unexpected failure processing {student.full_name} (ID: {student.id})", exc_info=True)
                failed_count += 1

        duration = time.time() - start_time
        logger.info(
            f"COMMAND END: send_fee_reminders completed in {duration:.2f}s. "
            f"Checked: {total_checked}, Sent: {sent_count}, Already Reminded: {already_reminded_count}, Skipped: {skipped_count}, Failed: {failed_count}"
        )

    def process_student_reminder(self, student, today, staff_users):
        """
        Processes reminders for a student. For 'Both' dual-service students,
        coaching and library fee tracks are evaluated independently.
        Single-service students are evaluated against their respective service expiry.
        """
        tracks = []
        if student.service_type == 'Both':
            if student.coaching_fee_expiry_date:
                tracks.append(('coaching', student.coaching_fee_expiry_date))
            if student.library_fee_expiry_date:
                tracks.append(('library', student.library_fee_expiry_date))
        elif student.service_type == 'Coaching':
            exp = student.coaching_fee_expiry_date or student.fee_expiry_date
            if exp:
                tracks.append(('coaching', exp))
        else:
            exp = student.library_fee_expiry_date or student.fee_expiry_date
            if exp:
                tracks.append(('library', exp))

        if not tracks:
            # Silent cleanup for students with no expiry
            Notification.objects.filter(
                user=student.user,
                category="fee",
                meta__reminder_type__in=["pre_10", "pre_5", "first_day", "warning_1day", "recurring_3day"]
            ).delete()
            return "skipped"

        results = []
        cooldown_period = timezone.now() - datetime.timedelta(hours=24)

        for service, expiry in tracks:
            reminder_type = None
            if today == expiry - datetime.timedelta(days=10):
                reminder_type = "pre_10"
            elif today == expiry - datetime.timedelta(days=5):
                reminder_type = "pre_5"
            elif today == expiry:
                reminder_type = "first_day"
            elif today == expiry + datetime.timedelta(days=1):
                reminder_type = "warning_1day"
            elif today > expiry:
                days_overdue = (today - expiry).days
                if days_overdue > 1 and days_overdue % 3 == 0:
                    reminder_type = "recurring_3day"

            if not reminder_type:
                results.append("skipped")
                continue

            # Service-specific cooldown check to prevent duplicates
            recent_notification = Notification.objects.filter(
                user=student.user,
                category="fee",
                meta__reminder_type=reminder_type,
                meta__service=service,
                created_at__gte=cooldown_period
            ).exists()

            if recent_notification:
                logger.info(f"COOLDOWN: {student.full_name} ({service}) already reminded ({reminder_type}) within 24h.")
                results.append("already_reminded")
                continue

            try:
                service_details = notifications.get_student_service_details(student, service=service)
                month_year = expiry.strftime("%B %Y")
                formatted_expiry_date = expiry.strftime("%d %b %Y")

                # Channel Specific Dispatch
                if reminder_type == "pre_10":
                    notifications.send_fee_reminder_email(student, "pre_10", month_year, service=service)
                elif reminder_type == "pre_5":
                    notifications.send_fee_reminder_whatsapp(student, "pre_5", formatted_expiry_date, service=service)
                elif reminder_type == "first_day":
                    notifications.send_fee_reminder_email(student, "first_day", month_year, service=service)
                elif reminder_type == "warning_1day":
                    notifications.send_fee_reminder_whatsapp(student, "warning_1day", formatted_expiry_date, service=service)
                elif reminder_type == "recurring_3day":
                    notifications.send_fee_reminder_email(student, "recurring_3day", month_year, service=service)

                # Student In-App Notification
                if reminder_type == "pre_10":
                    status_text = "due in 10 days"
                elif reminder_type == "pre_5":
                    status_text = "due in 5 days"
                elif reminder_type == "first_day":
                    status_text = "due today"
                else:
                    status_text = "overdue"

                svc_label = service.capitalize() if student.service_type == 'Both' else ""
                notif_title = f"{svc_label} Fee Reminder ({reminder_type})".strip()
                student_message = f"Your fee for {service_details} ({month_year}) is {status_text}."

                notifications.create_notification(
                    user=student.user,
                    title=notif_title,
                    message=student_message,
                    link=reverse('users:student_dashboard'),
                    category="fee",
                    meta={
                        "reminder_type": reminder_type,
                        "student_id": student.id,
                        "service": service,
                        "service_details": service_details,
                        "expiry_date": str(expiry)
                    }
                )

                # Teacher Notification (one per service)
                teacher_notified_recently = Notification.objects.filter(
                    category="fee_teacher",
                    meta__student_id=student.id,
                    meta__service=service,
                    meta__reminder_type=reminder_type,
                    created_at__gte=cooldown_period
                ).exists()

                if not teacher_notified_recently:
                    if reminder_type in ("pre_10", "pre_5"):
                        teacher_status = "Fee expires soon"
                    elif reminder_type == "first_day":
                        teacher_status = "Fee expires today"
                    else:
                        days_overdue = (today - expiry).days
                        if days_overdue == 1:
                            teacher_status = "Fee expired today"
                        else:
                            teacher_status = f"Fee overdue by {days_overdue} days" if days_overdue > 0 else "Fee overdue"

                    teacher_title = f"Fee Alert: {student.full_name} ({service.capitalize()})" if student.service_type == 'Both' else f"Fee Alert: {student.full_name}"
                    teacher_message = f"{teacher_status} ({service_details})"

                    for staff in staff_users:
                        notifications.create_notification(
                            user=staff,
                            title=teacher_title,
                            message=teacher_message,
                            link=reverse('users:student_progress') + f"?student_id={student.id}",
                            category="fee_teacher",
                            meta={
                                "student_id": student.id,
                                "student_name": student.full_name,
                                "mobile": student.mobile_number,
                                "service": service,
                                "service_details": service_details,
                                "expiry_date": str(expiry),
                                "reminder_type": reminder_type
                            }
                        )

                logger.info(f"SENT: Fee reminder ({reminder_type} - {service}) to {student.full_name}")
                results.append("sent")

            except Exception as e:
                logger.error(f"FAILURE: Could not send {service} reminder to {student.full_name} (ID: {student.id}): {str(e)}")
                results.append("failed")

        if "sent" in results:
            return "sent"
        if "failed" in results:
            return "failed"
        if "already_reminded" in results:
            return "already_reminded"
        return "skipped"