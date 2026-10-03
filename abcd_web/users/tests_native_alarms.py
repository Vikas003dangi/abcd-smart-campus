# users/tests_native_alarms.py
import json
from datetime import timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.core.signing import TimestampSigner
from users.models import TodoTask

class NativeAlarmAuthTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='test_alarm_user', password='password123')
        self.other_user = User.objects.create_user(username='other_alarm_user', password='password123')

        self.task = TodoTask.objects.create(
            user=self.user,
            category='REMINDER',
            is_done=False,
            is_trash=False,
            metadata={
                'title': 'Test Exam Reminder',
                'recurrence': 'once',
                'alarm_enabled': True,
                'alarm_status': 'ringing',
                'time_str': '10:00'
            }
        )

    def test_active_reminders_api_generates_action_token(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('users:active_reminders_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        reminders = data.get('reminders', [])
        self.assertTrue(len(reminders) >= 1)
        rem = next(r for r in reminders if r['id'] == self.task.id)
        self.assertIn('action_token', rem)
        token = rem['action_token']

        # Verify token un-signs to task_id:user_id
        signer = TimestampSigner(salt='abcd-reminder-action')
        original = signer.unsign(token, max_age=3600)
        self.assertEqual(original, f"{self.task.id}:{self.user.id}")

    def test_active_reminders_api_returns_all_recurrence_fields_and_plain_reminders(self):
        # Create a recurring task with until_date, day_of_month, interval_days, and plain reminder (alarm_enabled=False)
        recurring_task = TodoTask.objects.create(
            user=self.user,
            category='REMINDER',
            is_done=False,
            is_trash=False,
            metadata={
                'title': 'Monthly Fee Reminder',
                'recurrence': 'monthly',
                'day_of_month': 28,
                'interval_days': 15,
                'until_date': '2026-12-31',
                'days_of_week': [0, 2, 4],
                'alarm_enabled': False,  # Plain reminder (gentle notification)
                'alarm_status': 'ringing',
                'time_str': '14:30'
            }
        )

        self.client.force_login(self.user)
        response = self.client.get(reverse('users:active_reminders_api'))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        reminders = data.get('reminders', [])
        rem = next(r for r in reminders if r['id'] == recurring_task.id)

        self.assertFalse(rem['is_alarm'], "Plain reminder must have is_alarm=False")
        self.assertEqual(rem['recurrence'], 'monthly')
        self.assertEqual(rem['day_of_month'], 28)
        self.assertEqual(rem['interval_days'], 15)
        self.assertEqual(rem['until_date'], '2026-12-31')
        self.assertEqual(rem['days_of_week'], '0,2,4')
        self.assertEqual(rem['time_str'], '14:30')

    def test_unauthenticated_post_without_token_fails(self):
        # Client not logged in
        url = reverse('users:todo_reminder_action', kwargs={'task_id': self.task.id})
        response = self.client.post(
            url,
            data=json.dumps({'action': 'stop'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json().get('success'))

    def test_unauthenticated_post_with_valid_token_stops_alarm(self):
        signer = TimestampSigner(salt='abcd-reminder-action')
        token = signer.sign(f"{self.task.id}:{self.user.id}")

        url = reverse('users:todo_reminder_action', kwargs={'task_id': self.task.id})
        response = self.client.post(
            url,
            data=json.dumps({'action': 'stop', 'action_token': token}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('action'), 'stop')

        # Verify task is updated in DB
        self.task.refresh_from_db()
        self.assertEqual(self.task.metadata.get('alarm_status'), 'stopped')
        self.assertTrue(self.task.is_done)

    def test_unauthenticated_post_with_valid_token_snoozes_alarm(self):
        signer = TimestampSigner(salt='abcd-reminder-action')
        token = signer.sign(f"{self.task.id}:{self.user.id}")

        url = reverse('users:todo_reminder_action', kwargs={'task_id': self.task.id})
        response = self.client.post(
            url,
            data=json.dumps({'action': 'snooze', 'minutes': 15, 'action_token': token}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('action'), 'snooze')
        self.assertIn('snooze_until', data)

        # Verify task is updated in DB
        self.task.refresh_from_db()
        self.assertEqual(self.task.metadata.get('alarm_status'), 'snoozed')
        self.assertIsNotNone(self.task.metadata.get('next_retry_at'))

    def test_tampered_token_rejected(self):
        url = reverse('users:todo_reminder_action', kwargs={'task_id': self.task.id})
        response = self.client.post(
            url,
            data=json.dumps({'action': 'stop', 'action_token': 'fake_token_123'}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json().get('success'))

    def test_task_id_mismatch_token_rejected(self):
        signer = TimestampSigner(salt='abcd-reminder-action')
        token = signer.sign(f"99999:{self.user.id}")

        url = reverse('users:todo_reminder_action', kwargs={'task_id': self.task.id})
        response = self.client.post(
            url,
            data=json.dumps({'action': 'stop', 'action_token': token}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.json().get('success'))

    def test_deleted_task_or_account_returns_404(self):
        signer = TimestampSigner(salt='abcd-reminder-action')
        token = signer.sign("88888:99999")

        url = reverse('users:todo_reminder_action', kwargs={'task_id': 88888})
        response = self.client.post(
            url,
            data=json.dumps({'action': 'stop', 'action_token': token}),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.json().get('success'))


class NativeTwaCapabilityGatingTests(TestCase):
    """
    Focused regression tests verifying client capability gating in abcd-sound.js:
    A. Android Chrome standalone PWA -> NOT native TWA, does NOT set TWA mode, does NOT dispatch abcdalarm://
    B. Existing Play v4 TWA without bridge_token -> NOT native alarm mode, does NOT set TWA mode
    C. New TWA with valid bridge_token -> native alarm mode enabled, SET_TWA_MODE sent, abcdalarm:// dispatched
    """

    def _run_node_scenario(self, setup_js):
        import os
        import subprocess

        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        node_script = f"""
        const fs = require('fs');
        const code = fs.readFileSync('abcd_web/static/js/abcd-sound.js', 'utf8');

        const mockWindow = {{
            location: {{ search: '', pathname: '/', hash: '' }},
            history: {{ replaceState: () => {{}} }},
            matchMedia: () => ({{ matches: false }}),
            addEventListener: () => {{}},
            document: {{ readyState: 'complete', addEventListener: () => {{}} }}
        }};
        const mockSessionStorage = new Map();
        const sessionStorageObj = {{
            getItem: (k) => mockSessionStorage.get(k) || null,
            setItem: (k, v) => mockSessionStorage.set(k, String(v)),
            removeItem: (k) => mockSessionStorage.delete(k)
        }};
        const mockLocalStorage = new Map();
        const localStorageObj = {{
            getItem: (k) => mockLocalStorage.get(k) || null,
            setItem: (k, v) => mockLocalStorage.set(k, String(v))
        }};
        const iframeSources = [];
        const mockDoc = {{
            referrer: '',
            readyState: 'complete',
            addEventListener: () => {{}},
            createElement: (tag) => {{
                const el = {{ style: {{}} }};
                Object.defineProperty(el, 'src', {{
                    set: (v) => iframeSources.push(v),
                    get: () => iframeSources[iframeSources.length - 1]
                }});
                return el;
            }},
            body: {{ appendChild: () => {{}} }},
            getElementById: () => null
        }};
        const swMessages = [];
        const mockNavigator = {{
            userAgent: 'Mozilla/5.0',
            serviceWorker: {{
                controller: {{
                    postMessage: (msg) => swMessages.push(msg)
                }},
                addEventListener: () => {{}}
            }}
        }};

        {setup_js}

        const futureTime = new Date(Date.now() + 3600000).toISOString();
        const context = {{
            window: mockWindow,
            document: mockDoc,
            navigator: mockNavigator,
            sessionStorage: sessionStorageObj,
            localStorage: localStorageObj,
            fetch: () => Promise.resolve({{
                ok: true,
                json: () => Promise.resolve({{
                    status: 'ok',
                    reminders: [
                        {{ id: 101, title: 'Test Task', recurrence: 'once', fire_at: futureTime, is_alarm: true, action_token: 'token123' }}
                    ]
                }})
            }}),
            console: {{ debug: () => {{}}, log: () => {{}}, error: () => {{}}, warn: () => {{}} }},
            setTimeout: (fn) => fn(),
            setInterval: () => {{}},
            URLSearchParams: URLSearchParams,
            Date: Date,
            encodeURIComponent: encodeURIComponent
        }};

        const vm = require('vm');
        vm.createContext(context);
        vm.runInContext(code, context);

        context.window.checkGlobalDueAlarms();

        setTimeout(() => {{
            console.log(JSON.stringify({{
                isNativeActive: context.window.isNativeAlarmTwaActive(),
                swMessagesCount: swMessages.length,
                iframeSourcesCount: iframeSources.length,
                iframeSources: iframeSources,
                iframeSource: iframeSources[0] || null
            }}));
        }}, 30);
        """
        res = subprocess.run(
            ["node", "-e", node_script],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        self.assertEqual(res.returncode, 0, f"Node script failed: {res.stderr}")
        return json.loads(res.stdout.strip())

    def test_scenario_a_android_chrome_standalone_pwa_is_not_native_twa(self):
        setup_js = """
        mockNavigator.userAgent = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36';
        mockWindow.matchMedia = (q) => ({ matches: q.includes('display-mode: standalone') });
        """
        data = self._run_node_scenario(setup_js)
        self.assertFalse(data["isNativeActive"], "Android standalone PWA must not be identified as native alarm TWA")
        self.assertEqual(data["swMessagesCount"], 0, "PWA must not set SET_TWA_MODE in Service Worker")
        self.assertEqual(data["iframeSourcesCount"], 0, "PWA must not dispatch abcdalarm://")

    def test_scenario_b_play_store_v4_twa_without_bridge_token_is_not_native_alarm(self):
        setup_js = """
        mockNavigator.userAgent = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36';
        mockDoc.referrer = 'android-app://in.abcdcampus.app';
        mockWindow.location.search = '?pwa_app=1';
        """
        data = self._run_node_scenario(setup_js)
        self.assertFalse(data["isNativeActive"], "Play Store v4 without bridge_token must not activate native alarm mode")
        self.assertEqual(data["swMessagesCount"], 0, "Play Store v4 must not set SET_TWA_MODE in Service Worker")
        self.assertEqual(data["iframeSourcesCount"], 0, "Play Store v4 must not dispatch abcdalarm://")

    def test_scenario_c_new_twa_with_valid_bridge_token_activates_native_alarm(self):
        setup_js = """
        mockNavigator.userAgent = 'Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36';
        mockDoc.referrer = 'android-app://in.abcdcampus.app';
        mockWindow.location.search = '?pwa_app=1&bridge_token=auth-uuid-test-999';
        """
        data = self._run_node_scenario(setup_js)
        self.assertTrue(data["isNativeActive"], "New TWA with bridge_token must activate native alarm mode")
        self.assertEqual(data["swMessagesCount"], 1, "New TWA must notify Service Worker of SET_TWA_MODE")
        self.assertEqual(data["iframeSourcesCount"], 2, "New TWA must dispatch abcdalarm://reconcile and abcdalarm://schedule")
        self.assertTrue(any("abcdalarm://reconcile" in s for s in data["iframeSources"]), "Must dispatch reconcile")
        self.assertTrue(any("abcdalarm://schedule" in s for s in data["iframeSources"]), "Must dispatch schedule")
        self.assertTrue(all("bridge_token=auth-uuid-test-999" in s for s in data["iframeSources"]), "All dispatches must preserve bridge_token")


class ReminderSaveEndpointsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='save_endpoint_user', password='password123')
        self.client.login(username='save_endpoint_user', password='password123')
        from users.models import Course
        self.course = Course.objects.create(title='Python Mastery', description='Learn Python')

    def test_todo_add_reminder_success(self):
        future_dt = timezone.localtime(timezone.now()) + timedelta(hours=2)
        payload = {
            'title': 'Test Add Reminder',
            'note': 'Test Note',
            'recurrence': 'once',
            'fire_at': future_dt.isoformat(),
            'alarm_enabled': True,
            'email_notify': False
        }
        res = self.client.post(
            reverse('users:todo_add_reminder'),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertIn('task_id', data)
        self.assertTrue(TodoTask.objects.filter(id=data['task_id'], user=self.user).exists())

    def test_todo_update_reminder_success(self):
        future_dt = timezone.localtime(timezone.now()) + timedelta(hours=3)
        task = TodoTask.objects.create(
            user=self.user,
            category='REMINDER',
            metadata={'title': 'Original Title', 'recurrence': 'once'}
        )
        payload = {
            'title': 'Updated Title',
            'note': 'Updated Note',
            'recurrence': 'once',
            'date': future_dt.strftime('%Y-%m-%d'),
            'time': future_dt.strftime('%H:%M'),
            'alarm_enabled': False
        }
        res = self.client.post(
            reverse('users:todo_update_reminder', kwargs={'task_id': task.id}),
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        task.refresh_from_db()
        self.assertEqual(task.metadata.get('title'), 'Updated Title')
        self.assertFalse(task.metadata.get('alarm_enabled'))

    def test_save_learning_reminder_success(self):
        future_dt = timezone.now() + timedelta(hours=4)
        payload = {
            'title': 'Study Python Basics',
            'recurrence': 'once',
            'reminder_time': future_dt.isoformat()
        }
        res = self.client.post(
            f'/api/courses/{self.course.id}/reminder/',
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get('success'))
        self.assertIn('reminder', data)
        self.assertEqual(data['reminder']['title'], 'Study Python Basics')

