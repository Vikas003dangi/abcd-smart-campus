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
    - Ensures 91 prefix without doubling it
    """
    if not phone:
        return None
    
    # Extract only digits
    digits = "".join(re.findall(r'\d+', str(phone)))
    
    # Logic for 10-digit or 12-digit (with 91) numbers
    if len(digits) == 10:
        return f"91{digits}"
    elif len(digits) == 12 and digits.startswith("91"):
        return digits
    
    return digits

# --- FEE RECEIPT WHATSAPP (DOCUMENT API) ---
def send_fee_receipt_whatsapp(student, transaction, pdf_content):
    """
    Sends the fee receipt PDF via Meta WhatsApp Document API.
    Uses 'fee_receipt_v2' template with document header parameter.
    Fallback to direct document message if template is pending.
    """
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
                    {"type": "text", "text": service_details},
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

        payload = {
            "messaging_product": "whatsapp",
            "to": clean_number,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "en_US"},
                "components": [{"type": "body", "parameters": [
                    {"type": "text", "text": student.full_name},
                    {"type": "text", "text": service_details},
                    {"type": "text", "text": expiry_date_str}
                ]}]
            }
        }
        res = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
        if res.status_code != 200:
            logger.warning(f"WhatsApp fee reminder template '{template_name}' error ({res.text})")
        else:
            logger.info(f"Sent WhatsApp fee reminder '{reminder_type}' to {student.full_name}.")
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
                "name": "hold_warning_3day_student",
                "language": {"code": "en_US"},
                "components": [{"type": "body", "parameters": [
                    {"type": "text", "text": student.full_name},
                    {"type": "text", "text": seat_details},
                    {"type": "text", "text": teacher_phone}
                ]}]
            }
        }
        res = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
        if res.status_code != 200:
            logger.warning(f"WhatsApp hold warning error for student {student.full_name}: {res.text}")
        else:
            logger.info(f"Sent WhatsApp hold warning to student {student.full_name}.")
    except Exception as e:
        logger.error(f"Error sending WhatsApp hold warning to student: {e}")


def send_hold_warning_whatsapp_teacher(teacher_user, student_name, seat_details):
    """
    Sends WhatsApp Hold Info Alert to teacher using 'hold_warning_3day_teacher' template.
    Body params: {{1}} = student name, {{2}} = seat details
    """
    profile = getattr(teacher_user, 'profile', None)
    phone = getattr(profile, 'whatsapp_number', None) or getattr(profile, 'mobile_number', None) or getattr(teacher_user, 'username', None)
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
                "name": "hold_warning_3day_teacher",
                "language": {"code": "en_US"},
                "components": [{"type": "body", "parameters": [
                    {"type": "text", "text": student_name},
                    {"type": "text", "text": seat_details}
                ]}]
            }
        }
        res = requests.post(whatsapp_url, headers=headers, json=payload, timeout=15)
        if res.status_code != 200:
            logger.warning(f"WhatsApp hold warning error for teacher {teacher_user.username}: {res.text}")
        else:
            logger.info(f"Sent WhatsApp hold warning to teacher {teacher_user.username}.")
    except Exception as e:
        logger.error(f"Error sending WhatsApp hold warning to teacher: {e}")


        


# dashboard_notifications for students
from .models import Notification

def create_notification(user, title, message, link=None, category="general", meta=None):
    if not user:
        return

    Notification.objects.create(
        user=user,
        title=title,
        message=message,
        link=link,
        category=category,
        meta=meta
    )

    # 🔔 Send device push notification
    send_push(user, title, message, link or "/")
# ---------------------------------------------------------

# push notifications for students
def send_push(user, title, body, url="/", icon=None, badge=None, tag=None):
    """
    Send browser/device push notification to all
    subscribed devices of the user.
    """
    if not user:
        return

    subscriptions = PushSubscription.objects.filter(user=user)
    if not subscriptions.exists():
        return

    payload = {
        "title": title,
        "body": body,
        "url": url,
        "icon": icon or "/static/data/favicon/favicon-96x96.png",
        "badge": badge or "/static/data/favicon/favicon-32x32.png",
        "tag": tag or "abcd-notification",
    }

    for sub in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": sub.endpoint,
                    "keys": sub.keys,
                },
                data=json.dumps(payload),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={
                    "sub": "mailto:admin@abcd.com"
                }
            )
        except Exception as e:
            logger.debug(f"Web push error for sub {sub.id}: {e}")


def send_broadcast_whatsapp(students, subject, message, banner_image_url=None, attachments=None, buttons=None):
    """
    Send broadcast/banner/document WhatsApp messages using Meta templates.
    Supports attached documents/files and formats clickable download links.
    """
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
            full_message += "\n\n📎 Attached Documents:\n" + "\n".join(att_links)

    if buttons and isinstance(buttons, list) and len(buttons) > 0:
        btn_links = "\n\n🔗 Links:\n" + "\n".join([f"• {b.get('label', 'Link')}: {b.get('url', '')}" for b in buttons if b.get('url')])
        full_message += btn_links

    safe_subject = (subject or "Announcement")[:90]
    safe_message = full_message or "New Announcement"
    if len(safe_message) > 950:
        safe_message = safe_message[:945] + "..."

    for student in students:
        phone = getattr(student, "whatsapp_number", None) or getattr(student, "mobile_number", None)
        if not phone:
            continue
        
        clean_num = sanitize_whatsapp_number(phone)
        if not clean_num:
            continue

        try:
            if banner_image_url:
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
                                    "image": {"link": banner_image_url}
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
            else:
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
                subject=f"📊 Exam Progress Update: {topic}",
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


