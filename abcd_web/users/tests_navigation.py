from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from users.models import StudentProfile, StudentAchievement
from datetime import date

class NavigationArchitectureTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.guest_user = User.objects.create_user(username='guest_user', email='guest@example.com', password='Password123!')
        self.student_user = User.objects.create_user(username='student_user', email='student@example.com', password='Password123!')
        self.alumni_user = User.objects.create_user(username='alumni_user', email='alumni@example.com', password='Password123!')
        self.teacher_user = User.objects.create_superuser(username='teacher_user', email='teacher@example.com', password='Password123!')

        # Set up student profile
        StudentProfile.objects.create(
            user=self.student_user,
            full_name='Student Tester',
            mobile_number='9876543210',
            dob=date(2002, 5, 10),
            status='admitted',
            is_admitted=True
        )

        # Set up alumni achievement
        StudentAchievement.objects.create(
            user=self.alumni_user,
            first_name='Alumni',
            last_name='Tester',
            about_yourself='Great experience',
            current_post='Officer',
            selection_year=2024,
            working_city='Delhi',
            short_achievement='CDS Officer',
            gender='Male',
            dob=date(2000, 1, 1),
            services_used='library',
            experience_feedback='Good',
            abcd_feedback='Awesome',
            status='approved'
        )

    def test_unauthenticated_smart_back_routes_to_home(self):
        """Unauthenticated user accessing smart-back is safely routed to public home."""
        resp = self.client.get(reverse('users:smart_back_router'))
        self.assertRedirects(resp, reverse('users:home_page'))

    def test_teacher_smart_back_routes_to_teacher_dashboard(self):
        """Staff/Teacher accessing smart-back is routed to teacher dashboard."""
        self.client.login(username='teacher_user', password='Password123!')
        resp = self.client.get(reverse('users:smart_back_router'))
        self.assertRedirects(resp, reverse('users:teacher_dashboard'))

    def test_student_smart_back_routes_to_student_dashboard(self):
        """Admitted student accessing smart-back is routed to student dashboard."""
        self.client.login(username='student_user', password='Password123!')
        resp = self.client.get(reverse('users:smart_back_router'))
        self.assertRedirects(resp, reverse('users:student_dashboard'))

    def test_alumni_smart_back_routes_to_alumni_dashboard(self):
        """Alumni accessing smart-back is routed to alumni dashboard."""
        self.client.login(username='alumni_user', password='Password123!')
        resp = self.client.get(reverse('users:smart_back_router'))
        self.assertRedirects(resp, reverse('users:alumni_dashboard'))

    def test_guest_smart_back_routes_to_guest_page(self):
        """Authenticated user without student or alumni profile routes to guest page."""
        self.client.login(username='guest_user', password='Password123!')
        resp = self.client.get(reverse('users:smart_back_router'))
        self.assertRedirects(resp, reverse('users:guest_page'))

    def test_home_page_includes_abcd_nav_controller(self):
        """Home page correctly loads the unified ABCDNav controller and exit modal."""
        resp = self.client.get(reverse('users:home_page'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'abcd-nav')
        self.assertContains(resp, 'id="abcdExitModal"')

    def test_subpage_includes_abcd_nav_initialization(self):
        """Child pages correctly initialize ABCDNav with isBasePage: false."""
        resp = self.client.get(reverse('users:courses'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'abcd-nav')
        self.assertContains(resp, 'window.ABCDNav.init({')
        self.assertContains(resp, 'isBasePage: false')
