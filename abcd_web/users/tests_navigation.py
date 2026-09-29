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
        self.assertNotContains(resp, 'id="abcdExitModal"')

    def test_todo_page_is_subpage_without_exit_modal(self):
        """To-Do page is a subpage with isBasePage: false and does NOT have Exit Modal."""
        self.client.login(username='student_user', password='Password123!')
        resp = self.client.get(reverse('users:todo_hub'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'abcd-nav')
        self.assertContains(resp, 'isBasePage: false')
        self.assertNotContains(resp, 'id="abcdExitModal"')

    def test_student_dashboard_has_exit_modal_and_base_page(self):
        """Student Dashboard is a base page and includes the Exit Modal."""
        self.client.login(username='student_user', password='Password123!')
        resp = self.client.get(reverse('users:student_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'abcd-nav')
        self.assertContains(resp, 'isBasePage: true')
        self.assertContains(resp, 'id="abcdExitModal"')

    def test_teacher_dashboard_has_exit_modal_and_base_page(self):
        """Teacher Dashboard is a base page and includes the Exit Modal."""
        self.client.login(username='teacher_user', password='Password123!')
        resp = self.client.get(reverse('users:teacher_dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'abcd-nav')
        self.assertContains(resp, 'isBasePage: true')
        self.assertContains(resp, 'id="abcdExitModal"')


class NavigationParentUrlTests(TestCase):
    """Verify that subpages embed the correct parentUrl for ABCDNav to resolve."""

    def setUp(self):
        self.client = Client()
        self.student_user = User.objects.create_user(username='nav_student', email='nav_s@test.com', password='Pwd123!')
        self.teacher_user = User.objects.create_superuser(username='nav_teacher', email='nav_t@test.com', password='Pwd123!')
        StudentProfile.objects.create(
            user=self.student_user, full_name='Nav Student', mobile_number='9999999999',
            dob=date(2002, 1, 1), status='admitted', is_admitted=True
        )
        self.alumni_user = User.objects.create_user(username='nav_alumni', email='nav_a@test.com', password='Pwd123!')
        self.achievement = StudentAchievement.objects.create(
            user=self.alumni_user, first_name='Nav', last_name='Alumni',
            about_yourself='Test', current_post='Test', selection_year=2024,
            working_city='Test', short_achievement='Test', gender='Male',
            dob=date(2000, 1, 1), services_used='library',
            experience_feedback='Good', abcd_feedback='Good', status='approved'
        )

    def test_student_courses_is_subpage(self):
        """Courses page should be a subpage (not base) with no exit modal."""
        self.client.login(username='nav_student', password='Pwd123!')
        resp = self.client.get(reverse('users:courses'))
        self.assertContains(resp, 'isBasePage: false')
        self.assertNotContains(resp, 'id="abcdExitModal"')

    def test_student_todo_is_subpage(self):
        """To-Do should be a subpage falling back to homeBaseUrl (student dashboard)."""
        self.client.login(username='nav_student', password='Pwd123!')
        resp = self.client.get(reverse('users:todo_hub'))
        self.assertContains(resp, 'isBasePage: false')
        self.assertNotContains(resp, 'id="abcdExitModal"')

    def test_student_complaints_is_subpage(self):
        """Complaints page is a subpage."""
        self.client.login(username='nav_student', password='Pwd123!')
        resp = self.client.get(reverse('users:student_complaints'))
        self.assertContains(resp, 'isBasePage: false')

    def test_hall_of_fame_is_subpage(self):
        """Hall of Fame is a subpage (not a base page)."""
        resp = self.client.get(reverse('users:hall_of_fame'))
        self.assertContains(resp, 'isBasePage: false')

    def test_achievement_detail_is_context_aware(self):
        """Achievement detail should have contextAware: true."""
        resp = self.client.get(reverse('users:achievement_detail', kwargs={'pk': self.achievement.pk}))
        self.assertContains(resp, 'isBasePage: false')
        self.assertContains(resp, 'contextAware: true')


    def test_teacher_courses_is_subpage(self):
        """Teacher courses should be a subpage."""
        self.client.login(username='nav_teacher', password='Pwd123!')
        resp = self.client.get(reverse('users:teacher_courses'))
        self.assertContains(resp, 'isBasePage: false')
        self.assertNotContains(resp, 'id="abcdExitModal"')

    def test_teacher_broadcast_is_subpage(self):
        """Teacher broadcast should be a subpage."""
        self.client.login(username='nav_teacher', password='Pwd123!')
        resp = self.client.get(reverse('users:teacher_broadcast'))
        self.assertContains(resp, 'isBasePage: false')

    def test_guest_page_is_base_page(self):
        """Guest page should be a base page with exit modal."""
        guest = User.objects.create_user(username='nav_guest', email='ng@test.com', password='Pwd123!')
        c = Client()
        c.login(username='nav_guest', password='Pwd123!')
        resp = c.get(reverse('users:guest_page'))
        self.assertContains(resp, 'isBasePage: true')
        self.assertContains(resp, 'id="abcdExitModal"')

    def test_alumni_dashboard_is_base_page(self):
        """Alumni dashboard should be a base page with exit modal."""
        self.client.login(username='nav_alumni', password='Pwd123!')
        resp = self.client.get(reverse('users:alumni_dashboard'))
        self.assertContains(resp, 'isBasePage: true')
        self.assertContains(resp, 'id="abcdExitModal"')

    def test_guest_visiting_subpage_has_no_exit_modal(self):
        """Guest visiting courses (which extends base_template) should NOT get exit modal."""
        guest = User.objects.create_user(username='sub_guest', email='sg@test.com', password='Pwd123!')
        c = Client()
        c.login(username='sub_guest', password='Pwd123!')
        resp = c.get(reverse('users:courses'))
        self.assertContains(resp, 'isBasePage: false')
        self.assertNotContains(resp, 'id="abcdExitModal"')

    def test_alumni_visiting_subpage_has_no_exit_modal(self):
        """Alumni visiting courses (which extends base_template) should NOT get exit modal."""
        self.client.login(username='nav_alumni', password='Pwd123!')
        resp = self.client.get(reverse('users:courses'))
        self.assertContains(resp, 'isBasePage: false')
        self.assertNotContains(resp, 'id="abcdExitModal"')



class NavigationExitModalTests(TestCase):
    """Verify the Exit Modal structure for v3.0 fallback view."""

    def setUp(self):
        self.client = Client()
        self.student_user = User.objects.create_user(username='exit_student', email='exit_s@test.com', password='Pwd123!')
        StudentProfile.objects.create(
            user=self.student_user, full_name='Exit Student', mobile_number='8888888888',
            dob=date(2002, 6, 15), status='admitted', is_admitted=True
        )

    def test_exit_modal_has_confirm_and_fallback_views(self):
        """Exit modal should contain both the confirm view and the fallback view."""
        self.client.login(username='exit_student', password='Pwd123!')
        resp = self.client.get(reverse('users:student_dashboard'))
        self.assertContains(resp, 'id="abcdExitConfirmView"')
        self.assertContains(resp, 'id="abcdExitFallbackView"')
        self.assertContains(resp, 'id="abcdExitFallbackGotItBtn"')
        self.assertContains(resp, 'id="abcdExitShortcut"')

    def test_exit_modal_fallback_hidden_by_default(self):
        """Fallback view should be hidden by default."""
        self.client.login(username='exit_student', password='Pwd123!')
        resp = self.client.get(reverse('users:student_dashboard'))
        self.assertContains(resp, 'id="abcdExitFallbackView" style="display:none;"')

    def test_exit_modal_has_kbd_styling(self):
        """Exit modal should include kbd element styling for keyboard shortcuts."""
        self.client.login(username='exit_student', password='Pwd123!')
        resp = self.client.get(reverse('users:student_dashboard'))
        self.assertContains(resp, '#abcdExitModal kbd')

    def test_abcd_nav_version_3_on_base_page(self):
        """ABCDNav script should be loaded at version 3.0.0 on base pages."""
        self.client.login(username='exit_student', password='Pwd123!')
        resp = self.client.get(reverse('users:student_dashboard'))
        self.assertContains(resp, 'v=3.0.0')

    def test_abcd_nav_version_3_on_subpage(self):
        """ABCDNav script should be loaded at version 3.0.0 on subpages."""
        self.client.login(username='exit_student', password='Pwd123!')
        resp = self.client.get(reverse('users:courses'))
        self.assertContains(resp, 'v=3.0.0')
