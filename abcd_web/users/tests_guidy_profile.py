from datetime import date
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from users.models import StudentProfile, StudentAchievement, Seat

User = get_user_model()

class GuidyProfileInfoTests(TestCase):
    def setUp(self):
        # User A (Guest User)
        self.guest_user = User.objects.create_user(username='guest_vikas', first_name='Vikas', last_name='Dangi', password='password123')
        
        # User B (Coaching Student Raj Pandey)
        self.student_user = User.objects.create_user(username='student_raj', first_name='Raj', last_name='Pandey', password='password123')
        self.student_profile = StudentProfile.objects.create(
            user=self.student_user,
            full_name='Raj Pandey',
            service_type='Coaching',
            batch='Spoken English 1'
        )

        # User C (Pure Alumni Vijay Chakravarti)
        self.alumni_user = User.objects.create_user(username='alumni_vijay', first_name='Vijay', last_name='Chakravarti', password='password123')
        self.alumni_achievement = StudentAchievement.objects.create(
            user=self.alumni_user,
            first_name='Vijay',
            last_name='Chakravarti',
            dob=date(1995, 1, 1),
            current_post='IAS',
            selection_year=2025,
            working_city='Bhopal',
            status='approved',
            services_used='library'
        )

    def test_guest_user_not_colliding_with_student_pk(self):
        """Even if entity_type is 'student', if user has no StudentProfile, it must return Guest User, not another student's profile."""
        self.client.login(username='alumni_vijay', password='password123')
        url = reverse('users:guidy_profile_info', kwargs={'entity_type': 'student', 'entity_id': self.guest_user.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['name'], 'Vikas Dangi')
        self.assertEqual(data['role'], 'Guest User')

    def test_pure_alumni_does_not_see_student_profile_card(self):
        """Alumni who is not an admitted student should not have active student dashboard or see student profile switcher."""
        self.client.login(username='alumni_vijay', password='password123')
        url = reverse('users:alumni_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context.get('has_active_student_dashboard'))
        self.assertFalse(response.context.get('is_dual_user'))
        content = response.content.decode('utf-8')
        # Student Profile card must not be present
        self.assertNotIn('<span>Student Profile</span>', content)

    def test_alumni_visiting_complaints_on_get_does_not_create_pending_student(self):
        """Visiting complaints on GET must not create a StudentProfile with status='pending'."""
        self.client.login(username='alumni_vijay', password='password123')
        self.assertFalse(StudentProfile.objects.filter(user=self.alumni_user).exists())
        url = reverse('users:student_complaints')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Verify no StudentProfile was created on GET
        self.assertFalse(StudentProfile.objects.filter(user=self.alumni_user).exists())

    def test_library_admission_without_seat_excluded_from_teacher_dashboard(self):
        """Library admission without a chosen seat must never appear in new library admissions."""
        phantom_user = User.objects.create_user(username='phantom_user', password='password123')
        phantom_profile = StudentProfile.objects.create(
            user=phantom_user,
            full_name='Phantom Applicant',
            service_type='Library',
            status='pending',
            seat=None
        )
        teacher = User.objects.create_user(username='teacher1', password='password123', is_staff=True)
        self.client.login(username='teacher1', password='password123')
        url = reverse('users:teacher_dashboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        new_lib_students = response.context.get('pending_new_library_students')
        self.assertNotIn(phantom_profile, new_lib_students)
