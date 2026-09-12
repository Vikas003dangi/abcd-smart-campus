# users/notifications.py
import re, json, requests, logging
from pywebpush import webpush
from django.conf import settings
from .models import PushSubscription
from users.email_service import send_html_email
from django.urls import reverse
from django.utils.timezone import now, localdate

logger = logging.getLogger(__name__)

# --- UPDATED Helper function to work with the NEW Seat model ---
def get_student_service_details(student):
    """Returns a detailed string of the student's service for messages."""
    if student.service_type == 'Coaching':
        batch_name = student.get_batch_display()
        return f"{batch_name} coaching"
    elif student.service_type == 'Library':
        # Check if the student has a seat assigned
        if hasattr(student, 'seat') and student.seat:
            seat = student.seat
            floor_name = seat.floor
            seat_num = f" seat number {seat.seat_number}"
            return f"{floor_name} library{seat_num}"
        else:
            # Student is a library student but no seat is assigned yet
            return "Library"
    return "N/A"


def sanitize_whatsapp_number(phone):
    """
    Sanitizes phone numbers for Meta API: 
    - Removes spaces, dashes, +, and non-digits
    - Strips leading 0 (e.g. 09827662450 -> 9827662450) or 00 prefix
    - Ensures 91 prefix without doubling it (standard 12-digit Indian format)
    """
    if not phone:
        return None
    
    # Extract only digits
    digits = "".join(re.findall(r'\d+', str(phone)))
    
    # Strip international 00 prefix
    if digits.startswith("00"):
        digits = digits[2:]
        
    # Strip single leading zero (common in Indian domestic mobile input)
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    
    # Standard 10-digit Indian mobile -> prepend 91
    if len(digits) == 10:
        return f"91{digits}"
    elif len(digits) == 12 and digits.startswith("91"):
        return digits
    
    return digits


def has_whatsapp_configured():
    """Checks if Meta WhatsApp Cloud API credentials are configured in settings."""
    return bool(getattr(settings, 'WHATSAPP_API_TOKEN', None) and getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', None))


# --- FEE RECEIPT WHATSAPP (DOCUMENT API) ---
def send_fee_receipt_whatsapp(student, transaction, pdf_content):
    """
    Sends the fee receipt PDF via Meta WhatsApp Document API.
    Uses 'fee_receipt_v2' template with document header parameter.
    Fallback to direct document message if template is pending.
    """
    if not has_whatsapp_configured():
        logger.info("WhatsApp Dispatch SKIPPED: Meta Cloud API credentials not configured.")
        return

    raw_number = getattr(student, 'whatsapp_number', None) or getattr(student, 'mobile_number', None)
    clean_number = sanitize_whatsapp_number(raw_number)

    # STRICT Indian Phone Validation (91 prefix + 10 digits = 12 total)
    if not clean_number or len(clean_number) != 12 or not clean_number.startswith("91"):
        logger.warning(f"WhatsApp Dispatch SKIPPED: Invalid Indian format '{clean_number}' for {student.full_name} (Raw: {raw_number})")
        return

    media_id = None
    try:
        # Step 1: Upload PDF to Meta Media Endpoint
        upload_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/media"
        headers = {"Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}"}
        
        logger.info(f"WhatsApp Receipt UPLOAD START: {student.full_name} (Receipt: {transaction.receipt_number})")
        
        files = {
            'file': (f"Fee_Receipt_{transaction.receipt_number}.pdf", pdf_content, 'application/pdf'),
        }
        data = {
            'messaging_product': 'whatsapp',
            'type': 'document'
        }
        
        upload_response = requests.post(upload_url, headers=headers, data=data, files=files, timeout=20)
        upload_response.raise_for_status()
        media_id = upload_response.json().get('id')
        
        if not media_id:
            logger.error(f"WhatsApp Upload Error: No media_id returned for {student.full_name}")
            return
            
        logger.info(f"WhatsApp Receipt UPLOAD SUCCESS: media_id={media_id}")

        # Step 2: Send Document Message using template fee_receipt_v2
        send_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers_send = {
            "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}",
            "Content-Type": "application/json"
        }
        
        raw_service = get_student_service_details(student)
        service_details = str(raw_service).replace('\n', ' ').strip()
        amount_str = str(getattr(transaction, 'amount_paid', 0))
        clean_receipt_no = str(transaction.receipt_number).replace('/', '_')

        # Payload: Meta Template fee_receipt_v2
        payload = {
            "messaging_product": "whatsapp",
            "to": clean_number,
            "type": "template",
            "template": {
                "name": "fee_receipt_v2",
                "language": {"code": "en_US"},
                "components": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "document",
                                "document": {
                                    "id": media_id,
                                    "filename": f"Fee_Receipt_{clean_receipt_no}.pdf"
                                }
                            }
                        ]
                    },
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": student.full_name},
                            {"type": "text", "text": amount_str},
                            {"type": "text", "text": service_details},
                            {"type": "text", "text": clean_receipt_no}
                        ]
                    }
                ]
            }
        }
        
        send_response = requests.post(send_url, headers=headers_send, json=payload, timeout=20)
        if send_response.status_code != 200:
            # Fallback to direct document message if template is pending approval
            logger.warning(f"fee_receipt_v2 template dispatch returned {send_response.status_code} ({send_response.text}), trying direct document dispatch...")
            first_name = student.user.first_name if hasattr(student, 'user') and student.user and student.user.first_name else student.full_name.split()[0]
            caption = (
                f"Dear {first_name},\n"
                f"Your fee payment of Rs. {amount_str} for {service_details} has been submitted successfully at ABCD Coaching & Library.\n"
                f"Receipt No: {transaction.receipt_number}\n\n"
                f"Please download the attached receipt for complete details.\n\n"
                f"Thank You\n~ Team ABCD"
            )
            fallback_payload = {
                "messaging_product": "whatsapp",
                "to": clean_number,
                "type": "document",
                "document": {
                    "id": media_id,
                    "filename": f"Fee_Receipt_{transaction.receipt_number}.pdf",
                    "caption": caption
                }
            }
            send_response = requests.post(send_url, headers=headers_send, json=fallback_payload, timeout=20)

        if send_response.status_code == 200:
            transaction.whatsapp_sent = True
            transaction.save(update_fields=['whatsapp_sent'])
            logger.info(f"WhatsApp Receipt MESSAGE SENT & RECORDED: {student.full_name} to {clean_number} (Receipt: {transaction.receipt_number})")
        else:
            logger.error(f"WhatsApp Receipt MESSAGE FAILED for {student.full_name} ({clean_number}). Meta Response ({send_response.status_code}): {send_response.text}")

    except Exception as e:
        logger.exception(f"WhatsApp Receipt WORKFLOW FAILED for {student.full_name} (Receipt: {transaction.receipt_number}): {str(e)}")



