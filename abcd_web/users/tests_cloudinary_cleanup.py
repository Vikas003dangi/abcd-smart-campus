from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
from io import StringIO
from django.test import TestCase, override_settings
from django.core.management import call_command
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth.models import User
from users.models import StudentProfile, Complaint, safe_delete_file_field
from users.admin import StudentProfileAdmin, ComplaintAdmin
from users.management.commands.cloudinary_orphans import (
    normalize_cloudinary_ref, get_active_db_identifiers
)


class CloudinarySignalsSafeDeletionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='test_clean_user', password='password123')
        self.student = StudentProfile.objects.create(
            user=self.user,
            full_name='Clean Test Student',
            mobile_number='9876543210'
        )

    @patch('users.models.safe_delete_file_field')
    def test_student_photo_update_triggers_post_save_cleanup(self, mock_safe_delete):
        # 1. Attach initial photo
        self.student.photo = SimpleUploadedFile("initial_photo.jpg", b"fake_bytes_1", content_type="image/jpeg")
        self.student.save()
        mock_safe_delete.reset_mock()

        # 2. Update photo with on_commit callback execution
        with self.captureOnCommitCallbacks(execute=True):
            self.student.photo = SimpleUploadedFile("updated_photo.jpg", b"fake_bytes_2", content_type="image/jpeg")
            self.student.save()

        # safe_delete_file_field should have been called for the old photo
        self.assertTrue(mock_safe_delete.called)

    @patch('users.models.safe_delete_file_field')
    def test_complaint_image_update_triggers_post_save_cleanup(self, mock_safe_delete):
        complaint = Complaint.objects.create(
            student=self.student,
            subject=Complaint.SUBJECT_WIFI,
            message="Wifi is down",
            image1=SimpleUploadedFile("wifi_old.jpg", b"fake_img_1", content_type="image/jpeg")
        )
        mock_safe_delete.reset_mock()

        # Update image1 with on_commit callback execution
        with self.captureOnCommitCallbacks(execute=True):
            complaint.image1 = SimpleUploadedFile("wifi_new.jpg", b"fake_img_2", content_type="image/jpeg")
            complaint.save()

        self.assertTrue(mock_safe_delete.called)

    @patch('users.models.safe_delete_file_field')
    def test_complaint_delete_cleans_up_images(self, mock_safe_delete):
        complaint = Complaint.objects.create(
            student=self.student,
            subject=Complaint.SUBJECT_CLEANING,
            message="Dirty corridor",
            image1=SimpleUploadedFile("corridor.jpg", b"fake_img_1", content_type="image/jpeg")
        )
        mock_safe_delete.reset_mock()

        complaint.delete()
        self.assertTrue(mock_safe_delete.called)


class AdminMediaCleanupMixinTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='admin_clean_user', password='password123')
        self.student = StudentProfile.objects.create(
            user=self.user,
            full_name='Admin Clean Student',
            mobile_number='9876543211'
        )

    @patch('users.models.safe_delete_file_field')
    def test_student_admin_delete_queryset_calls_individual_delete(self, mock_safe_delete):
        self.student.photo = SimpleUploadedFile("admin_photo.jpg", b"photo_bytes", content_type="image/jpeg")
        self.student.save()
        mock_safe_delete.reset_mock()

        admin_instance = StudentProfileAdmin(StudentProfile, None)
        qs = StudentProfile.objects.filter(id=self.student.id)
        admin_instance.delete_queryset(None, qs)

        self.assertFalse(StudentProfile.objects.filter(id=self.student.id).exists())
        self.assertTrue(mock_safe_delete.called)

    @patch('users.models.safe_delete_file_field')
    def test_complaint_admin_delete_queryset_calls_individual_delete(self, mock_safe_delete):
        complaint = Complaint.objects.create(
            student=self.student,
            subject=Complaint.SUBJECT_NOISE,
            message="Noise complaint",
            image1=SimpleUploadedFile("noise.jpg", b"noise_bytes", content_type="image/jpeg")
        )
        mock_safe_delete.reset_mock()

        admin_instance = ComplaintAdmin(Complaint, None)
        qs = Complaint.objects.filter(id=complaint.id)
        admin_instance.delete_queryset(None, qs)

        self.assertFalse(Complaint.objects.filter(id=complaint.id).exists())
        self.assertTrue(mock_safe_delete.called)


