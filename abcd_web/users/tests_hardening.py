import io
from PIL import Image
from unittest.mock import patch
from datetime import datetime, timedelta
from django.test import TestCase, RequestFactory
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.core.cache import cache
from django.utils import timezone
from users.models import StudentProfile, Complaint
from users.forms import ComplaintForm
from users.utils import sanitize_and_prepare_image, MAX_IMAGE_PIXELS
from users.views import upload_profile_photo, student_complaints_view


def create_test_image(width=100, height=100, format='JPEG', color=(255, 0, 0)):
    """Helper to generate in-memory test image bytes."""
    buf = io.BytesIO()
    img = Image.new('RGB', (width, height), color=color)
    img.save(buf, format=format)
    return buf.getvalue()


class ImageGuardTests(TestCase):
    def test_sanitize_valid_small_image(self):
        img_bytes = create_test_image(width=50, height=50, format='JPEG')
        cleaned_bytes, ext = sanitize_and_prepare_image(img_bytes, max_size_mb=5)
        self.assertEqual(ext, 'jpg')
        self.assertGreater(len(cleaned_bytes), 0)

    def test_file_size_exceeded_raises_validation_error(self):
        large_bytes = b'X' * (6 * 1024 * 1024)  # 6MB
        with self.assertRaises(ValidationError) as ctx:
            sanitize_and_prepare_image(large_bytes, max_size_mb=5)
        self.assertIn("5MB", str(ctx.exception))

    def test_decompression_bomb_guard_triggers(self):
        # Generate 100x100 = 10,000 pixels, but set max_pixels=500
        img_bytes = create_test_image(width=100, height=100, format='JPEG')
        with self.assertRaises(ValidationError) as ctx:
            sanitize_and_prepare_image(img_bytes, max_pixels=500)
        self.assertTrue(
            "abnormally large" in str(ctx.exception) or "maximum allowed limit" in str(ctx.exception)
        )

    def test_exif_metadata_is_stripped(self):
        # Create image with custom EXIF tag
        img = Image.new('RGB', (50, 50), color=(0, 255, 0))
        exif = img.getexif()
        exif[0x010E] = "Secret Camera Owner Metadata"  # ImageDescription tag
        buf = io.BytesIO()
        img.save(buf, format='JPEG', exif=exif)

        # Sanitize
        cleaned_bytes, ext = sanitize_and_prepare_image(buf.getvalue(), max_size_mb=5)

        # Inspect resulting image
        with Image.open(io.BytesIO(cleaned_bytes)) as cleaned_img:
            result_exif = cleaned_img.getexif()
            self.assertNotIn(0x010E, result_exif)


class ComplaintsHardeningTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='complaint_tester', password='password123')
        self.student = StudentProfile.objects.create(
            user=self.user,
            full_name='Complaint Tester',
            mobile_number='9876543220'
        )
        self.factory = RequestFactory()

    def test_complaint_form_rejects_oversized_image(self):
        oversized = SimpleUploadedFile("big.jpg", b'0' * (6 * 1024 * 1024), content_type="image/jpeg")
        form = ComplaintForm(
            data={"subject": Complaint.SUBJECT_WIFI, "message": "Test complaint"},
            files={"image1": oversized}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("image1", form.errors)

    def test_complaint_daily_limit_blocks_excessive_submissions(self):
        today = timezone.now()
        # Seed 5 complaints submitted today
        for i in range(5):
            Complaint.objects.create(
                student=self.student,
                role='student',
                subject=Complaint.SUBJECT_NOISE,
                message=f"Complaint #{i+1}",
                created_at=today
            )

        # Attempt 6th complaint via view
        request = self.factory.post('/complaints/', {
            'subject': Complaint.SUBJECT_WIFI,
            'message': '6th complaint of the day'
        })
        request.user = self.user
        request.session = {'active_dashboard': 'student'}

        # Mock messages framework
        with patch('django.contrib.messages.error') as mock_msg:
            response = student_complaints_view(request)
            self.assertEqual(response.status_code, 302)  # Redirected
            self.assertTrue(mock_msg.called)
            self.assertIn("Daily limit reached", str(mock_msg.call_args))


class ProfilePhotoRateLimitTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username='photo_rate_user', password='password123')
        self.staff_user = User.objects.create_user(username='photo_staff_user', password='password123', is_staff=True)
        self.student = StudentProfile.objects.create(
            user=self.user,
            full_name='Photo Rate Student',
            mobile_number='9876543221'
        )
        self.factory = RequestFactory()

    def test_cooldown_between_photo_uploads(self):
        img_bytes = create_test_image(width=50, height=50)
        uploaded = SimpleUploadedFile("avatar1.jpg", img_bytes, content_type="image/jpeg")

        # 1st request succeeds
        request1 = self.factory.post(f'/api/student/{self.student.id}/photo/', {'photo': uploaded})
        request1.user = self.user
        response1 = upload_profile_photo(request1, self.student.id)
        self.assertEqual(response1.status_code, 200)

        # Immediate 2nd request is rate limited (cooldown)
        uploaded2 = SimpleUploadedFile("avatar2.jpg", img_bytes, content_type="image/jpeg")
        request2 = self.factory.post(f'/api/student/{self.student.id}/photo/', {'photo': uploaded2})
        request2.user = self.user
        response2 = upload_profile_photo(request2, self.student.id)
        self.assertEqual(response2.status_code, 429)
        self.assertIn("10 seconds", response2.content.decode())

    def test_daily_photo_update_limit(self):
        img_bytes = create_test_image(width=50, height=50)
        daily_key = f"photo_daily_count_user_{self.user.id}_{timezone.localdate().isoformat()}"
        # Set daily count already to 10
        cache.set(daily_key, 10, timeout=86400)

        uploaded = SimpleUploadedFile("avatar.jpg", img_bytes, content_type="image/jpeg")
        request = self.factory.post(f'/api/student/{self.student.id}/photo/', {'photo': uploaded})
        request.user = self.user
        response = upload_profile_photo(request, self.student.id)

        self.assertEqual(response.status_code, 429)
        self.assertIn("maximum 10 changes per day", response.content.decode())

    def test_staff_exempt_from_rate_limits(self):
        img_bytes = create_test_image(width=50, height=50)
        daily_key = f"photo_daily_count_user_{self.staff_user.id}_{timezone.localdate().isoformat()}"
        cooldown_key = f"photo_cooldown_user_{self.staff_user.id}"
        cache.set(daily_key, 50, timeout=86400)
        cache.set(cooldown_key, True, timeout=60)

        uploaded = SimpleUploadedFile("staff_upload.jpg", img_bytes, content_type="image/jpeg")
        request = self.factory.post(f'/api/student/{self.student.id}/photo/', {'photo': uploaded})
        request.user = self.staff_user
        response = upload_profile_photo(request, self.student.id)

        # Staff bypasses rate limits
        self.assertEqual(response.status_code, 200)
