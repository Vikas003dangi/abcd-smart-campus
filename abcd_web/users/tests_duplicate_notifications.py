# users/tests_duplicate_notifications.py
import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone
from users.models import PushSubscription, StudentProfile, Payment, FeeTransaction, Notification
from users.notifications import create_notification, send_push

User = get_user_model()


class DuplicateNotificationsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.user = User.objects.create_user(username='dup_test_user', password='password123', email='dup@test.com')
        self.teacher = User.objects.create_user(username='dup_teacher', password='password123', is_staff=True)
        self.student = StudentProfile.objects.create(
            user=self.user,
            full_name='Duplicate Test Student',
            status='admitted',
            service_type='Library',
            mobile_number='9876543210'
        )

    def tearDown(self):
        cache.clear()

    @patch('users.notifications.send_push')
    def test_create_notification_sends_push_exactly_once(self, mock_send_push):
        """create_notification must trigger send_push exactly 1 time per notification event."""
        notif = create_notification(
            user=self.user,
            title='Test Notification Title',
            message='Test Notification Message',
            link='/test/',
            category='general',
            tag='test-tag-unique-1'
        )
        self.assertIsNotNone(notif)
        self.assertEqual(mock_send_push.call_count, 1)

    def test_subscription_upsert_and_max_two_limit(self):
        """save_push_subscription must upsert by endpoint and prune user subscriptions to at most 2."""
        self.client.login(username='dup_test_user', password='password123')

        # 1. First subscription
        p1 = {'endpoint': 'https://fcm.googleapis.com/fcm/send/token1', 'keys': {'auth': 'a1', 'p256dh': 'p1'}}
        res1 = self.client.post('/api/save-push-subscription/', data=json.dumps(p1), content_type='application/json')
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 1)

        # 2. Re-saving first subscription (upsert - should not duplicate)
        res1_again = self.client.post('/api/save-push-subscription/', data=json.dumps(p1), content_type='application/json')
        self.assertEqual(res1_again.status_code, 200)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 1)

        # 3. Second subscription (e.g. TWA)
        p2 = {'endpoint': 'https://fcm.googleapis.com/fcm/send/token2', 'keys': {'auth': 'a2', 'p256dh': 'p2'}, 'client_type': 'twa'}
        res2 = self.client.post('/api/save-push-subscription/', data=json.dumps(p2), content_type='application/json')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 2)

        # 4. Third subscription (e.g. desktop) -> must prune oldest so count never exceeds 2
        p3 = {'endpoint': 'https://fcm.googleapis.com/fcm/send/token3', 'keys': {'auth': 'a3', 'p256dh': 'p3'}, 'client_type': 'desktop'}
        res3 = self.client.post('/api/save-push-subscription/', data=json.dumps(p3), content_type='application/json')
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 2)
        # Token 1 should have been pruned
        self.assertFalse(PushSubscription.objects.filter(endpoint=p1['endpoint']).exists())
        self.assertTrue(PushSubscription.objects.filter(endpoint=p2['endpoint']).exists())
        self.assertTrue(PushSubscription.objects.filter(endpoint=p3['endpoint']).exists())

    @patch('pywebpush.webpush')
    def test_twa_aware_filtering_suppresses_mobile_browser_duplicate(self, mock_webpush):
        """When user has both an active TWA and a mobile browser subscription, send_push sends ONLY to TWA."""
        # Create TWA subscription
        sub_twa = PushSubscription.objects.create(
            user=self.user,
            endpoint='https://fcm.googleapis.com/fcm/send/twa_device_token',
            keys={'auth': 'auth_twa', 'p256dh': 'p256_twa'},
            client_type='twa'
        )
        # Create mobile browser subscription
        sub_browser = PushSubscription.objects.create(
            user=self.user,
            endpoint='https://fcm.googleapis.com/fcm/send/browser_device_token',
            keys={'auth': 'auth_browser', 'p256dh': 'p256_browser'},
            client_type='browser'
        )

        send_push(
            user=self.user,
            title='Receipt Alert',
            body='Payment of Rs 100 recorded',
            tag='test-receipt-tag-unique-99'
        )

        # webpush should be called exactly once for the TWA subscription
        self.assertEqual(mock_webpush.call_count, 1)
        call_kwargs = mock_webpush.call_args[1]
        self.assertEqual(call_kwargs['subscription_info']['endpoint'], sub_twa.endpoint)

    @patch('pywebpush.webpush')
    def test_per_notification_cache_dedupe_prevents_double_firing(self, mock_webpush):
        """Duplicate send_push calls with the same tag within 8s window must be suppressed by cache dedupe."""
        PushSubscription.objects.create(
            user=self.user,
            endpoint='https://fcm.googleapis.com/fcm/send/token_dedupe_test',
            keys={'auth': 'auth1', 'p256dh': 'p2561'},
            client_type='twa'
        )

        # First dispatch
        send_push(
            user=self.user,
            title='Fee Receipt',
            body='Payment of Rs 100',
            tag='fee-receipt-dedupe-tag-123'
        )
        self.assertEqual(mock_webpush.call_count, 1)

        # Immediate duplicate dispatch
        send_push(
            user=self.user,
            title='Fee Receipt',
            body='Payment of Rs 100',
            tag='fee-receipt-dedupe-tag-123'
        )
        # Call count should remain 1 (second was deduplicated)
        self.assertEqual(mock_webpush.call_count, 1)

    def test_fee_double_submit_idempotency_creates_one_transaction(self):
        """Simultaneous/repeated fee submission for the same student, teacher, amount, and month within 10s must be idempotent."""
        self.client.login(username='dup_teacher', password='password123')

        payload = {
            'actions': [{
                'action': 'add_fee',
                'month': 'October',
                'year': '2026',
                'amount': '500',
                'payment_date': '2026-10-04'
            }],
            'final_dispatch': True,
            'use_default_expiry': True
        }

        # First request
        url1 = reverse('users:process_fees', args=[self.student.id])
        res1 = self.client.post(
            url1,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 200)
        data1 = res1.json()
        self.assertEqual(data1.get('status'), 'success')

        # Assert 1 transaction and 1 notification created
        self.assertEqual(FeeTransaction.objects.filter(student=self.student).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.user, category='payment').count(), 1)

        # Second rapid request (e.g. mobile double tap)
        res2 = self.client.post(
            url1,
            data=json.dumps(payload),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()
        self.assertEqual(data2.get('status'), 'success')
        self.assertIn('duplicate', data2.get('message', '').lower())

        # Still exactly 1 transaction and 1 notification
        self.assertEqual(FeeTransaction.objects.filter(student=self.student).count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.user, category='payment').count(), 1)

    def test_fee_idempotency_does_not_block_second_student(self):
        """Idempotency lock must not block fee submission for a different student."""
        self.client.login(username='dup_teacher', password='password123')

        user2 = User.objects.create_user(username='student_b_user', password='password123')
        student2 = StudentProfile.objects.create(
            user=user2,
            full_name='Student B',
            status='admitted',
            service_type='Library',
            mobile_number='9876543211'
        )

        payload_student1 = {
            'actions': [{'action': 'add_fee', 'month': 'November', 'year': '2026', 'amount': '500'}],
            'final_dispatch': True
        }
        payload_student2 = {
            'actions': [{'action': 'add_fee', 'month': 'November', 'year': '2026', 'amount': '500'}],
            'final_dispatch': True
        }

        # Submit for student 1
        url1 = reverse('users:process_fees', args=[self.student.id])
        res1 = self.client.post(
            url1,
            data=json.dumps(payload_student1),
            content_type='application/json'
        )
        self.assertEqual(res1.status_code, 200)

        # Immediately submit for student 2 (must succeed and NOT be blocked)
        url2 = reverse('users:process_fees', args=[student2.id])
        res2 = self.client.post(
            url2,
            data=json.dumps(payload_student2),
            content_type='application/json'
        )
        self.assertEqual(res2.status_code, 200)
        self.assertNotIn('duplicate', res2.json().get('message', '').lower())
        self.assertEqual(FeeTransaction.objects.filter(student=student2).count(), 1)

    def test_dedupe_push_subscriptions_management_command(self):
        """dedupe_push_subscriptions command must be DRY RUN by default and delete down to 2 when --apply is passed."""
        # Create 4 subscriptions for self.user
        for i in range(1, 5):
            PushSubscription.objects.create(
                user=self.user,
                endpoint=f'https://fcm.googleapis.com/fcm/send/cmd_test_{i}',
                keys={'auth': f'a{i}', 'p256dh': f'p{i}'},
                client_type='browser' if i % 2 == 0 else 'twa'
            )

        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 4)

        # 1. DRY RUN
        call_command('dedupe_push_subscriptions')
        # Subscriptions should remain 4
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 4)

        # 2. APPLY
        call_command('dedupe_push_subscriptions', apply=True)
        # Should be reduced to at most 2
        self.assertEqual(PushSubscription.objects.filter(user=self.user).count(), 2)
