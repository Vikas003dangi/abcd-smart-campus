import os
import shutil
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from django.urls import reverse
from users.models import Message, GroupMessage, ChatSession, GroupChatSession, DirectChatSession

User = get_user_model()


class GuidyDownloadAttachmentTests(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='u1', email='u1@test.com', password='pass1234')
        self.user2 = User.objects.create_user(username='u2', email='u2@test.com', password='pass1234')
        self.stranger = User.objects.create_user(username='u3', email='u3@test.com', password='pass1234')

        # Create direct session between user1 and user2
        self.direct_session = DirectChatSession.objects.create(
            user1=self.user1,
            user2=self.user2,
            is_active=True
        )

        # Ensure temp test dir exists
        self.test_dir = os.path.join(settings.MEDIA_ROOT, 'guidy_temp')
        os.makedirs(self.test_dir, exist_ok=True)

        # Create test message with file
        self.uploaded_content = b"%PDF-1.4 dummy pdf binary content"
        self.file = SimpleUploadedFile("Receipt_123.pdf", self.uploaded_content, content_type="application/pdf")
        self.msg = Message.objects.create(
            direct_session=self.direct_session,
            sender=self.user1,
            content="Here is the receipt",
            message_type="document",
            file=self.file,
            file_name="Receipt_123.pdf"
        )
        # Also ensure local cached copy exists
        self.local_cache_path = os.path.join(self.test_dir, f"msg_{self.msg.id}_Receipt_123.pdf")
        with open(self.local_cache_path, 'wb') as f:
            f.write(self.uploaded_content)

        # Create group and group message
        self.group = GroupChatSession.objects.create(
            name="Study Group",
            created_by=self.user1,
            is_active=True
        )
        self.group.members.add(self.user1, self.user2)

        self.group_file = SimpleUploadedFile("Notes.pdf", b"%PDF-1.4 notes content", content_type="application/pdf")
        self.gmsg = GroupMessage.objects.create(
            group=self.group,
            sender=self.user2,
            content="Class notes",
            message_type="document",
            file=self.group_file,
            file_name="Notes.pdf"
        )
        self.group_cache_path = os.path.join(self.test_dir, f"gmsg_{self.gmsg.id}_Notes.pdf")
        with open(self.group_cache_path, 'wb') as f:
            f.write(b"%PDF-1.4 notes content")

    def tearDown(self):
        # Clean up test files
        if os.path.exists(self.local_cache_path):
            try:
                os.remove(self.local_cache_path)
            except Exception:
                pass
        if os.path.exists(self.group_cache_path):
            try:
                os.remove(self.group_cache_path)
            except Exception:
                pass

    def test_participant_can_download_direct_attachment(self):
        self.client.login(username='u2', password='pass1234')
        url = reverse('users:guidy_download_attachment', kwargs={'msg_id': self.msg.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment;', response.headers.get('Content-Disposition', ''))
        self.assertIn('Receipt_123.pdf', response.headers.get('Content-Disposition', ''))

    def test_stranger_cannot_download_direct_attachment(self):
        self.client.login(username='u3', password='pass1234')
        url = reverse('users:guidy_download_attachment', kwargs={'msg_id': self.msg.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_group_member_can_download_group_attachment(self):
        self.client.login(username='u1', password='pass1234')
        url = reverse('users:guidy_download_group_attachment', kwargs={'msg_id': self.gmsg.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('Notes.pdf', response.headers.get('Content-Disposition', ''))

    def test_non_group_member_cannot_download_group_attachment(self):
        self.client.login(username='u3', password='pass1234')
        url = reverse('users:guidy_download_group_attachment', kwargs={'msg_id': self.gmsg.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_expired_media_returns_404(self):
        self.msg.media_expired = True
        self.msg.save(update_fields=['media_expired'])
        self.client.login(username='u1', password='pass1234')
        url = reverse('users:guidy_download_attachment', kwargs={'msg_id': self.msg.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)
