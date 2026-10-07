"""
users/tests_auto_reply.py
=========================
Comprehensive test suite for Phase 3 Smart Auto-Reply in Guidy.

Test Matrix:
1. User messages ABCD Asst. -> 5 min pass -> auto-reply posted.
2. User messages Sandeep Sir -> 15 min pass -> auto-reply posted.
3. Owner replies before timer -> auto-reply cancelled (human_replied_first=True).
4. User sends 5 messages in 2 minutes -> only ONE auto-reply.
5. User sends message after 6 hours -> new auto-reply allowed.
6. Staff/teacher messages owner -> NO auto-reply (only students/alumni/guests).
7. Emergency keywords -> tele-MANAS reply (14416 / 112) + flagged in admin.
8. Payment dispute -> human-handoff reply with phone (9827662450).
9. Rotation: 3 messages over separate days get 3 different variants without back-to-back repetition.
10. Bot bubble renders differently in Guidy (auto-reply CSS & bot badge).
11. Admin toggle turns it off -> no reply even after 15 min.
"""

from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.utils import timezone
from users.models import (
    DirectChatSession, Message, AutoReplyConfig, AutoReplyLog,
    StudentProfile, TeacherProfile, Notification
)
from users.auto_reply import (
    classify_message, process_due_auto_replies,
    get_or_create_auto_reply_config,
    ABCD_ASST_EMAIL, SANDEEP_SIR_EMAIL, OFFICE_PHONE
)


