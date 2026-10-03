import os
import subprocess
from unittest.mock import patch
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.conf import settings
from users.views import email_diagnostics_view

User = get_user_model()


class SecretsAndDiagnosticsSecurityTestCase(TestCase):
    def setUp(self):
        self.email_patcher = patch('users.email_service.send_html_email', return_value=True)
        self.mock_email = self.email_patcher.start()
        self.factory = RequestFactory()
        self.staff_user = User.objects.create_user(
            username='staff_sec_test',
            email='staff_sec@example.com',
            password='TestPassword123!',
            is_staff=True
        )
        self.regular_user = User.objects.create_user(
            username='regular_sec_test',
            email='regular_sec@example.com',
            password='TestPassword123!',
            is_staff=False,
            is_superuser=False
        )

    def tearDown(self):
        self.email_patcher.stop()

    def test_no_leaked_credentials_in_tracked_files(self):
        """
        Scans all git-tracked files in the repository to guarantee no plaintext
        leaked secrets or known leaked credential patterns exist.
        """
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
        result = subprocess.run(
            ['git', 'ls-files'],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True
        )
        tracked_files = [f.strip() for f in result.stdout.splitlines() if f.strip()]

        # Pattern needles constructed dynamically to avoid false positives on this test file
        needles = [
            "".join(["c", "p", "w", "e"]),
            "".join(["VIK", "003", "@", "dan"]),
            "".join(["Sandeep", "ananda", "jimaharaj"]),
        ]

        binary_exts = {'.png', '.jpg', '.jpeg', '.gif', '.ico', '.webp', '.pdf', '.woff', '.woff2', '.ttf', '.eot', '.db', '.sqlite3'}
        current_test_relpath = os.path.relpath(__file__, repo_root).replace('\\', '/')

        violations = []
        for rel_path in tracked_files:
            if rel_path.replace('\\', '/') == current_test_relpath:
                continue
            ext = os.path.splitext(rel_path)[1].lower()
            if ext in binary_exts:
                continue

            full_path = os.path.join(repo_root, rel_path)
            if not os.path.isfile(full_path):
                continue

            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    for needle in needles:
                        if needle in content:
                            masked = f"{needle[:2]}...{needle[-2:]}"
                            violations.append(f"Pattern {masked} found in tracked file: {rel_path}")
            except Exception as e:
                pass

        self.assertEqual(violations, [], f"Found leaked patterns in tracked files:\n" + "\n".join(violations))

    def test_email_diagnostics_locked_to_unauthenticated(self):
        """Unauthenticated requests must receive 403 Forbidden."""
        request = self.factory.get('/api/diag/email-test/')
        from django.contrib.auth.models import AnonymousUser
        request.user = AnonymousUser()
        response = email_diagnostics_view(request)
        self.assertEqual(response.status_code, 403)

    def test_email_diagnostics_locked_to_regular_user(self):
        """Non-staff users must receive 403 Forbidden."""
        request = self.factory.get('/api/diag/email-test/')
        request.user = self.regular_user
        response = email_diagnostics_view(request)
        self.assertEqual(response.status_code, 403)

    def test_email_diagnostics_safe_for_staff(self):
        """Staff GET returns 200 and never outputs plaintext password."""
        request = self.factory.get('/api/diag/email-test/')
        request.user = self.staff_user
        response = email_diagnostics_view(request)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        # Confirm no password value is leaked
        self.assertNotIn('EMAIL_HOST_PASSWORD:', content)
        self.assertNotIn('cpwe', content)
        self.assertIn('EMAIL_HOST_PASSWORD_CONFIGURED', content)

    def test_email_diagnostics_send_requires_post(self):
        """GET with send=1 must be rejected with 405 Method Not Allowed."""
        request = self.factory.get('/api/diag/email-test/?send=1')
        request.user = self.staff_user
        response = email_diagnostics_view(request)
        self.assertEqual(response.status_code, 405)

    def test_reset_superuser_password_command(self):
        """reset_superuser_password sets new password and clears lockout cache."""
        test_admin = User.objects.create_superuser(
            username='sec_admin_target',
            email='sec_target@example.com',
            password='OldPassword123!'
        )
        # Populate lockout cache
        cache.set(f"login_failed_user_{test_admin.username}", 5, 900)
        cache.set(f"login_attempts_{test_admin.pk}", 5, 86400)

        with patch('getpass.getpass', side_effect=['NewSecurePass!456', 'NewSecurePass!456']):
            call_command('reset_superuser_password', 'sec_admin_target')

        test_admin.refresh_from_db()
        self.assertTrue(test_admin.check_password('NewSecurePass!456'))
        self.assertIsNone(cache.get(f"login_failed_user_{test_admin.username}"))
        self.assertIsNone(cache.get(f"login_attempts_{test_admin.pk}"))

    def test_reset_superuser_password_rejects_non_superuser_without_promote(self):
        """Non-superuser cannot be reset without explicit --promote flag."""
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError) as ctx:
            call_command('reset_superuser_password', 'regular_sec_test')
        self.assertIn("is not a superuser", str(ctx.exception))

    def test_reset_superuser_password_promotes_with_flag_and_confirmation(self):
        """Non-superuser is promoted when --promote and matching confirmation username are provided."""
        with patch('builtins.input', return_value='regular_sec_test'):
            with patch('getpass.getpass', side_effect=['BrandNewPass!789', 'BrandNewPass!789']):
                call_command('reset_superuser_password', 'regular_sec_test', promote=True)

        self.regular_user.refresh_from_db()
        self.assertTrue(self.regular_user.is_superuser)
        self.assertTrue(self.regular_user.is_staff)
        self.assertTrue(self.regular_user.check_password('BrandNewPass!789'))

    def test_reset_superuser_password_validates_and_reprompts(self):
        """Short or invalid password is rejected and user is re-prompted."""
        test_admin = User.objects.create_superuser(
            username='sec_val_admin',
            email='val_admin@example.com',
            password='OldPassword123!'
        )
        # Attempt 1: short '123'
        # Attempt 2: valid 'ComplexLongPassword!999' + confirm
        with patch('getpass.getpass', side_effect=['123', 'ComplexLongPassword!999', 'ComplexLongPassword!999']):
            call_command('reset_superuser_password', 'sec_val_admin')

        test_admin.refresh_from_db()
        self.assertTrue(test_admin.check_password('ComplexLongPassword!999'))

    def test_recovery_key_requires_at_least_16_characters(self):
        """Recovery key < 16 chars must be rejected by auth backend."""
        from users.auth_backends import EmailOrUsernameModelBackend
        backend = EmailOrUsernameModelBackend()

        vaku_user = User.objects.create_superuser(
            username='vaku_test_recovery',
            email='vd19055@gmail.com',
            password='InitialPassword123!'
        )

        # 15 characters key: rejected
        with self.settings(VAKU_RECOVERY_KEY='short_15_char__'):
            auth_user = backend.authenticate(None, username='vd19055@gmail.com', password='short_15_char__')
            self.assertIsNone(auth_user)

        # 16+ characters key: accepted and logged
        with self.settings(VAKU_RECOVERY_KEY='strong_recovery_key_16_chars!'):
            with self.assertLogs('users.auth_backends', level='WARNING') as log_ctx:
                auth_user = backend.authenticate(None, username='vd19055@gmail.com', password='strong_recovery_key_16_chars!')
                self.assertIsNotNone(auth_user)
                self.assertEqual(auth_user.username, 'vaku_test_recovery')
                self.assertTrue(any('Master recovery key used for superuser' in msg for msg in log_ctx.output))
                # Confirm secret key value is never logged
                self.assertFalse(any('strong_recovery_key_16_chars!' in msg for msg in log_ctx.output))

    def test_email_diagnostics_live_send_atomic_rate_limit(self):
        """Second live send within 30s returns 429 Too Many Requests."""
        cache.clear()
        request = self.factory.post('/api/diag/email-test/', {'send': '1', 'to': 'test@example.com'})
        request.user = self.staff_user

        # First request succeeds
        resp1 = email_diagnostics_view(request)
        self.assertEqual(resp1.status_code, 200)

        # Immediate second request returns 429
        resp2 = email_diagnostics_view(request)
        self.assertEqual(resp2.status_code, 429)
        self.assertIn('Rate limit exceeded', resp2.content.decode('utf-8'))
