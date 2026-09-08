# users/email_service.py

import os
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
        thread.daemon = True
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

        # 2. Locate local static files for instantaneous 0ms "flash loading" via Inline CID (Content-ID MIME)
        inline_images = []
        base_dir = getattr(settings, 'BASE_DIR', None)
        
        logo_file = None
        ill_file = None
        if base_dir:
            search_dirs = [
                os.path.join(base_dir, 'static'),
                getattr(settings, 'STATIC_ROOT', None)
            ]
            for s_dir in search_dirs:
                if not s_dir or not os.path.exists(s_dir):
                    continue
                cand_logo = os.path.join(s_dir, 'data', 'light-logo.png')
                if not logo_file and os.path.exists(cand_logo):
                    logo_file = cand_logo
                cand_ill = os.path.join(s_dir, 'data', 'email_illustrations', illustration_name)
                if not ill_file and os.path.exists(cand_ill):
                    ill_file = cand_ill

        # 3. Attach Logo inline if file exists locally, otherwise fallback to public URL
        if logo_file and os.path.exists(logo_file):
            try:
                with open(logo_file, 'rb') as f:
                    img_logo = MIMEImage(f.read(), _subtype='png')
                img_logo.add_header('Content-ID', '<abcd_logo>')
                img_logo.add_header('Content-Disposition', 'inline', filename='logo.png')
                inline_images.append(img_logo)
                logo_url = "cid:abcd_logo"
            except Exception as e:
                logger.warning(f"Failed to read local logo for CID: {e}")
                logo_url = f"{site_url.rstrip('/')}/static/data/light-logo.png"
        else:
            logo_url = f"{site_url.rstrip('/')}/static/data/light-logo.png"

        # 4. Attach Hero Illustration inline if file exists locally, otherwise fallback to public URL
        if ill_file and os.path.exists(ill_file):
            try:
                with open(ill_file, 'rb') as f:
                    img_ill = MIMEImage(f.read(), _subtype='png')
                img_ill.add_header('Content-ID', '<abcd_illustration>')
                img_ill.add_header('Content-Disposition', 'inline', filename=illustration_name)
                inline_images.append(img_ill)
                illustration_url = "cid:abcd_illustration"
            except Exception as e:
                logger.warning(f"Failed to read local illustration for CID: {e}")
                illustration_url = f"{site_url.rstrip('/')}/static/data/email_illustrations/{illustration_name}"
        else:
            illustration_url = f"{site_url.rstrip('/')}/static/data/email_illustrations/{illustration_name}"

        context['logo_url'] = logo_url
        context['illustration_url'] = illustration_url

        html_content = render_to_string(template, context)
        
        if not text_content:
            # Generate plain text by stripping HTML tags to prevent spam filtering
            import re
            clean_text = re.sub(r'<(script|style)\b[^>]*>([\s\S]*?)</\1>', '', html_content)
            clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
            clean_text = re.sub(r'\s+', ' ', clean_text).strip()
            text_content = clean_text

        # Use a connection with an explicit timeout to prevent command freezing
        connection = get_connection(timeout=timeout)

        # Transactional anti-spam headers to inform mail providers (Gmail, Outlook) of authentic automated system emails
        headers = {
            'Auto-Submitted': 'auto-generated',
            'X-Auto-Response-Suppress': 'All',
        }

        reply_to_addr = getattr(settings, 'ADMIN_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None)
        reply_to_list = [reply_to_addr] if reply_to_addr else None

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
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