# --- FEES CONSOLIDATED NOTIFICATION FUNCTION (DEPRECATED) ---
def send_all_consolidated_notifications(teacher_name, student, year, details_list):
    """
    DEPRECATED: This function is no longer used for fee submission.
    Submission communication is now handled via PDF receipts in views.py.
    """
    pass


# approved mail to students

def send_admission_approval_notifications(student, seat=None):
    """
    Sends admission approval notifications asynchronously in a background thread.
    Accepts an optional 'seat' object.
    """
    import threading
    
    def _send_notifs():
        try:
            # Get the service details (which will include the seat info if it exists)
            service_details = get_student_service_details(student)
            
            if student.user.email:
                send_approval_email(student, seat, service_details)
            
            # Send WhatsApp regardless of email presence
            send_approval_whatsapp(student, service_details)
        except Exception as e:
            logger.error(f"Error in send_admission_approval_notifications thread: {e}")

    thread = threading.Thread(target=_send_notifs)
    thread.daemon = True
    thread.start()


def send_approval_email(student, seat, service_details):
    """
    Sends a beautifully designed admission approval email to the student.
    Uses student profile email if updated/specified, falling back to user.email.
    """
    from .utils import get_user_notification_email
    target_email = get_user_notification_email(student)
    if not target_email:
        logger.warning(f"Cannot send admission approval email to {student.full_name}, no email found.")
        return

    try:
        send_html_email(
            subject="Admission Approved at ABCD",
            to_email=target_email,
            template="emails/admission_approved.html",
            context={
                "student": student,
                "seat": seat,
                "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
            },
            fail_silently=False,
        )

        logger.info(f"Approval email sent to {student.full_name} ({target_email})")

    except Exception as e:
        logger.error(f"Failed to send approval email: {e}")


def send_approval_whatsapp(student, service_details):
    """Sends an admission approval WhatsApp message to the student using template admission_approved_v2."""
    if not has_whatsapp_configured():
        logger.info("WhatsApp Dispatch SKIPPED: Meta Cloud API credentials not configured.")
        return

    phone = getattr(student, 'whatsapp_number', None) or getattr(student, 'mobile_number', None)
    clean_number = sanitize_whatsapp_number(phone)
    if not clean_number:
        return
    try:
        whatsapp_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = { "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}", "Content-Type": "application/json" }

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_number,
            "type": "template",
            "template": {
                "name": "admission_approved_v2",
                "language": {"code": "en_US"},
                "components": [{"type": "body", "parameters": [
                    {"type": "text", "text": student.full_name},
                    {"type": "text", "text": str(service_details)[:100]},
                ]}]
            }
        }
        res = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
        if res.status_code == 200:
            logger.info(f"Approval WhatsApp sent successfully to {student.full_name} ({clean_number}).")
        else:
            logger.error(f"Failed to send Approval WhatsApp to {student.full_name} ({clean_number}). Meta Response ({res.status_code}): {res.text}")
    except Exception as e:
        logger.error(f"Error sending approval WhatsApp: {e}")


