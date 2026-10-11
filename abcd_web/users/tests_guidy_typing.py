from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.core.cache import cache
from django.urls import reverse
from users.models import DirectChatSession, GroupChatSession, ChatSession, GuidyBlock, Message, GroupMessage
from users.consumers import is_typing_allowed_for_chat
from asgiref.sync import async_to_sync
import time


class GuidyTypingIndicatorTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()

        # Users
        self.user1 = User.objects.create_user(username='rahul_user', first_name='Rahul', password='password123')
        self.user2 = User.objects.create_user(username='priya_user', first_name='Priya', password='password123')
        self.user3 = User.objects.create_user(username='aman_user', first_name='Aman', password='password123')
        self.stranger = User.objects.create_user(username='stranger_user', first_name='Stranger', password='password123')

        # 1-on-1 Direct Chat Session
        self.direct_session = DirectChatSession.objects.create(
            user1=self.user1,
            user2=self.user2,
            is_active=True
        )

        # Group Chat Session
        self.group_session = GroupChatSession.objects.create(
            name="Study Circle",
            created_by=self.user1,
            is_active=True
        )
        self.group_session.members.add(self.user1, self.user2, self.user3)

    def tearDown(self):
        cache.clear()

    def test_direct_chat_membership_and_authorization(self):
        """Only members can send typing. Non-members are rejected."""
        # Member 1 & 2 are authorized
        self.assertTrue(async_to_sync(is_typing_allowed_for_chat)(self.user1.id, 'direct', self.direct_session.id))
        self.assertTrue(async_to_sync(is_typing_allowed_for_chat)(self.user2.id, 'direct', self.direct_session.id))

        # Stranger is unauthorized
        cache.clear()
        self.assertFalse(async_to_sync(is_typing_allowed_for_chat)(self.stranger.id, 'direct', self.direct_session.id))

    def test_blocked_users_excluded_from_typing(self):
        """If user2 is blocked by user1, typing indicator must be disallowed."""
        cache.clear()
        self.assertTrue(async_to_sync(is_typing_allowed_for_chat)(self.user1.id, 'direct', self.direct_session.id))

        # Block user2
        GuidyBlock.objects.create(blocker=self.user1, blocked=self.user2)
        cache.clear()

        # Both sides disallowed from typing to each other
        self.assertFalse(async_to_sync(is_typing_allowed_for_chat)(self.user2.id, 'direct', self.direct_session.id))
        self.assertFalse(async_to_sync(is_typing_allowed_for_chat)(self.user1.id, 'direct', self.direct_session.id))

    def test_group_chat_membership(self):
        """Group typing is allowed for members and creator, disallowed for strangers."""
        cache.clear()
        self.assertTrue(async_to_sync(is_typing_allowed_for_chat)(self.user1.id, 'group', self.group_session.id))
        self.assertTrue(async_to_sync(is_typing_allowed_for_chat)(self.user2.id, 'group', self.group_session.id))
        self.assertTrue(async_to_sync(is_typing_allowed_for_chat)(self.user3.id, 'group', self.group_session.id))

        # Stranger cannot type in group
        cache.clear()
        self.assertFalse(async_to_sync(is_typing_allowed_for_chat)(self.stranger.id, 'group', self.group_session.id))

    def test_http_typing_endpoint_no_database_writes(self):
        """Typing signals must NEVER write to the database (messages count stays identical)."""
        initial_msg_count = Message.objects.count()
        initial_grp_msg_count = GroupMessage.objects.count()

        self.client.login(username='rahul_user', password='password123')
        response = self.client.post('/guidy/typing/', {
            'chat_type': 'direct',
            'session_id': self.direct_session.id,
            'is_typing': '1'
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json().get('success'))

        # Check DB write count: strictly 0
        self.assertEqual(Message.objects.count(), initial_msg_count)
        self.assertEqual(GroupMessage.objects.count(), initial_grp_msg_count)

    def test_http_typing_rate_limiting(self):
        """Rapid successive typing calls are throttled gracefully."""
        self.client.login(username='rahul_user', password='password123')

        # First signal passes
        r1 = self.client.post('/guidy/typing/', {
            'chat_type': 'direct',
            'session_id': self.direct_session.id,
            'is_typing': '1'
        })
        self.assertEqual(r1.status_code, 200)
        self.assertFalse(r1.json().get('throttled', False))

        # Immediate second signal within 2s is throttled
        r2 = self.client.post('/guidy/typing/', {
            'chat_type': 'direct',
            'session_id': self.direct_session.id,
            'is_typing': '1'
        })
        self.assertEqual(r2.status_code, 200)
        self.assertTrue(r2.json().get('throttled', False))

    def test_unauthorized_user_http_typing_rejected(self):
        """Non-members cannot send HTTP typing signals."""
        self.client.login(username='stranger_user', password='password123')
        response = self.client.post('/guidy/typing/', {
            'chat_type': 'direct',
            'session_id': self.direct_session.id,
            'is_typing': '1'
        })
        self.assertEqual(response.status_code, 403)

    def test_http_polling_returns_active_typing_users(self):
        """HTTP poll endpoint returns typing_users payload with first name and excludes self."""
        # User 1 sets typing status
        self.client.login(username='rahul_user', password='password123')
        self.client.post('/guidy/typing/', {
            'chat_type': 'direct',
            'session_id': self.direct_session.id,
            'is_typing': '1'
        })

        # User 2 polls direct chat -> sees User 1 typing
        self.client.login(username='priya_user', password='password123')
        poll_res = self.client.post(f'/guidy/direct/{self.direct_session.id}/poll/', {})
        self.assertEqual(poll_res.status_code, 200)
        data = poll_res.json()
        self.assertIn('typing_users', data)
        self.assertEqual(len(data['typing_users']), 1)
        self.assertEqual(data['typing_users'][0]['user_id'], self.user1.id)
        self.assertEqual(data['typing_users'][0]['first_name'], 'Rahul')

        # User 1 polls own chat -> does NOT see self typing
        self.client.login(username='rahul_user', password='password123')
        poll_res_self = self.client.post(f'/guidy/direct/{self.direct_session.id}/poll/', {})
        self.assertEqual(poll_res_self.status_code, 200)
        self.assertEqual(len(poll_res_self.json().get('typing_users', [])), 0)

    def test_group_polling_multiple_typings(self):
        """Group polling aggregates multiple typing users."""
        # Rahul (user1) and Priya (user2) type in group
        self.client.login(username='rahul_user', password='password123')
        self.client.post('/guidy/typing/', {
            'chat_type': 'group',
            'session_id': self.group_session.id,
            'is_typing': '1'
        })

        self.client.login(username='priya_user', password='password123')
        self.client.post('/guidy/typing/', {
            'chat_type': 'group',
            'session_id': self.group_session.id,
            'is_typing': '1'
        })

        # Aman (user3) polls group
        self.client.login(username='aman_user', password='password123')
        poll_res = self.client.post(f'/guidy/groups/{self.group_session.id}/poll/', {})
        self.assertEqual(poll_res.status_code, 200)
        data = poll_res.json()
        typings = data.get('typing_users', [])
        typing_ids = [t['user_id'] for t in typings]
        self.assertIn(self.user1.id, typing_ids)
        self.assertIn(self.user2.id, typing_ids)
        self.assertNotIn(self.user3.id, typing_ids)

    def test_rendered_html_contains_indicator_markup_and_css_variables(self):
        """Rendered guidy.html must contain the typing indicator markup and CSS variables."""
        self.client.login(username='rahul_user', password='password123')
        res = self.client.get(f'/guidy/?direct={self.direct_session.id}')
        self.assertEqual(res.status_code, 200)
        html = res.content.decode('utf-8')

        # Check Markup elements
        self.assertIn('id="guidyTypingIndicator"', html)
        self.assertIn('id="guidyTypingBubble"', html)
        self.assertIn('id="guidyTypingNames"', html)
        self.assertIn('class="g-typing-dots"', html)
        self.assertIn('class="g-typing-dot"', html)
        self.assertIn('id="guidyTypingAria"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertIn('sr-only', html)

        # Check CSS definitions & palette
        self.assertIn('.g-typing-indicator-row', html)
        self.assertIn('.g-typing-bubble', html)
        self.assertIn('.g-typing-names', html)
        self.assertIn('var(--g-primary-s', html)
        self.assertIn('var(--g-msg-in)', html)
        self.assertIn('body.dark-theme .g-typing-bubble', html)
        self.assertIn('body.dark-theme .g-typing-dot', html)
        self.assertIn('prefers-reduced-motion', html)
