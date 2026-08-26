# users/email_service.py

import logging
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

        # 2. Map logo & illustration to public HTTPS URLs for localhost (or production domain when deployed)
        is_local = "127.0.0.1" in site_url or "localhost" in site_url
        if is_local:
            logo_url = "https://files.catbox.moe/7qd1rr.png"
            illustration_url_map = {
                'welcome.png': 'https://files.catbox.moe/vgq3zq.png',
                'security.png': 'https://files.catbox.moe/woth7t.png',
                'seat.png': 'https://files.catbox.moe/se0u8g.png',
                'approval.png': 'https://files.catbox.moe/at7w40.png',
                'reminder.png': 'https://files.catbox.moe/aw7e4m.png',
                'payment.png': 'https://files.catbox.moe/xc32te.png',
                'complaint.png': 'https://files.catbox.moe/4ag5vr.png',
                'course.png': 'https://files.catbox.moe/frzfsa.png',
                'guidance.png': 'https://files.catbox.moe/q7b5dd.png',
                'announcement.png': 'https://files.catbox.moe/l5gk79.png',
                'achievement.png': 'https://files.catbox.moe/at7w40.png',
                'time_expired.png': 'https://files.catbox.moe/5mj8jt.png',
                'fee_due.png': 'https://files.catbox.moe/bqu21n.png',
            }
            illustration_url = illustration_url_map.get(illustration_name, 'https://files.catbox.moe/daepvn.png')
        else:
            logo_url = f"{site_url.rstrip('/')}/static/data/light-logo.png"
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

        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email],
            headers=headers,
            connection=connection
        )
        email.attach_alternative(html_content, "text/html")
        
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