def send_alumni_approval_whatsapp(student_or_ach, achievement_title):
    """Sends WhatsApp message to approved alumni using template alumni_approval_v2 (Utility category)."""
    if not has_whatsapp_configured():
        logger.info("WhatsApp Dispatch SKIPPED: Meta Cloud API credentials not configured.")
        return

    phone = getattr(student_or_ach, 'whatsapp_number', None) or getattr(student_or_ach, 'mobile_number', None)
    clean_number = sanitize_whatsapp_number(phone)
    if not clean_number:
        return
    full_name = getattr(student_or_ach, 'full_name', '') or f"{getattr(student_or_ach, 'first_name', '')} {getattr(student_or_ach, 'last_name', '')}".strip()
    try:
        whatsapp_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = { "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}", "Content-Type": "application/json" }

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_number,
            "type": "template",
            "template": {
                "name": "alumni_approval_v2",
                "language": {"code": "en_US"},
                "components": [{"type": "body", "parameters": [
                    {"type": "text", "text": full_name},
                    {"type": "text", "text": achievement_title or "Achievement"},
                ]}]
            }
        }
        res = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
        if res.status_code != 200:
            # Fallback to alumni_achievement_approved if v2 is pending
            payload["template"]["name"] = "alumni_achievement_approved"
            requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
        logger.info(f"Alumni Achievement Approval WhatsApp sent to {full_name} (Status: {res.status_code}).")
    except Exception as e:
        logger.error(f"Error sending Alumni Achievement WhatsApp: {e}")



def send_alumni_approval_email(student_or_ach, achievement_title):
    """Sends an email notification to approved alumni."""
    from .utils import get_user_notification_email
    email = getattr(student_or_ach, 'email', None) or get_user_notification_email(student_or_ach)
    if not email:
        return
    try:
        send_html_email(
            subject="Congratulations! Your Achievement Has Been Approved",
            to_email=email,
            template="emails/admission_approved.html",
            context={
                "title": "Achievement Approved",
                "student": student_or_ach,
                "dashboard_url": f"{settings.SITE_URL}{reverse('users:alumni_dashboard')}",
            },
            fail_silently=True,
        )
        logger.info(f"Alumni approval email sent to {email}.")
    except Exception as e:
        logger.error(f"Failed to send alumni approval email: {e}")


# --- SEAT CHANGE & HOLD STATUS NOTIFICATIONS ---

