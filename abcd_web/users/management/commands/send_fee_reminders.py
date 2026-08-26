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
        expiry = student.fee_expiry_date

        if expiry is None:
            # Silent cleanup for students with no expiry
            Notification.objects.filter(
                user=student.user,
                category="fee",
                meta__reminder_type__in=["pre", "first_day", "recurring"]
            ).delete()
            return "skipped"

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
            return "skipped"

        # Cooldown check
        cooldown_period = timezone.now() - datetime.timedelta(hours=24)
        recent_notification = Notification.objects.filter(
            user=student.user,
            category="fee",
            meta__reminder_type=reminder_type,
            created_at__gte=cooldown_period
        ).exists()

        if recent_notification:
            logger.info(f"COOLDOWN: {student.full_name} already reminded ({reminder_type}) within 24h.")
            return "already_reminded"

        try:
            service_details = notifications.get_student_service_details(student)
            month_year = expiry.strftime("%B %Y")
            formatted_expiry_date = expiry.strftime("%d %b %Y")
            
            # Channel Specific Dispatch
            if reminder_type == "pre_10":
                notifications.send_fee_reminder_email(student, "pre_10", month_year)
            elif reminder_type == "pre_5":
                notifications.send_fee_reminder_whatsapp(student, "pre_5", formatted_expiry_date)
            elif reminder_type == "first_day":
                notifications.send_fee_reminder_email(student, "first_day", month_year)
            elif reminder_type == "warning_1day":
                notifications.send_fee_reminder_whatsapp(student, "warning_1day", formatted_expiry_date)
            elif reminder_type == "recurring_3day":
                notifications.send_fee_reminder_email(student, "recurring_3day", month_year)
            
            # Student In-App Notification
            if reminder_type == "pre_10":
                status_text = "due in 10 days"
            elif reminder_type == "pre_5":
                status_text = "due in 5 days"
            elif reminder_type == "first_day":
                status_text = "due today"
            else:
                status_text = "overdue"

            student_message = f"Your fee for {service_details} ({month_year}) is {status_text}."

            notifications.create_notification(
                user=student.user,
                title=f"Fee Reminder ({reminder_type})",
                message=student_message,
                link=reverse('users:student_dashboard'),
                category="fee",
                meta={
                    "reminder_type": reminder_type, 
                    "student_id": student.id,
                    "service_details": service_details,
                    "expiry_date": str(expiry)
                }
            )

            
            # Teacher Notification
            teacher_notified_recently = Notification.objects.filter(
                category="fee_teacher",
                meta__student_id=student.id,
                meta__reminder_type=reminder_type,
                created_at__gte=cooldown_period
            ).exists()

            if not teacher_notified_recently:
                # Compact Status Messages for Teacher
                if reminder_type == "pre":
                    teacher_status = "Fee expires in 10 days"
                elif reminder_type == "first_day":
                    teacher_status = "Fee expires today"
                else:
                    days_overdue = (today - expiry).days
                    if days_overdue == 1:
                        teacher_status = "Fee expired today"
                    else:
                        teacher_status = f"Fee overdue by {days_overdue} days" if days_overdue > 0 else "Fee overdue"

                teacher_title = f"Fee Alert: {student.full_name}"
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
                            "service_details": service_details,
                            "expiry_date": str(expiry),
                            "reminder_type": reminder_type
                        }
                    )
            
            logger.info(f"SENT: Fee reminder ({reminder_type}) to {student.full_name}")
            return "sent"

        except Exception as e:
            logger.error(f"FAILURE: Could not send reminder to {student.full_name} (ID: {student.id}): {str(e)}")
            return "failed"