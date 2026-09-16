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
    help = 'Diagnose and test the email delivery pipeline'

    def add_arguments(self, parser):
        parser.add_argument(
            '--to',
            type=str,
            default=None,
            help='Recipient email address for the test email'
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Only check configuration, do not send a test email'
        )

    def _write(self, msg, style_func=None):
        """Write message safely, stripping non-ASCII on Windows consoles."""
        if style_func:
            msg = style_func(msg)
        try:
            self.stdout.write(msg)
        except UnicodeEncodeError:
            # Fallback: strip non-ASCII chars for cp1252/Windows consoles
            safe = msg.encode('ascii', 'replace').decode('ascii')
            self.stdout.write(safe)

    def handle(self, *args, **options):
        self._write('\n=== ABCD EMAIL DELIVERY DIAGNOSTIC ===\n', self.style.MIGRATE_HEADING)

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
            self._write('  [WARN] SMTP Fallback: CONFIGURED (but BLOCKED on Render/Railway free plans)', self.style.WARNING)
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
                '  [CRITICAL] VERDICT: NO HTTP EMAIL PROVIDER IS CONFIGURED!\n'
                '       On Render/Railway free plans, SMTP is BLOCKED.\n'
                '       Emails will FAIL in production.\n'
                '\n'
                '       FIX: Set BREVO_API_KEY in your Render environment variables.\n'
                '       1. Sign up at https://app.brevo.com (free, 300 emails/day)\n'
                '       2. Verify sender: abcd2013baq@gmail.com\n'
                '       3. Generate API key: SMTP & API > API Keys\n'
                '       4. Add to Render Dashboard > Environment:\n'
                '          BREVO_API_KEY=xkeysib-your-key-here',
                self.style.ERROR
            )

        if options['check_only']:
            self._write('\n=== CHECK COMPLETE (no email sent) ===\n', self.style.MIGRATE_HEADING)
            return

        # 2. Send a test email
        to_email = options['to'] or getattr(settings, 'ADMIN_EMAIL', None) or smtp_user or 'abcd2013baq@gmail.com'

        self._write(f'\n--- Sending test email to: {to_email} ---\n', self.style.MIGRATE_HEADING)

        from users.email_service import send_html_email
        import time

        start = time.time()
        result = send_html_email(
            subject='ABCD Email Test - Delivery Diagnostic',
            to_email=to_email,
            template='emails/otp_register.html',
            context={
                'username': 'TestUser',
                'otp': '123456',
                'subject': 'ABCD Email Test - Delivery Diagnostic',
                'preheader': 'This is a test email to verify delivery works',
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
                f'         Most likely cause: No HTTP provider configured + SMTP port blocked.',
                self.style.ERROR
            )

        self._write('\n=== DIAGNOSTIC COMPLETE ===\n', self.style.MIGRATE_HEADING)