def send_seat_change_approval(student, seat):
    """
    Sends a seat change approval email to the student (HTML).
    """
    from .utils import get_user_notification_email
    target_email = get_user_notification_email(student)
    try:
        if target_email:
            send_html_email(
                subject="Your Seat Change is Approved",
                to_email=target_email,
                template="emails/seat_update.html",
                context={
                    "title": "Seat Change Approved",
                    "student": student,
                    "update_type": "seat_change_approved",
                    "seat": seat,
                    "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                },
                fail_silently=False,
            )
            logger.info(f"Seat change approval email sent to {student.full_name} ({target_email})")
        else:
            logger.warning(f"Cannot send email to {student.full_name}, no email on file.")

    except Exception as e:
        logger.error(f"Failed to send seat change approval email: {e}")


def send_hold_request_status(student, seat, status):
    """Sends a hold request status (approved/denied) email to the student."""
    from .utils import get_user_notification_email
    target_email = get_user_notification_email(student)
    
    if status == "approved":
        title = "Seat Hold Approved"
        update_type = "hold_approved"
        hold_period = (
            f"{seat.hold_start_date.strftime('%d %b %Y')} "
            f"to {seat.hold_end_date.strftime('%d %b %Y')}"
        )
    else:
        title = "Seat Hold Request Denied"
        update_type = "hold_denied"
        hold_period = None

    try:
        if target_email:
            send_html_email(
                subject=f"{title}",
                to_email=target_email,
                template="emails/seat_update.html",
                context={
                    "title": title,
                    "student": student,
                    "update_type": update_type,
                    "seat": seat,
                    "hold_period": hold_period,
                    "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                },
                fail_silently=False,
            )

            logger.info(f"Seat hold {status} email sent to {student.full_name} ({target_email})")
        else:
            logger.warning(f"Cannot send email to {student.full_name}, no email on file.")

    except Exception as e:
        logger.error(f"Failed to send seat hold status email: {e}")


# --- FEE REMINDER NOTIFICATIONS ---
def send_fee_reminder_email(student, reminder_type, date_text):
    """
    Sends fee reminder email.
    Types: 'pre_10' (10 days advance), 'first_day' (due today), 'recurring_3day' (every 3 days overdue).
    """
    from .utils import get_user_notification_email
    target_email = get_user_notification_email(student)
    if not target_email:
        return

    service_details = get_student_service_details(student)

    if reminder_type == "pre_10":
        subject = "Your ABCD Fee is Due in 10 Days"
    elif reminder_type == "first_day":
        subject = "Your ABCD Fee is Due Today"
    else:  # "recurring_3day"
        subject = "URGENT: Your ABCD Fee is Overdue"

    try:
        send_html_email(
            subject=subject,
            to_email=target_email,
            template="emails/fee_notification.html",
            context={
                "title": subject,
                "student": student,
                "reminder_type": reminder_type,
                "service_details": service_details,
                "months_text": date_text,
                "date": localdate().strftime("%d %b %Y"),
                "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
            },
            fail_silently=False,
        )
        logger.info(f"Fee reminder email ({reminder_type}) sent to {student.full_name} ({target_email}).")
    except Exception as e:
        logger.error(f"Failed to send fee reminder email ({reminder_type}): {e}")


def send_fee_reminder_whatsapp(student, reminder_type, expiry_date_str):
    """
    Sends WhatsApp fee reminders strictly for:
    - 'pre_5': 5 days before expiry (Template: fee_reminder_5day)
    - 'warning_1day': 1 day after expiry warning (Template: fee_warning_overdue)
    """
    if not has_whatsapp_configured():
        logger.info("WhatsApp fee reminder SKIPPED: Meta Cloud API not configured.")
        return

    phone = getattr(student, 'whatsapp_number', None) or getattr(student, 'mobile_number', None)
    clean_number = sanitize_whatsapp_number(phone)
    if not clean_number:
        return

    service_details = get_student_service_details(student)

    if reminder_type == "pre_5":
        template_name = "fee_reminder_5day"
    elif reminder_type == "warning_1day":
        template_name = "fee_warning_overdue"
    else:
        return

    try:
        whatsapp_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = { "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}", "Content-Type": "application/json" }

        safe_student_name = (getattr(student, 'full_name', '') or "Student")[:90]
        safe_service = str(service_details)[:100]
        safe_expiry = str(expiry_date_str)[:50]

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en_US"},
                "components": [{"type": "body", "parameters": [
                    {"type": "text", "text": safe_student_name},
                    {"type": "text", "text": safe_service},
                    {"type": "text", "text": safe_expiry}
                ]}]
            }
        }
        res = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
        if res.status_code != 200:
            logger.warning(f"WhatsApp fee reminder template '{template_name}' error ({res.text})")
        else:
            logger.info(f"Sent WhatsApp fee reminder '{reminder_type}' to {safe_student_name}.")
    except Exception as e:
        logger.error(f"Error sending WhatsApp fee reminder ({reminder_type}): {e}")


def send_fee_reminder(student, reminder_type, new_month_name):
    """
    Backward-compatibility wrapper for legacy fee reminder calls.
    """
    if reminder_type == "pre":
        send_fee_reminder_email(student, "pre_10", new_month_name)
        send_fee_reminder_whatsapp(student, "pre_5", new_month_name)
    elif reminder_type == "first_day":
        send_fee_reminder_email(student, "first_day", new_month_name)
    else:
        send_fee_reminder_whatsapp(student, "warning_1day", new_month_name)
        send_fee_reminder_email(student, "recurring_3day", new_month_name)


def send_hold_warning_whatsapp_student(student, seat_details, teacher_phone="9827662450"):
    """
    Sends WhatsApp Hold Grace Period Warning to student using 'hold_warning_3day_student' template.
    Body params: {{1}} = student name, {{2}} = seat details, {{3}} = teacher phone number
    """
    if not has_whatsapp_configured():
        logger.info("WhatsApp student hold warning SKIPPED: Meta Cloud API not configured.")
        return

    phone = getattr(student, 'whatsapp_number', None) or getattr(student, 'mobile_number', None)
    clean_number = sanitize_whatsapp_number(phone)
    if not clean_number:
        return

    try:
        whatsapp_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = { "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}", "Content-Type": "application/json" }

        safe_student_name = (getattr(student, 'full_name', '') or "Student")[:90]
        safe_seat = str(seat_details)[:100]
        safe_phone = str(teacher_phone)[:30]

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_number,
            "type": "template",
            "template": {
                "name": "hold_warning_3day_student",
                "language": {"code": "en_US"},
                "components": [{"type": "body", "parameters": [
                    {"type": "text", "text": safe_student_name},
                    {"type": "text", "text": safe_seat},
                    {"type": "text", "text": safe_phone}
                ]}]
            }
        }
        res = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
        if res.status_code != 200:
            logger.warning(f"WhatsApp hold warning error for student {safe_student_name}: {res.text}")
        else:
            logger.info(f"Sent WhatsApp hold warning to student {safe_student_name}.")
    except Exception as e:
        logger.error(f"Error sending WhatsApp hold warning to student: {e}")