class CloudinaryOrphansCommandTests(TestCase):
    def test_normalize_cloudinary_ref(self):
        self.assertEqual(normalize_cloudinary_ref("media/photos/sample.jpg"), "photos/sample.jpg")
        self.assertEqual(normalize_cloudinary_ref("image/upload/v1234/test.png"), "v1234/test.png")
        self.assertEqual(normalize_cloudinary_ref("/complaints/test\\img.png"), "complaints/test/img.png")
        self.assertEqual(normalize_cloudinary_ref(""), "")

    @override_settings(
        CLOUDINARY_CLOUD_NAME='test_cloud',
        CLOUDINARY_API_KEY='test_key',
        CLOUDINARY_API_SECRET='test_secret'
    )
    @patch('cloudinary.uploader.destroy')
    @patch('cloudinary.api.resources')
    def test_cloudinary_orphans_dry_run_identifies_orphan_without_deleting(self, mock_resources, mock_destroy):
        # Create active student with a known photo name
        user = User.objects.create_user(username='active_orphan_test', password='password123')
        StudentProfile.objects.create(
            user=user,
            full_name='Active Student',
            mobile_number='9876543212',
            photo='student_photos/active_avatar.jpg'
        )

        old_date = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        recent_date = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()

        # Cloudinary returns resources for 'image', then empty for 'raw' and 'video'
        mock_resources.side_effect = [
            {
                'resources': [
                    {'public_id': 'student_photos/active_avatar', 'format': 'jpg', 'created_at': old_date, 'bytes': 100},
                    {'public_id': 'complaints/old_orphan_123', 'format': 'png', 'created_at': old_date, 'bytes': 200},
                    {'public_id': 'temp/recent_upload_456', 'format': 'jpg', 'created_at': recent_date, 'bytes': 300},
                ]
            },
            {'resources': []},
            {'resources': []}
        ]

        out = StringIO()
        call_command('cloudinary_orphans', stdout=out)
        output = out.getvalue()

        self.assertIn("DRY RUN (Simulated)", output)
        self.assertIn("Recent assets skipped (< 24h): 1", output)
        self.assertIn("Orphaned assets identified: 1", output)
        self.assertIn("complaints/old_orphan_123", output)
        self.assertFalse(mock_destroy.called)

    @override_settings(
        CLOUDINARY_CLOUD_NAME='test_cloud',
        CLOUDINARY_API_KEY='test_key',
        CLOUDINARY_API_SECRET='test_secret'
    )
    @patch('cloudinary.uploader.destroy')
    @patch('cloudinary.api.resources')
    def test_cloudinary_orphans_apply_with_confirm_deletes_orphan(self, mock_resources, mock_destroy):
        old_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        mock_resources.side_effect = [
            {
                'resources': [
                    {'public_id': 'abandoned_file_999', 'format': 'jpg', 'created_at': old_date, 'bytes': 500}
                ]
            },
            {'resources': []},
            {'resources': []}
        ]
        mock_destroy.return_value = {'result': 'ok'}

        out = StringIO()
        call_command('cloudinary_orphans', apply=True, confirm='DELETE', stdout=out)
        output = out.getvalue()

        self.assertIn("APPLY (Live Deletion)", output)
        self.assertIn("Successfully deleted 1 orphaned asset(s)", output)
        mock_destroy.assert_called_once_with('abandoned_file_999', resource_type='image')

    @override_settings(
        CLOUDINARY_CLOUD_NAME='test_cloud',
        CLOUDINARY_API_KEY='test_key',
        CLOUDINARY_API_SECRET='test_secret'
    )
    @patch('cloudinary.uploader.destroy')
    @patch('cloudinary.api.resources')
    def test_cloudinary_orphans_apply_without_confirm_aborts(self, mock_resources, mock_destroy):
        old_date = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        mock_resources.side_effect = [
            {
                'resources': [
                    {'public_id': 'abandoned_file_888', 'format': 'jpg', 'created_at': old_date, 'bytes': 500}
                ]
            },
            {'resources': []},
            {'resources': []}
        ]

        out = StringIO()
        call_command('cloudinary_orphans', apply=True, confirm='WRONG', stdout=out)
        output = out.getvalue()

        self.assertIn("Confirmation failed", output)
        self.assertFalse(mock_destroy.called)
