# users/tests_alumni_deletion.py
import datetime
from unittest.mock import patch
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User
from django.urls import reverse
from users.models import StudentProfile, StudentAchievement


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    BREVO_API_KEY='',
    RESEND_API_KEY='',
    GMAIL_RELAY_URL=''
)
class AlumniDeletionTestCase(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Mock email dispatch so no external or SMTP attempts happen during tests
        cls.email_patcher = patch('users.email_service.send_html_email', return_value=True)
        cls.email_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.email_patcher.stop()
        super().tearDownClass()

    def setUp(self):
        self.client = Client()

        # Staff user (Teacher)
        self.staff_user = User.objects.create_user(
            username="teacher_test",
            email="teacher@test.com",
            password="TestPassword123!",
            is_staff=True
        )

        # Alumni-only user (no StudentProfile)
        self.alumni_only_user = User.objects.create_user(
            username="alumni_only_user",
            email="alumnionly@test.com",
            first_name="Alumni",
            last_name="Only",
            password="TestPassword123!"
        )
        self.alumni_only_ach = StudentAchievement.objects.create(
            user=self.alumni_only_user,
            first_name="Alumni",
            last_name="Only",
            about_yourself="Aspiring Officer",
            current_post="IAS Officer",
            selection_year=2024,
            working_city="Delhi",
            short_achievement="IAS 2024",
            gender="Male",
            dob=datetime.date(1998, 1, 1),
            services_used="library",
            experience_feedback="Great place",
            abcd_feedback="Helpful guidance",
            status="approved"
        )

        # Student + Alumni user
        self.both_user = User.objects.create_user(
            username="both_user",
            email="both@test.com",
            first_name="Both",
            last_name="User",
            password="TestPassword123!"
        )
        self.both_profile = StudentProfile.objects.create(
            user=self.both_user,
            mobile_number="9876543210"
        )
        self.both_ach = StudentAchievement.objects.create(
            user=self.both_user,
            first_name="Both",
            last_name="User",
            about_yourself="Bank PO",
            current_post="Probationary Officer",
            selection_year=2023,
            working_city="Mumbai",
            short_achievement="SBI PO",
            gender="Female",
            dob=datetime.date(1999, 5, 12),
            services_used="both",
            experience_feedback="Excellent coaching",
            abcd_feedback="Awesome environment",
            status="approved"
        )

    def test_delete_achievement_preserves_alumni_only_user(self):
        """Deleting achievement for an alumni-only user deletes the achievement but preserves the login User account."""
        self.client.force_login(self.staff_user)
        url = reverse("users:delete_achievement", kwargs={"pk": self.alumni_only_ach.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        # Achievement must be deleted
        self.assertFalse(StudentAchievement.objects.filter(pk=self.alumni_only_ach.pk).exists())
        # User credentials must be preserved
        self.assertTrue(User.objects.filter(pk=self.alumni_only_user.pk).exists())

    def test_delete_achievement_preserves_student_profile(self):
        """Deleting achievement for a user with both student profile and achievement deletes only achievement."""
        self.client.force_login(self.staff_user)
        url = reverse("users:delete_achievement", kwargs={"pk": self.both_ach.pk})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)

        # Achievement must be deleted
        self.assertFalse(StudentAchievement.objects.filter(pk=self.both_ach.pk).exists())
        # StudentProfile and User credentials must remain intact
        self.assertTrue(StudentProfile.objects.filter(pk=self.both_profile.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.both_user.pk).exists())

    def test_delete_student_view_scope_alumni(self):
        """Deleting with delete_scope='alumni' on a dual user deletes only achievement, keeping profile and user."""
        self.client.force_login(self.staff_user)
        url = reverse("users:delete_student", kwargs={"student_id": self.both_profile.pk})
        response = self.client.post(url, {"delete_scope": "alumni"})
        self.assertEqual(response.status_code, 302)

        # Achievement must be deleted
        self.assertFalse(StudentAchievement.objects.filter(pk=self.both_ach.pk).exists())
        # StudentProfile and User must remain intact
        self.assertTrue(StudentProfile.objects.filter(pk=self.both_profile.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.both_user.pk).exists())

    def test_delete_student_view_complete_preserves_user(self):
        """Complete wipe on a student removes profile and achievement but preserves user account as guest."""
        self.client.force_login(self.staff_user)
        url = reverse("users:delete_student", kwargs={"student_id": self.both_profile.pk})
        response = self.client.post(url, {"delete_scope": "complete"})
        self.assertEqual(response.status_code, 302)

        # Profile and achievement must be deleted
        self.assertFalse(StudentProfile.objects.filter(pk=self.both_profile.pk).exists())
        self.assertFalse(StudentAchievement.objects.filter(pk=self.both_ach.pk).exists())
        # User account must remain preserved
        self.assertTrue(User.objects.filter(pk=self.both_user.pk).exists())

    def test_unauthorized_user_cannot_delete_achievement(self):
        """Regular user cannot delete an achievement belonging to someone else."""
        regular_user = User.objects.create_user(
            username="regular_user",
            email="regular@test.com",
            password="TestPassword123!"
        )
        self.client.force_login(regular_user)
        url = reverse("users:delete_achievement", kwargs={"pk": self.alumni_only_ach.pk})
        response = self.client.post(url)
        # Should redirect without deleting
        self.assertTrue(StudentAchievement.objects.filter(pk=self.alumni_only_ach.pk).exists())