def send_hold_warning_whatsapp_teacher(teacher_user_or_phone, student_name, seat_details):
    """
    Sends WhatsApp Hold Info Alert to teacher using 'hold_warning_3day_teacher' template.
    Body params: {{1}} = student name, {{2}} = seat details
    Accepts either a User model instance or a direct phone number string (e.g. Sandeep Sir's phone).
    """
    if not has_whatsapp_configured():
        logger.info("WhatsApp teacher hold warning SKIPPED: Meta Cloud API not configured.")
        return

    if isinstance(teacher_user_or_phone, str) and teacher_user_or_phone.replace('+', '').isdigit():
        phone = teacher_user_or_phone
    else:
        # Check TeacherProfile, then StudentProfile, then username fallback
        t_prof = getattr(teacher_user_or_phone, 'teacher_profile', None)
        s_prof = getattr(teacher_user_or_phone, 'profile', None)
        phone = None
        if t_prof:
            raw_w = (getattr(t_prof, 'whatsapp_numbers', '') or '').strip()
            if raw_w:
                phone = [w.strip() for w in raw_w.split(',') if w.strip()][0]
            else:
                phone = getattr(t_prof, 'mobile_number', None)
        if not phone and s_prof:
            phone = getattr(s_prof, 'whatsapp_number', None) or getattr(s_prof, 'mobile_number', None)
        if not phone:
            phone = getattr(teacher_user_or_phone, 'username', None)

    clean_number = sanitize_whatsapp_number(phone)
    if not clean_number:
        return

    try:
        whatsapp_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
        headers = { "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}", "Content-Type": "application/json" }

        safe_student_name = str(student_name)[:90]
        safe_seat_details = str(seat_details)[:100]

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_number,
            "type": "template",
            "template": {
                "name": "hold_warning_3day_teacher",
                "language": {"code": "en_US"},
                "components": [{"type": "body", "parameters": [
                    {"type": "text", "text": safe_student_name},
                    {"type": "text", "text": safe_seat_details}
                ]}]
            }
        }
        teacher_label = getattr(teacher_user_or_phone, 'username', str(clean_number))
        res = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
        if res.status_code != 200:
            logger.warning(f"WhatsApp hold warning error for teacher {teacher_label}: {res.text}")
        else:
            logger.info(f"Sent WhatsApp hold warning to teacher {teacher_label}.")
    except Exception as e:
        logger.error(f"Error sending WhatsApp hold warning to teacher: {e}")


        


# dashboard_notifications for students
from .models import Notification

EMOJI_AND_SPECIAL_PATTERN = re.compile(
    r'[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff\u2b50\u200d\ufe0f\u2000-\u206f]'
)

