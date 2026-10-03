# users/management/commands/test_email.py
"""
Diagnostic command to test email delivery through all configured providers.

Usage:
    python manage.py test_email                          # Sends to admin email
    python manage.py test_email --to user@example.com    # Sends to specific address
    python manage.py test_email --check-only             # Just show config, don't send
"""

import os
import sys
import logging
from django.core.management.base import BaseCommand
from django.conf import settings

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Diagnose and test the email delivery pipeline (supports single, specific, or all 27 sample emails)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            type=str,
            default=None,
            help='Recipient email address for the test email(s) (e.g. vd1905@gmail.com)'
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check configuration, do not send any email'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Send all 27 system email templates as sample emails to the recipient'
        )
        parser.add_argument(
            '--template',
            type=str,
            default=None,
            help='Send a specific email template (e.g. student_fee_receipt, birthday_wish_email)'
        )
        parser.add_argument(
            '--export-gallery',
            type=str,
            nargs='?',
            const='B:/ABCD/email_preview_gallery.html',
            default=None,
            help='Export all 27 rendered templates to an interactive HTML gallery file'
        )

    def _write(self, msg, style_func=None):
        """Write message safely, stripping non-ASCII on Windows consoles."""
        if style_func:
            msg = style_func(msg)
        try:
            self.stdout.write(msg)
        except UnicodeEncodeError:
            safe = msg.encode('ascii', 'replace').decode('ascii')
            self.stdout.write(safe)

    def handle(self, *args, **options):
        self._write('\n=== ABCD EMAIL DELIVERY DIAGNOSTIC ===\n', self.style.MIGRATE_HEADING)

        # Handle Gallery Export early if requested
        if options.get('export_gallery'):
            out_file = options['export_gallery']
            from users.email_samples import export_email_preview_gallery
            to_addr = options['to'] or 'vd1905@gmail.com'
            dest = export_email_preview_gallery(out_file, recipient=to_addr)
            self._write(f'  [OK] Exported interactive email gallery (27 templates) to:', self.style.SUCCESS)
            self._write(f'       {dest}\n')
            if not options['all'] and not options['to'] and not options['template']:
                return

        # 1. Check all configured providers
        relay_url = (getattr(settings, 'GMAIL_RELAY_URL', '') or os.environ.get('GMAIL_RELAY_URL', '') or '').strip()
        brevo_key = (getattr(settings, 'BREVO_API_KEY', '') or os.environ.get('BREVO_API_KEY', '') or '').strip()
        resend_key = (getattr(settings, 'RESEND_API_KEY', '') or os.environ.get('RESEND_API_KEY', '') or '').strip()
        smtp_user = (getattr(settings, 'EMAIL_HOST_USER', '') or '').strip()
        smtp_pass = (getattr(settings, 'EMAIL_HOST_PASSWORD', '') or '').strip()
        smtp_host = getattr(settings, 'EMAIL_HOST', 'NOT SET')
        smtp_port = getattr(settings, 'EMAIL_PORT', 'NOT SET')

        self._write('Provider Configuration:', self.style.HTTP_INFO)
        self._write('')

        # Google Apps Script Relay
        if relay_url:
            self._write('  [OK] Google Apps Script Relay: CONFIGURED', self.style.SUCCESS)
            display_url = f'{relay_url[:60]}...' if len(relay_url) > 60 else relay_url
            self._write(f'       URL: {display_url}')
        else:
            self._write('  [MISSING] Google Apps Script Relay: NOT CONFIGURED (GMAIL_RELAY_URL is empty)', self.style.ERROR)

        # Brevo
        if brevo_key:
            self._write('  [OK] Brevo HTTP API: CONFIGURED', self.style.SUCCESS)
            self._write(f'       Key: {brevo_key[:12]}...{brevo_key[-4:]}')
        else:
            self._write('  [MISSING] Brevo HTTP API: NOT CONFIGURED (BREVO_API_KEY is empty)', self.style.ERROR)

        # Resend
        if resend_key:
            self._write('  [OK] Resend HTTP API: CONFIGURED', self.style.SUCCESS)
            self._write(f'       Key: {resend_key[:12]}...{resend_key[-4:]}')
        else:
            self._write('  [MISSING] Resend HTTP API: NOT CONFIGURED (RESEND_API_KEY is empty)', self.style.ERROR)

        # SMTP Fallback
        if smtp_user and smtp_pass:
            self._write('  [WARN] SMTP Fallback: CONFIGURED (Direct SMTP port connection)', self.style.WARNING)
            self._write(f'         Host: {smtp_host}:{smtp_port}, User: {smtp_user}')
        else:
            self._write('  [MISSING] SMTP Fallback: NOT CONFIGURED', self.style.ERROR)

        self._write('')

        # Summary verdict
        http_available = bool(relay_url or brevo_key or resend_key)
        if http_available:
            self._write(
                '  [OK] VERDICT: At least one HTTP provider is configured.\n'
                '       Emails should work on Render/Railway without SMTP port access.',
                self.style.SUCCESS
            )
        else:
            self._write(
                '  [NOTICE] VERDICT: Only direct SMTP is configured.\n'
                '       If Google returns 535 BadCredentials, a fresh Gmail App Password\n'
                '       or Brevo API Key is required.',
                self.style.WARNING
            )

        if options['check_only']:
            self._write('\n=== CHECK COMPLETE (no email sent) ===\n', self.style.MIGRATE_HEADING)
            return

        from users.email_service import send_html_email
        import time

        to_email = options['to'] or getattr(settings, 'ADMIN_EMAIL', None) or smtp_user or 'vd1905@gmail.com'

        # -------------------------------------------------------------
        # Dispatch Mode: Send ALL 27 Templates or a Specific Template
        # -------------------------------------------------------------
        if options['all'] or options['template']:
            from users.email_samples import get_all_sample_emails
            catalog = get_all_sample_emails()

            if options['template']:
                filter_key = options['template'].strip().lower()
                catalog = [c for c in catalog if filter_key in c['id'].lower() or filter_key in c['template'].lower()]
                if not catalog:
                    self._write(f'  [ERROR] No email template matched "{options["template"]}"', self.style.ERROR)
                    return

            total = len(catalog)
            self._write(f'\n--- Dispatching {total} Sample Email(s) to: {to_email} ---\n', self.style.MIGRATE_HEADING)

            success_count = 0
            for idx, item in enumerate(catalog, 1):
                self._write(f'[{idx}/{total}] [{item["category"]}] {item["name"]}...')
                t0 = time.time()
                try:
                    ok = send_html_email(
                        subject=item['subject'],
                        to_email=to_email,
                        template=item['template'],
                        context=item['context'],
                        fail_silently=False,
                        timeout=15,
                        run_async=False
                    )
                    elapsed = time.time() - t0
                    if ok:
                        self._write(f'    -> [PASS] Sent in {elapsed:.1f}s ({item["subject"]})', self.style.SUCCESS)
                        success_count += 1
                    else:
                        self._write(f'    -> [FAIL] Delivery returned False after {elapsed:.1f}s', self.style.ERROR)
                except Exception as e:
                    elapsed = time.time() - t0
                    self._write(f'    -> [ERROR] Failed after {elapsed:.1f}s: {e}', self.style.ERROR)

                if idx < total:
                    time.sleep(1.2)

            self._write('\n' + '=' * 45)
            if success_count == total:
                self._write(f'SUCCESS: Delivered all {success_count}/{total} sample emails to {to_email}!', self.style.SUCCESS)
            else:
                self._write(f'COMPLETED: {success_count}/{total} sample emails sent successfully to {to_email}.', self.style.WARNING)
                if success_count == 0:
                    self._write(
                        '  NOTE: If sending failed due to 535 BadCredentials, generate a new Gmail\n'
                        '  App Password at https://myaccount.google.com/apppasswords or set BREVO_API_KEY.\n'
                        '  Meanwhile, you can inspect all 27 rendered emails visually in:\n'
                        '  file:///B:/ABCD/email_preview_gallery.html',
                        self.style.NOTICE
                    )
            self._write('=' * 45 + '\n')
            return

        # -------------------------------------------------------------
        # Default: Send Single Quick Diagnostic OTP Email
        # -------------------------------------------------------------
        self._write(f'\n--- Sending test email to: {to_email} ---\n', self.style.MIGRATE_HEADING)

        start = time.time()
        result = send_html_email(
            subject='ABCD Email Test - Delivery Diagnostic',
            to_email=to_email,
            template='emails/otp_register.html',
            context={
                'username': 'Vikas Dangi',
                'otp': '482910',
                'subject': 'ABCD Email Test - Delivery Diagnostic',
                'preview_text': 'This is a test email to verify ABCD email delivery works perfectly',
                'login_url': f'{settings.SITE_URL}/login/',
            },
            fail_silently=True,
            timeout=15,
            run_async=False
        )
        elapsed = time.time() - start

        self._write('')
        if result:
            self._write(
                f'  [OK] TEST EMAIL SENT SUCCESSFULLY in {elapsed:.1f}s\n'
                f'       Check inbox of: {to_email}\n'
                f'       (Check spam/junk folder too)',
                self.style.SUCCESS
            )
        else:
            self._write(
                f'  [FAIL] TEST EMAIL FAILED after {elapsed:.1f}s\n'
                f'         Check the logs above for specific error details.\n'
                f'         Most likely cause: No HTTP provider configured + Gmail SMTP credentials rejected.',
                self.style.ERROR
            )

        self._write('\n=== DIAGNOSTIC COMPLETE ===\n', self.style.MIGRATE_HEADING)