class AutoReplyEngineTests(TestCase):
    def setUp(self):
        # Create ABCD Asst
        self.asst_user = User.objects.create_user(
            username='abcd_asst',
            email=ABCD_ASST_EMAIL,
            password='Password123!',
            first_name='ABCD',
            last_name='Assistant',
            is_staff=True,
            is_superuser=True
        )
        # Create Sandeep Sir
        self.sandeep_user = User.objects.create_user(
            username='sandeepananda',
            email=SANDEEP_SIR_EMAIL,
            password='Password123!',
            first_name='Sandeep',
            last_name='Sir'
        )
        TeacherProfile.objects.create(
            user=self.sandeep_user,
            display_name='Sandeep Sir',
            mobile_number=OFFICE_PHONE
        )

        # Create regular student
        self.student_user = User.objects.create_user(
            username='student_raj',
            email='raj@example.com',
            password='Password123!',
            first_name='Raj',
            last_name='Kumar'
        )
        StudentProfile.objects.create(
            user=self.student_user,
            full_name='Raj Kumar',
            sex='Male',
            service_type='Library',
            mobile_number='9876543210',
            whatsapp_number='9876543210'
        )

        # Create teacher/staff sender
        self.staff_sender = User.objects.create_user(
            username='staff_priya',
            email='priya@example.com',
            password='Password123!',
            is_staff=True
        )

        # Direct chat sessions
        self.session_asst = DirectChatSession.objects.create(
            user1=self.student_user,
            user2=self.asst_user,
            is_active=True
        )
        self.session_sandeep = DirectChatSession.objects.create(
            user1=self.student_user,
            user2=self.sandeep_user,
            is_active=True
        )

        # Enable auto-reply for test accounts
        c1 = get_or_create_auto_reply_config(self.asst_user)
        c1.is_enabled = True
        c1.save()

        c2 = get_or_create_auto_reply_config(self.sandeep_user)
        c2.is_enabled = True
        c2.save()

        self.client = Client()

    def test_01_user_messages_abcd_asst_5min_pass_auto_reply_posted(self):
        """User messages ABCD Asst. -> 5 min pass -> auto-reply posted."""
        self.client.force_login(self.student_user)
        resp = self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
            'content': 'Namaste, what are the library timings today?'
        })
        self.assertEqual(resp.status_code, 200)

        # Pending log created with due_at ~ 5 min
        log = AutoReplyLog.objects.filter(direct_session=self.session_asst, status='pending').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.account, self.asst_user)
        self.assertEqual(log.sender, self.student_user)
        self.assertEqual(log.detected_topic, 'timings')

        # Fast forward 4 minutes: should not send yet
        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=4)):
            sent = process_due_auto_replies()
            self.assertEqual(sent, 0)
            self.assertEqual(Message.objects.filter(direct_session=self.session_asst, sender=self.asst_user).count(), 0)

        # Fast forward 5 minutes 10 seconds: should send
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=5, seconds=10)):
            sent = process_due_auto_replies()
            self.assertEqual(sent, 1)

            log.refresh_from_db()
            self.assertEqual(log.status, 'sent')
            self.assertIsNotNone(log.reply_message)
            self.assertTrue(log.reply_message.is_auto_reply)
            self.assertIn("ABCD Library", log.chosen_response)
            self.assertIn("8:00 AM to 8:30 PM", log.chosen_response)

    def test_02_user_messages_sandeep_sir_15min_pass_auto_reply_posted(self):
        """User messages Sandeep Sir -> 15 min pass -> auto-reply posted."""
        self.client.force_login(self.student_user)
        resp = self.client.post(f'/guidy/direct/{self.session_sandeep.id}/send/', {
            'content': 'Sir, can I get seat availability for ground floor evening shift?'
        })
        self.assertEqual(resp.status_code, 200)

        log = AutoReplyLog.objects.filter(direct_session=self.session_sandeep, status='pending').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.detected_topic, 'seats')

        now = timezone.now()
        # Fast forward 10 minutes: should not send yet (Sandeep Sir wait is 15m)
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=10)):
            sent = process_due_auto_replies()
            self.assertEqual(sent, 0)

        # Fast forward 16 minutes: should send
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=16)):
            sent = process_due_auto_replies()
            self.assertEqual(sent, 1)
            reply = Message.objects.filter(direct_session=self.session_sandeep, sender=self.sandeep_user).first()
            self.assertIsNotNone(reply)
            self.assertTrue(reply.is_auto_reply)
            self.assertEqual(reply.auto_reply_topic, 'seats')

    def test_03_owner_replies_before_timer_auto_reply_cancelled(self):
        """Owner replies before timer -> auto-reply cancelled."""
        self.client.force_login(self.student_user)
        self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
            'content': 'Hello, I have a doubt regarding admission fees.'
        })

        log = AutoReplyLog.objects.filter(direct_session=self.session_asst, status='pending').first()
        self.assertIsNotNone(log)

        # Owner replies manually after 2 minutes
        self.client.force_login(self.asst_user)
        resp = self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
            'content': 'Hello Raj, I am looking into your account now.'
        })
        self.assertEqual(resp.status_code, 200)

        log.refresh_from_db()
        self.assertEqual(log.status, 'human_replied')
        self.assertTrue(log.human_replied_first)

        # Advance past 10 minutes and run sweep: should NOT send auto reply
        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=10)):
            sent = process_due_auto_replies()
            self.assertEqual(sent, 0)

    def test_04_user_sends_5_messages_in_2_minutes_only_one_auto_reply(self):
        """User sends 5 messages in 2 minutes -> only ONE auto-reply."""
        self.client.force_login(self.student_user)
        for i in range(5):
            self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
                'content': f'Message number {i+1} regarding syllabus'
            })

        # Exactly 1 pending log should exist
        logs = AutoReplyLog.objects.filter(direct_session=self.session_asst, status='pending')
        self.assertEqual(logs.count(), 1)

        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=6)):
            sent = process_due_auto_replies()
            self.assertEqual(sent, 1)

        replies = Message.objects.filter(direct_session=self.session_asst, sender=self.asst_user, is_auto_reply=True)
        self.assertEqual(replies.count(), 1)

    def test_05_user_sends_message_after_6_hours_new_auto_reply_allowed(self):
        """User sends message after 6 hours -> new auto-reply allowed."""
        self.client.force_login(self.student_user)
        self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
            'content': 'First query in the morning: library timings'
        })

        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=6)):
            process_due_auto_replies()

        self.assertEqual(AutoReplyLog.objects.filter(direct_session=self.session_asst, status='sent').count(), 1)

        # Message after 2 hours (within 6h cooldown): should CREATE new pending log (cooldown removed per user request)
        with patch('django.utils.timezone.now', return_value=now + timedelta(hours=2)):
            self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
                'content': 'Second query 2 hours later'
            })
            self.assertEqual(AutoReplyLog.objects.filter(direct_session=self.session_asst, status='pending').count(), 1)
            
            with patch('django.utils.timezone.now', return_value=now + timedelta(hours=2, minutes=6)):
                process_due_auto_replies()
                self.assertEqual(AutoReplyLog.objects.filter(direct_session=self.session_asst, status='sent').count(), 2)

        # Message after 6 hours 15 minutes: allowed!
        with patch('django.utils.timezone.now', return_value=now + timedelta(hours=6, minutes=15)):
            self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
                'content': 'Evening query after 6 hours'
            })
            self.assertEqual(AutoReplyLog.objects.filter(direct_session=self.session_asst, status='pending').count(), 1)

            # Advance 6 minutes to let due timer fire
            with patch('django.utils.timezone.now', return_value=now + timedelta(hours=6, minutes=22)):
                sent = process_due_auto_replies()
                self.assertEqual(sent, 1)
                self.assertEqual(AutoReplyLog.objects.filter(direct_session=self.session_asst, status='sent').count(), 3)

    def test_06_staff_messages_owner_no_auto_reply(self):
        """Staff/teacher messages owner -> NO auto-reply (only students/alumni/guests)."""
        session_staff = DirectChatSession.objects.create(
            user1=self.staff_sender,
            user2=self.asst_user,
            is_active=True
        )
        self.client.force_login(self.staff_sender)
        resp = self.client.post(f'/guidy/direct/{session_staff.id}/send/', {
            'content': 'Sandeep sir, please check teacher timetable updates.'
        })
        self.assertEqual(resp.status_code, 200)

        # Should NOT queue any auto reply for staff
        self.assertFalse(AutoReplyLog.objects.filter(direct_session=session_staff).exists())

    def test_07_emergency_keywords_tele_manas_and_flagged_admin(self):
        """Emergency keywords -> tele-MANAS reply (14416 / 112) + flagged in admin."""
        self.client.force_login(self.student_user)
        self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
            'content': 'I am feeling severe anxiety and depression, I cant take this anymore, help me please'
        })

        log = AutoReplyLog.objects.filter(direct_session=self.session_asst, status='pending').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.detected_topic, 'emergency')
        self.assertTrue(log.flagged_emergency)

        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=6)):
            process_due_auto_replies()

        log.refresh_from_db()
        self.assertEqual(log.status, 'sent')
        self.assertTrue(log.flagged_emergency)
        self.assertIn("14416", log.chosen_response)
        self.assertIn("8109455803", log.chosen_response)
        self.assertIn("Tele-MANAS", log.chosen_response)
        # Verify real in-app urgent Notification was created for human mentor
        self.assertTrue(Notification.objects.filter(user=self.asst_user, category="guidy").exists())

    def test_08_payment_dispute_human_handoff_with_phone(self):
        """Payment dispute -> human-handoff reply with phone."""
        self.client.force_login(self.student_user)
        self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
            'content': 'My payment failed and money was deducted twice. Please refund wrong amount!'
        })

        log = AutoReplyLog.objects.filter(direct_session=self.session_asst, status='pending').first()
        self.assertIsNotNone(log)
        self.assertEqual(log.detected_topic, 'fees_dispute')

        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=6)):
            process_due_auto_replies()

        log.refresh_from_db()
        self.assertIn(OFFICE_PHONE, log.chosen_response)
        self.assertTrue(
            "transaction" in log.chosen_response.lower() or
            "audited" in log.chosen_response.lower()
        )

    def test_09_rotation_three_different_variants_without_repetition(self):
        """Rotation: 3 messages over separate times get 3 different variants without back-to-back repetition."""
        responses = []
        now = timezone.now()

        for day in range(3):
            current_time = now + timedelta(days=day)
            with patch('django.utils.timezone.now', return_value=current_time):
                self.client.force_login(self.student_user)
                self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
                    'content': 'Hi there, quick question!'
                })

            with patch('django.utils.timezone.now', return_value=current_time + timedelta(minutes=6)):
                process_due_auto_replies()
                last_reply = Message.objects.filter(
                    direct_session=self.session_asst,
                    sender=self.asst_user,
                    is_auto_reply=True
                ).order_by('-timestamp').first()
                self.assertIsNotNone(last_reply)
                responses.append(last_reply.content)

        self.assertEqual(len(responses), 3)
        # All 3 variants distinct
        self.assertEqual(len(set(responses)), 3)
        # Never identical back-to-back
        self.assertNotEqual(responses[0], responses[1])
        self.assertNotEqual(responses[1], responses[2])

    def test_10_bot_bubble_renders_differently_in_guidy(self):
        """Bot bubble renders with auto-reply-bubble and bot badge in Guidy HTML/JSON."""
        # Create an auto-reply message
        msg = Message.objects.create(
            direct_session=self.session_asst,
            sender=self.asst_user,
            content="Namaste! Regarding fees and payment slips: check your student portal.",
            is_auto_reply=True,
            auto_reply_topic='fees'
        )

        self.client.force_login(self.student_user)
        resp = self.client.get(f'/guidy/?direct={self.session_asst.id}')
        self.assertEqual(resp.status_code, 200)
        content_html = resp.content.decode('utf-8')

        # Check template styling elements
        self.assertIn('auto-reply-bubble', content_html)
        self.assertIn('Smart Auto-Reply', content_html)
        self.assertIn('Automated response', content_html)

        # Check JSON API endpoint
        poll_resp = self.client.get(f'/guidy/direct/{self.session_asst.id}/poll/?after=0')
        self.assertEqual(poll_resp.status_code, 200)
        poll_data = poll_resp.json()
        self.assertTrue(poll_data['messages'][0]['is_auto_reply'])
        self.assertEqual(poll_data['messages'][0]['auto_reply_topic'], 'fees')

    def test_11_admin_toggle_turns_it_off(self):
        """Admin toggle turns it off -> no reply even after 15 min."""
        self.asst_user.email = "regular_account@abcd.com"
        self.asst_user.save()
        config = get_or_create_auto_reply_config(self.asst_user)
        config.is_enabled = False
        config.save()

        self.client.force_login(self.student_user)
        self.client.post(f'/guidy/direct/{self.session_asst.id}/send/', {
            'content': 'Namaste sir, need help with library seats.'
        })

        # Because disabled, no pending log should be scheduled
        self.assertFalse(AutoReplyLog.objects.filter(direct_session=self.session_asst, status='pending').exists())

        now = timezone.now()
        with patch('django.utils.timezone.now', return_value=now + timedelta(minutes=20)):
            sent = process_due_auto_replies()
            self.assertEqual(sent, 0)
            self.assertEqual(Message.objects.filter(direct_session=self.session_asst, is_auto_reply=True).count(), 0)