def strip_emojis_and_pipes(text):
    """
    Strips pipe characters, emojis, and spam trigger symbols from notification strings.
    """
    if not text:
        return ""
    # Replace all pipe characters with a space or dash
    cleaned = re.sub(r'\s*\|\s*', ' - ', str(text))
    # Strip any leading branding prefixes like "ABCD - ", "Guidy - ", "ToDo - "
    cleaned = re.sub(r'^(?:ABCD\s*-\s*|Guidy\s*-\s*|ToDo\s*-\s*)+', '', cleaned, flags=re.IGNORECASE)
    # Remove all unicode emojis and special pictogram symbols
    cleaned = EMOJI_AND_SPECIAL_PATTERN.sub('', cleaned)
    # Normalize punctuation and whitespace
    cleaned = re.sub(r'[!?]{2,}', '!', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned

def format_push_title(raw_title, category=None, source=None):
    """
    Standardizes push notification and alert titles to clean, spam-safe branding rules.
    Avoids pipes '|' and emojis which trigger Chrome Android's on-device spam detection.
    """
    if not raw_title and not category and not source:
        return "ABCD Campus"

    raw_clean = strip_emojis_and_pipes(raw_title)
    cat_clean = str(category or "").strip().lower()
    src_clean = str(source or "").strip().lower()

    # Guidy check
    if src_clean == 'guidy' or cat_clean == 'guidy' or 'guidy' in raw_clean.lower():
        return "Guidy Assistant"

    # ToDo check
    if src_clean == 'todo' or cat_clean == 'todo' or 'todo' in raw_clean.lower():
        if cat_clean in ['alarm', 'reminder'] or 'alarm' in raw_clean.lower() or 'reminder' in raw_clean.lower():
            pass  # Fall through to alarm/reminder handling below
        else:
            return "To-Do Hub"

    # Alarm and Reminder checks: produce clean, non-spam titles like "Alarm: Math Quiz" or "Reminder: Math Quiz"
    if cat_clean in ['alarm', 'reminder'] or 'alarm' in raw_clean.lower() or 'reminder' in raw_clean.lower():
        # Remove redundant leading "Alarm:" or "Reminder:" words so we can format uniformly
        sub_title = re.sub(r'^(?:Alarm|Reminder)\s*[:-]\s*', '', raw_clean, flags=re.IGNORECASE).strip()
        prefix = "Alarm" if (cat_clean == 'alarm' or 'alarm' in raw_clean.lower()) else "Reminder"
        return f"{prefix}: {sub_title}" if sub_title else prefix

    # Specific topic checks
    lower_title = raw_clean.lower()
    if cat_clean in ['course', 'lecture', 'quiz'] or any(k in lower_title for k in ['course', 'lecture', 'material', 'quiz']):
        return "Course Update"
    if cat_clean in ['hold', 'seat', 'library'] or any(k in lower_title for k in ['seat', 'library', 'hold']):
        return "Library Seat"
    if cat_clean == 'broadcast' or 'broadcast' in lower_title:
        return "Campus Notice"
    if cat_clean in ['announcement', 'notice'] or any(k in lower_title for k in ['announcement', 'notice']):
        return "Announcement"
    if cat_clean in ['admission', 'enrollment'] or any(k in lower_title for k in ['admission', 'enrolled', 'enrollment']):
        return "Admission Notice"
    if cat_clean == 'complaint' or 'complaint' in lower_title:
        return "Complaint Update"
    if cat_clean in ['fee', 'payment', 'fee_teacher'] or any(k in lower_title for k in ['fee', 'payment', 'receipt']):
        return "Fee Receipt"

    # Clean text fallback
    if raw_clean:
        clean_words = raw_clean.strip(' -:;,.')
        words = clean_words.split()
        if words:
            return " ".join(words[:4]).title()

    return "ABCD Campus"


def create_notification(user, title, message, link=None, category="general", meta=None, sound=None, tag=None):
    if not user:
        return

    clean_message = strip_emojis_and_pipes(message) or "You have a new update."
    formatted_title = format_push_title(title, category=category)

    notif = Notification.objects.create(
        user=user,
        title=formatted_title,
        message=clean_message,
        link=link,
        category=category,
        meta=meta
    )

    # Determine default sound for alarm / reminder
    if not sound:
        cat_lower = (category or "").lower()
        title_lower = (title or "").lower()
        is_guidy = (cat_lower == 'guidy') or (tag and 'guidy' in str(tag).lower()) or ('/guidy' in (link or '').lower())
        is_todo = (isinstance(meta, dict) and meta.get('source') == 'todo') or ('/todo' in (link or '').lower())
        if is_guidy:
            sound = "/static/audio/receive.mp3"
        elif cat_lower == 'alarm' or 'alarm' in title_lower:
            sound = "/static/audio/alarm.mp3"
        elif cat_lower == 'reminder' or 'reminder' in title_lower:
            # Inside To-Do Hub reminder without alarm uses PWA.mp3; outside To-Do Hub uses alarms and reminders.mp3
            sound = "/static/audio/PWA.mp3" if is_todo else "/static/audio/alarms and reminders.mp3"
        else:
            sound = "/static/audio/PWA.mp3"

    # Send device push notification
    send_push(user, formatted_title, clean_message, url=link or "/", category=category, sound=sound, tag=tag, meta=meta)
    return notif
# ---------------------------------------------------------

# push notifications for students
def send_push(user, title, body, url="/", icon=None, badge=None, tag=None, sound=None, badge_count=None, category=None, source=None, meta=None):
    """
    Send browser/device push notification to all
    subscribed devices of the user with custom sound, vibration, and app badging.
    """
    if not user:
        return

    subscriptions = PushSubscription.objects.filter(user=user)
    if not subscriptions.exists():
        return

    formatted_title = format_push_title(title, category=category, source=source)
    clean_body = strip_emojis_and_pipes(body) or "You have a new update."

    cat_lower = (category or "").lower()
    src_lower = (source or "").lower()
    title_lower = (title or "").lower()
    tag_lower = (tag or "").lower()

    # Guidy messages are chat / assistant communication and must NEVER be treated as alarms or reminders
    is_guidy = (cat_lower == 'guidy' or src_lower == 'guidy' or tag_lower.startswith('guidy-') or '/guidy' in (url or '').lower())

    if is_guidy:
        is_alarm = False
        is_reminder = False
    else:
        meta_is_alarm = meta.get('is_alarm') if isinstance(meta, dict) else None
        if meta_is_alarm is not None:
            is_alarm = bool(meta_is_alarm)
        else:
            is_alarm = (cat_lower == 'alarm' or src_lower == 'alarm' or
                        'alarm' in title_lower or 'alarm' in tag_lower)

        is_reminder = (not is_alarm) and (cat_lower == 'reminder' or src_lower == 'reminder' or
                                           'reminder' in title_lower or 'reminder' in tag_lower)

    # Distinct sounds:
    # 1. Guidy chat: receive.mp3
    # 2. Inside To-Do Hub: alarm uses alarm.mp3, reminder without alarm uses PWA.mp3
    # 3. Outside To-Do Hub: reminder uses 'alarms and reminders.mp3'
    # 4. Standard general notification: PWA.mp3
    is_todo = (isinstance(meta, dict) and meta.get('source') == 'todo') or (src_lower == 'todo') or ('/todo' in (url or '').lower())
    if not sound:
        if is_guidy:
            sound = "/static/audio/receive.mp3"
        elif is_alarm:
            sound = "/static/audio/alarm.mp3"
        elif is_reminder:
            sound = "/static/audio/PWA.mp3" if is_todo else "/static/audio/alarms and reminders.mp3"
        else:
            sound = "/static/audio/PWA.mp3"

    # Calculate or get badge count (Guidy unread messages + active alerts)
    if badge_count is None:
        try:
            from users.views import get_guidy_badge_count
            badge_count = get_guidy_badge_count(user)
        except Exception:
            badge_count = 1

    task_id = meta.get('task_id') if isinstance(meta, dict) else None
    fallback_alarm_tag = f"abcd-reminder-{task_id}" if task_id else f"abcd-alarm-{user.id}"
    unique_tag = tag or (fallback_alarm_tag if (is_alarm or is_reminder) else "abcd-notification")

    payload = {
        "title": formatted_title,
        "body": clean_body,
        "url": url,
        "icon": icon or "/static/data/favicon/web-app-manifest-192x192.png",
        "badge": badge or "/static/data/favicon/favicon-96x96.png",
        "sound": sound,
        "badge_count": max(1, badge_count or 1),
        "tag": unique_tag,
        "category": category,
        "source": source,
        "is_alarm": is_alarm,
        "task_id": task_id,
    }

    from pywebpush import webpush, WebPushException

    # Deduplicate subscriptions: keep newest active subscriptions, avoid duplicate endpoints
    seen_endpoints = set()
    unique_subs = []
    for sub in subscriptions.order_by('-id'):
        if sub.endpoint and sub.endpoint not in seen_endpoints:
            seen_endpoints.add(sub.endpoint)
            unique_subs.append(sub)

    # Clean topic for RFC 8030 push collapsing (alphanumeric and dashes, max 32 chars)
    topic_header = re.sub(r'[^a-zA-Z0-9_-]', '-', str(unique_tag))[:32].strip('-')

    delivered = False
    for sub in unique_subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": sub.keys,
                },
                data=json.dumps(payload),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={
                    "sub": (
                        f"mailto:{str(getattr(settings, 'VAPID_CLAIM_EMAIL', 'abcd2013baq@gmail.com')).strip().strip('\'\"').removeprefix('mailto:')}"
                    )
                },
                headers={
                    "Urgency": "high" if is_alarm else "normal",
                    "Topic": topic_header or "abcd-alert"
                },
                ttl=86400,
                timeout=10
            )
            delivered = True
        except WebPushException as ex:
            logger.debug(f"Web push error for sub {sub.id}: {ex}")
            # Automatically prune dead or expired subscriptions (404/410)
            if ex.response is not None and ex.response.status_code in (404, 410):
                try:
                    sub.delete()
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Web push error for sub {sub.id}: {e}")

    return delivered


