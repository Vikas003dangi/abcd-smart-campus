# users/email_service.py

import os
import re
import logging
from email.mime.image import MIMEImage
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.conf import settings

logger = logging.getLogger(__name__)

def send_html_email(
    *,
    subject: str,
    to_email: str,
    template: str,
    context: dict,
    attachments: list = None,
    fail_silently=True,
    timeout=15,
    text_content: str = None,
    run_async=False
):
    """
    Central email sender for entire project.
    Hardened against SMTP hangs with timeouts and structured logging.
    """
    # Direct delivery to destination address
    pass
    if run_async:
        import threading
        thread = threading.Thread(
            target=send_html_email,
            kwargs={
                'subject': subject,
                'to_email': to_email,
                'template': template,
                'context': context,
                'attachments': attachments,
                'fail_silently': fail_silently,
                'timeout': timeout,
                'text_content': text_content,
                'run_async': False
            }
        )
        thread.daemon = False
        thread.start()
        return True

    if not to_email or not str(to_email).strip():
        logger.warning(f"EMAIL SKIPPED: Missing recipient address for subject '{subject}'")
        return False
    to_email = str(to_email).strip()

    try:
        if context is None:
            context = {}

        site_url = context.get("site_url") or settings.SITE_URL
        context.setdefault("site_url", site_url)

        # 1. Determine illustration filename based on subject/template
        illustration_name = 'welcome.png'
        tmpl_lower = (template or '').lower()
        subj_lower = (subject or '').lower()

        if any(k in tmpl_lower or k in subj_lower for k in ['birthday']):
            illustration_name = 'birthday.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['grace']):
            illustration_name = 'hold_grace.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['learning']):
            illustration_name = 'learning_reminder.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['due', 'reminder']) and any(k in tmpl_lower or k in subj_lower for k in ['fee', 'payment']):
            illustration_name = 'fee_due.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['fee', 'receipt', 'payment', 'paid']):
            illustration_name = 'payment.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['complaint']):
            illustration_name = 'complaint.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['course', 'coaching', 'material']):
            illustration_name = 'course.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['achievement']):
            illustration_name = 'achievement.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['guidy', 'guidance']):
            illustration_name = 'guidance.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['expired', 'expire']):
            illustration_name = 'time_expired.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['broadcast', 'announcement']):
            illustration_name = 'announcement.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['otp', 'security', 'password', 'verify']):
            illustration_name = 'security.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['approval', 'approved', 'admitted', 'alumni']):
            illustration_name = 'approval.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['seat', 'hold', 'allotment']):
            illustration_name = 'seat.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['reminder', 'todo', 'visitor']):
            illustration_name = 'reminder.png'
        elif any(k in tmpl_lower or k in subj_lower for k in ['welcome']):
            illustration_name = 'welcome.png'

        # Use lightweight direct URLs for images to keep email payload <5KB and ensure instant delivery
        site_url_clean = str(site_url).rstrip('/')
        inline_images = []
        context['logo_url'] = f"{site_url_clean}/static/data/light-logo.png"
        context['illustration_url'] = f"{site_url_clean}/static/data/email_illustrations/{illustration_name}"

        html_content = render_to_string(template, context)
        
        # Sanitize subject: Strip emojis and pipe characters to guarantee deliverability
        clean_subject = re.sub(r'[\U00010000-\U0010ffff\u2600-\u27ff\u2300-\u23ff\u2b50\u200d\ufe0f\u2000-\u206f]', '', str(subject or '')).replace('|', '-').strip()
        clean_subject = re.sub(r'\s+', ' ', clean_subject)
        if not clean_subject:
            clean_subject = "ABCD Coaching & Library Update"

        if not text_content:
            # Generate high-quality human-readable plain text by converting block tags to newlines
            import html as py_html
            text = re.sub(r'<(script|style)\b[^>]*>([\s\S]*?)</\1>', '', html_content, flags=re.IGNORECASE)
            text = re.sub(r'<br\s*/?>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'</(p|div|tr|li|h[1-6])>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = py_html.unescape(text)
            text = re.sub(r'[ \t]+', ' ', text)
            text = re.sub(r'\n\s*\n+', '\n\n', text).strip()
            text_content = text

        # Use a connection with an explicit timeout to prevent command freezing
        connection = get_connection(timeout=timeout)

        # Transactional anti-spam headers to inform mail providers (Gmail, Outlook) of authentic automated system emails
        headers = {
            'Auto-Submitted': 'auto-generated',
            'X-Auto-Response-Suppress': 'All',
            'X-Mailer': 'ABCD Campus Mailer',
            'Feedback-ID': 'system:transactional:abcd',
        }

        reply_to_addr = getattr(settings, 'ADMIN_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None) or 'abcd2013baq@gmail.com'
        reply_to_list = [reply_to_addr] if reply_to_addr else None

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        if not from_email or '<>' in from_email or '@' not in from_email:
            smtp_user = (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip() or 'abcd2013baq@gmail.com'
            from_email = f'"ABCD Coaching & Library" <{smtp_user}>'

        email = EmailMultiAlternatives(
            subject=clean_subject,
            body=text_content,
            from_email=from_email,
            to=[to_email],
            reply_to=reply_to_list,
            headers=headers,
            connection=connection
        )
        email.attach_alternative(html_content, "text/html")
        
        # Attach inline images (CID) for instantaneous local rendering in email clients
        for img_mime in inline_images:
            email.attach(img_mime)

        # Attach custom files if provided (list of tuples: (name, content, mimetype))
        if attachments:
            for attachment in attachments:
                email.attach(*attachment)
        
        # 3. SAFE ERROR HANDLING: Wrap send inside try/except
        # We set fail_silently=False internally to catch the error and log it properly
        email.send(fail_silently=False)
        
        # 2. ADD LOGGING (Success)
        logger.info(f"EMAIL SUCCESS: Sent '{subject}' to {to_email}")
        return True

    except Exception as e:
        # 2. ADD LOGGING (Failure/Timeout)
        logger.error(f"EMAIL FAILURE: Failed to send '{subject}' to {to_email}. Reason: {str(e)}")
        
        # 4. KEEP fail_silently behavior compatible
        if not fail_silently:
            raise
            
        # 7. RETURN BOOLEAN STATUS
        return False
