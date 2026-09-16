# users/email_service.py

import os
import re
import base64
import logging
from django.core.mail import EmailMultiAlternatives, get_connection
from django.template.loader import render_to_string
from django.conf import settings
from django.contrib.staticfiles import finders

logger = logging.getLogger(__name__)

# In-memory cache for base64 data URIs so disk I/O and encoding are only done once
_IMAGE_DATA_URI_CACHE = {}

# One-time startup diagnostic flag
_EMAIL_CONFIG_CHECKED = False


def _check_email_config():
    """One-time startup diagnostic: warn loudly if no HTTP email provider is configured."""
    global _EMAIL_CONFIG_CHECKED
    if _EMAIL_CONFIG_CHECKED:
        return
    _EMAIL_CONFIG_CHECKED = True

    relay_url = (getattr(settings, 'GMAIL_RELAY_URL', '') or os.environ.get('GMAIL_RELAY_URL', '') or '').strip()
    brevo_key = (getattr(settings, 'BREVO_API_KEY', '') or os.environ.get('BREVO_API_KEY', '') or '').strip()
    resend_key = (getattr(settings, 'RESEND_API_KEY', '') or os.environ.get('RESEND_API_KEY', '') or '').strip()

    configured = []
    if relay_url:
        configured.append('Google Apps Script Relay')
    if brevo_key:
        configured.append('Brevo HTTP API')
    if resend_key:
        configured.append('Resend HTTP API')

    if configured:
        logger.info(f"[EMAIL CONFIG] HTTP email providers available: {', '.join(configured)}")
    else:
        logger.critical(
            "[EMAIL CONFIG] ⚠️  NO HTTP EMAIL PROVIDER IS CONFIGURED! "
            "GMAIL_RELAY_URL, BREVO_API_KEY, and RESEND_API_KEY are all empty. "
            "On Render/Railway/Docker, SMTP ports (465/587) are typically BLOCKED. "
            "Emails will FAIL unless an HTTP provider is set up. "
            "Set BREVO_API_KEY in your environment variables (free 300 emails/day). "
            "See docs/google_apps_script_relay.js for the Apps Script option."
        )

    smtp_user = (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip()
    smtp_pass = (getattr(settings, 'EMAIL_HOST_PASSWORD', '') or '').strip()
    if smtp_user and smtp_pass:
        logger.info(f"[EMAIL CONFIG] SMTP fallback configured: {smtp_user} via {getattr(settings, 'EMAIL_HOST', 'smtp.gmail.com')}:{getattr(settings, 'EMAIL_PORT', 465)}")
    else:
        logger.warning("[EMAIL CONFIG] SMTP fallback NOT configured (missing EMAIL_HOST_USER or EMAIL_HOST_PASSWORD)")


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
    
    Dispatch chain (tries each in order, stops on first success):
      1. Google Apps Script Relay (HTTPS, sends from abcd2013baq@gmail.com)
      2. Brevo HTTP API (HTTPS, 300 free/day)
      3. Resend HTTP API (HTTPS, 100 free/day)
      4. Direct SMTP via Gmail (BLOCKED on Render/Railway free plans)
    
    On cloud hosts that block SMTP ports (25/465/587), you MUST configure
    at least one HTTP provider (BREVO_API_KEY recommended).
    """
    # Run one-time diagnostic on first email attempt
    _check_email_config()

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

        # Embed images as base64 data URIs so they display instantly in Gmail/Outlook
        # without being blocked as "remote images" or appearing as attachments.
        # This matches how professional mailers (PhonePe, Razorpay, etc.) embed logos.

        def _img_to_data_uri(static_relative_path):
            """Find a static file and return a data: URI string, or None on failure (cached in memory)."""
            if static_relative_path in _IMAGE_DATA_URI_CACHE:
                return _IMAGE_DATA_URI_CACHE[static_relative_path]
            try:
                abs_path = finders.find(static_relative_path)
                if not abs_path:
                    # Fallback: look directly in STATIC_ROOT / staticfiles
                    from django.conf import settings as _s
                    import os
                    for root in [getattr(_s, 'STATIC_ROOT', None), getattr(_s, 'STATICFILES_DIRS', [None])[0]]:
                        if root:
                            candidate = os.path.join(str(root), static_relative_path)
                            if os.path.isfile(candidate):
                                abs_path = candidate
                                break
                if not abs_path:
                    return None
                with open(abs_path, 'rb') as f:
                    b64 = base64.b64encode(f.read()).decode('ascii')
                ext = static_relative_path.rsplit('.', 1)[-1].lower()
                mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'gif': 'image/gif', 'svg': 'image/svg+xml'}.get(ext, 'image/png')
                res = f"data:{mime};base64,{b64}"
                _IMAGE_DATA_URI_CACHE[static_relative_path] = res
                return res
            except Exception:
                return None

        inline_images = []

        # Logo: embed as base64 data URI (14KB — negligible)
        logo_data_uri = _img_to_data_uri('data/light-logo.png')
        site_url_clean = str(site_url).rstrip('/')
        context['logo_url'] = logo_data_uri or f"{site_url_clean}/static/data/light-logo.png"

        # Illustration: embed as base64 data URI (25–80KB per image)
        illus_data_uri = _img_to_data_uri(f'data/email_illustrations/{illustration_name}')
        context['illustration_url'] = illus_data_uri or f"{site_url_clean}/static/data/email_illustrations/{illustration_name}"

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

        # =====================================================================
        # HTTP DISPATCH CHAIN (HTTPS Port 443 — bypasses SMTP port blocks)
        # Each method is tried in order; first success returns immediately.
        # =====================================================================

        # --- OPTION A: Google Apps Script Webhook Relay ---
        relay_url = (getattr(settings, 'GMAIL_RELAY_URL', '') or os.environ.get('GMAIL_RELAY_URL', '') or '').strip()
        if relay_url:
            try:
                import requests as req_lib
                logger.info(f"[EMAIL DISPATCH] Attempting Google Apps Script Relay for '{clean_subject}' to {to_email}")
                payload = {
                    'to': to_email,
                    'subject': clean_subject,
                    'html': html_content,
                    'text': text_content,
                    'from_name': "ABCD Campus"
                }
                if attachments:
                    payload['attachments'] = []
                    for att in attachments:
                        att_name = att[0]
                        att_content = att[1]
                        att_mime = att[2] if len(att) > 2 else 'application/octet-stream'
                        b64_data = base64.b64encode(att_content if isinstance(att_content, bytes) else att_content.encode('utf-8')).decode('ascii')
                        payload['attachments'].append({
                            'name': att_name,
                            'content': b64_data,
                            'mimeType': att_mime
                        })
                resp = req_lib.post(relay_url, json=payload, timeout=min(timeout, 12))
                if resp.status_code == 200:
                    try:
                        res_data = resp.json()
                        if res_data.get('status') == 'ok':
                            logger.info(f"EMAIL SUCCESS (Google HTTP Relay): Sent '{clean_subject}' to {to_email}")
                            return True
                        else:
                            err_msg = res_data.get('message', 'Unknown Google Apps Script error')
                            logger.warning(f"[EMAIL DISPATCH] Google Apps Script Relay reported failure: '{err_msg}'. Falling back to Brevo...")
                    except Exception:
                        if '"status":"ok"' in resp.text:
                            logger.info(f"EMAIL SUCCESS (Google HTTP Relay): Sent '{clean_subject}' to {to_email}")
                            return True
                        logger.warning(f"[EMAIL DISPATCH] Google Apps Script Relay returned unexpected payload: {resp.text[:200]}. Falling back to Brevo...")
                else:
                    logger.warning(f"[EMAIL DISPATCH] Google HTTP Relay returned status {resp.status_code}: {resp.text[:200]}. Falling back to Brevo...")
            except Exception as h_err:
                logger.warning(f"[EMAIL DISPATCH] Google HTTP Relay error: {h_err}. Falling back to Brevo...")
        else:
            logger.debug("[EMAIL DISPATCH] Google Apps Script Relay: SKIPPED (GMAIL_RELAY_URL not configured)")

        # --- OPTION B: Brevo (Sendinblue) HTTP REST API (300 free emails/day) ---
        brevo_key = (getattr(settings, 'BREVO_API_KEY', '') or os.environ.get('BREVO_API_KEY', '') or '').strip()
        if brevo_key:
            try:
                import requests as req_lib
                sender_email = (getattr(settings, 'EMAIL_HOST_USER', '') or 'abcd2013baq@gmail.com').strip()
                logger.info(f"[EMAIL DISPATCH] Attempting Brevo HTTP API for '{clean_subject}' to {to_email}")
                brevo_payload = {
                    "sender": {"name": "ABCD Campus", "email": sender_email},
                    "to": [{"email": to_email}],
                    "subject": clean_subject,
                    "htmlContent": html_content,
                    "textContent": text_content
                }
                # Attach files via Brevo's attachment format
                if attachments:
                    brevo_payload["attachment"] = []
                    for att in attachments:
                        att_name = att[0]
                        att_content = att[1]
                        b64_data = base64.b64encode(att_content if isinstance(att_content, bytes) else att_content.encode('utf-8')).decode('ascii')
                        brevo_payload["attachment"].append({
                            "name": att_name,
                            "content": b64_data
                        })
                resp = req_lib.post(
                    "https://api.brevo.com/v3/smtp/email",
                    headers={
                        "api-key": brevo_key,
                        "Content-Type": "application/json",
                        "Accept": "application/json"
                    },
                    json=brevo_payload,
                    timeout=min(timeout, 10)
                )
                if resp.status_code in [200, 201, 202]:
                    logger.info(f"EMAIL SUCCESS (Brevo HTTP API): Sent '{clean_subject}' to {to_email}")
                    return True
                else:
                    logger.warning(f"[EMAIL DISPATCH] Brevo HTTP API returned status {resp.status_code}: {resp.text[:300]}. Falling back...")
            except Exception as b_err:
                logger.warning(f"[EMAIL DISPATCH] Brevo HTTP API error: {b_err}. Falling back...")
        else:
            logger.debug("[EMAIL DISPATCH] Brevo HTTP API: SKIPPED (BREVO_API_KEY not configured)")

        # --- OPTION C: Resend HTTP REST API (100 free emails/day) ---
        resend_key = (getattr(settings, 'RESEND_API_KEY', '') or os.environ.get('RESEND_API_KEY', '') or '').strip()
        if resend_key:
            try:
                import requests as req_lib
                from_addr = getattr(settings, 'RESEND_FROM_EMAIL', None) or "ABCD Smart Campus <onboarding@resend.dev>"
                logger.info(f"[EMAIL DISPATCH] Attempting Resend HTTP API for '{clean_subject}' to {to_email}")
                resp = req_lib.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {resend_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "from": from_addr,
                        "to": [to_email],
                        "subject": clean_subject,
                        "html": html_content,
                        "text": text_content
                    },
                    timeout=min(timeout, 8)
                )
                if resp.status_code in [200, 201, 202]:
                    logger.info(f"EMAIL SUCCESS (Resend HTTP API): Sent '{clean_subject}' to {to_email}")
                    return True
                else:
                    logger.warning(f"[EMAIL DISPATCH] Resend HTTP API returned status {resp.status_code}: {resp.text[:200]}. Falling back...")
            except Exception as r_err:
                logger.warning(f"[EMAIL DISPATCH] Resend HTTP API error: {r_err}. Falling back...")
        else:
            logger.debug("[EMAIL DISPATCH] Resend HTTP API: SKIPPED (RESEND_API_KEY not configured)")

        # --- OPTION D: Direct SMTP (LAST RESORT — blocked on Render/Railway free plans) ---
        logger.info(f"[EMAIL DISPATCH] All HTTP providers exhausted. Attempting SMTP fallback for '{clean_subject}' to {to_email}")

        # Use a connection with an explicit timeout to prevent command freezing
        connection = get_connection(timeout=timeout)

        # Transactional anti-spam headers to inform mail providers (Gmail, Outlook) of authentic automated system emails
        headers = {
            'Auto-Submitted': 'auto-generated',
            'X-Auto-Response-Suppress': 'All',
            'X-Mailer': 'ABCD Campus Mailer',
            'Feedback-ID': 'system:transactional:abcd',
            'X-Priority': '1',
            'Importance': 'high',
        }

        reply_to_addr = getattr(settings, 'ADMIN_EMAIL', None) or getattr(settings, 'EMAIL_HOST_USER', None) or 'abcd2013baq@gmail.com'
        reply_to_list = [reply_to_addr] if reply_to_addr else None

        from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
        if not from_email or '<>' in from_email or '@' not in from_email:
            smtp_user = (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip() or 'abcd2013baq@gmail.com'
            from_email = f'"ABCD Campus" <{smtp_user}>'

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
        
        # SAFE ERROR HANDLING: Wrap send inside try/except
        # We set fail_silently=False internally to catch the error and log it properly
        email.send(fail_silently=False)
        
        logger.info(f"EMAIL SUCCESS (SMTP): Sent '{subject}' to {to_email}")
        return True

    except Exception as e:
        logger.error(
            f"EMAIL FAILURE: ALL dispatch methods failed for '{subject}' to {to_email}. "
            f"Last error: {str(e)}. "
            f"Configured providers: GMAIL_RELAY_URL={'YES' if (getattr(settings, 'GMAIL_RELAY_URL', '') or '').strip() else 'NO'}, "
            f"BREVO_API_KEY={'YES' if (getattr(settings, 'BREVO_API_KEY', '') or '').strip() else 'NO'}, "
            f"RESEND_API_KEY={'YES' if (getattr(settings, 'RESEND_API_KEY', '') or '').strip() else 'NO'}"
        )
        
        # KEEP fail_silently behavior compatible
        if not fail_silently:
            raise
            
        # RETURN BOOLEAN STATUS
        return False