def send_broadcast_whatsapp(students, subject, message, banner_image_url=None, attachments=None, buttons=None):
    """
    Send broadcast/banner/document WhatsApp messages using Meta templates.
    Supports attached documents/files and formats clickable download links.
    """
    if not has_whatsapp_configured():
        logger.info("WhatsApp broadcast SKIPPED: Meta Cloud API not configured.")
        return

    from django.conf import settings
    import requests

    whatsapp_url = f"https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {settings.WHATSAPP_API_TOKEN}",
        "Content-Type": "application/json",
    }

    full_message = message or ""
    
    # Format document/media attachments if present
    if attachments and isinstance(attachments, list) and len(attachments) > 0:
        att_links = []
        for att in attachments:
            if isinstance(att, dict) and att.get('url'):
                name = att.get('name', 'Download Attachment')
                url = att.get('url')
                att_links.append(f"• {name}: {url}")
            elif isinstance(att, str):
                att_links.append(f"• Attachment: {att}")
        if att_links:
            full_message += "\n\nAttached Documents:\n" + "\n".join(att_links)

    if buttons and isinstance(buttons, list) and len(buttons) > 0:
        btn_links = "\n\nLinks:\n" + "\n".join([f"- {b.get('label', 'Link')}: {b.get('url', '')}" for b in buttons if b.get('url')])
        full_message += btn_links

    safe_subject = (subject or "Announcement")[:90]
    safe_message = full_message or "New Announcement"
    if len(safe_message) > 950:
        safe_message = safe_message[:945] + "..."

    # Ensure banner URL is an absolute http/https URL if provided
    valid_banner_url = None
    if banner_image_url and isinstance(banner_image_url, str):
        b_url = banner_image_url.strip()
        if not b_url.startswith(('http://', 'https://')):
            site_url = getattr(settings, 'SITE_URL', '').rstrip('/')
            b_url = f"{site_url}/{b_url.lstrip('/')}"
        if b_url.startswith(('http://', 'https://')):
            valid_banner_url = b_url

    for student in students:
        phone = getattr(student, "whatsapp_number", None) or getattr(student, "mobile_number", None)
        if not phone:
            continue
        
        clean_num = sanitize_whatsapp_number(phone)
        if not clean_num:
            continue

        try:
            sent_successfully = False
            if valid_banner_url:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": clean_num,
                    "type": "template",
                    "template": {
                        "name": "broadcast_banner",
                        "language": {"code": "en_US"},
                        "components": [
                            {
                                "type": "header",
                                "parameters": [{
                                    "type": "image",
                                    "image": {"link": valid_banner_url}
                                }]
                            },
                            {
                                "type": "body",
                                "parameters": [
                                    {"type": "text", "text": safe_subject},
                                    {"type": "text", "text": safe_message}
                                ]
                            }
                        ]
                    }
                }
                response = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
                if response.status_code == 200:
                    sent_successfully = True
                else:
                    logger.warning(f"WhatsApp broadcast_banner template failed ({response.text}); falling back to text message...")

            # Fallback to text template if no banner or banner failed
            if not sent_successfully:
                payload = {
                    "messaging_product": "whatsapp",
                    "to": clean_num,
                    "type": "template",
                    "template": {
                        "name": "broadcast_message",
                        "language": {"code": "en_US"},
                        "components": [{
                            "type": "body",
                            "parameters": [
                                {"type": "text", "text": safe_subject},
                                {"type": "text", "text": safe_message}
                            ]
                        }]
                    }
                }
                response = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
                if response.status_code != 200:
                    logger.warning(f"WhatsApp API error for {getattr(student, 'full_name', 'Student')}: {response.text}")

        except Exception as e:
            logger.error(f"Broadcast WhatsApp failed for {getattr(student, 'full_name', 'Student')}: {e}")


def send_seat_switch_approval_email(student, seat=None, shift=None):
    """Sends email when student seat/shift switch request is approved."""
    try:
        from .utils import get_user_notification_email
        email = get_user_notification_email(student)
        if email:
            send_html_email(
                subject="Your Seat / Shift Switch Request is Approved",
                to_email=email,
                template="emails/seat_update.html",
                context={
                    "title": "Seat / Shift Switch Approved",
                    "student": student,
                    "update_type": "switch_approved",
                    "seat": seat,
                    "shift": shift or getattr(student, 'shift', None),
                    "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                },
                fail_silently=True,
                run_async=True
            )
    except Exception as e:
        logger.error(f"Failed sending seat switch email: {e}")


def send_seat_rejection_email(student, seat=None, shift=None):
    """Sends email when student seat/shift switch or admission request is rejected/cancelled."""
    try:
        from .utils import get_user_notification_email
        email = get_user_notification_email(student)
        if email:
            send_html_email(
                subject="Update Regarding Your Seat / Shift Request",
                to_email=email,
                template="emails/seat_update.html",
                context={
                    "title": "Seat / Shift Request Update",
                    "student": student,
                    "update_type": "switch_rejected",
                    "seat": seat,
                    "shift": shift,
                    "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                },
                fail_silently=True,
                run_async=True
            )
    except Exception as e:
        logger.error(f"Failed sending seat rejection email: {e}")


def send_student_progress_email(student, topic, marks, total_marks):
    """Sends email to student when exam marks or performance records are added/updated."""
    try:
        from .utils import get_user_notification_email
        email = get_user_notification_email(student)
        if email:
            percentage = round((marks / total_marks) * 100, 1) if total_marks > 0 else 0
            custom_msg = f"Your performance marks for topic '{topic}' have been recorded: {marks} / {total_marks} ({percentage}%)."
            send_html_email(
                subject=f"Exam Progress Update: {topic}",
                to_email=email,
                template="emails/seat_update.html",
                context={
                    "title": "Exam Progress & Score Update",
                    "student": student,
                    "custom_text": custom_msg,
                    "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                },
                fail_silently=True,
                run_async=True
            )
    except Exception as e:
        logger.error(f"Failed sending progress email: {e}")


