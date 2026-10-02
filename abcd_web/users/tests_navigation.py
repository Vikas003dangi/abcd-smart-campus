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

    def test_assetlinks_contains_play_signing_cert_and_low_cache_ttl(self):
        """Verify assetlinks.json serves the 72:AB... fingerprint, use_as_origin, and 60s max-age."""
        resp = self.client.get('/.well-known/assetlinks.json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp['Cache-Control'], 'public, max-age=60')
        import json
        data = json.loads(resp.content.decode('utf-8'))
        relations = data[0]['relation']
        self.assertIn('delegate_permission/common.use_as_origin', relations)
        fingerprints = data[0]['target']['sha256_cert_fingerprints']
        self.assertIn(
            '72:AB:7B:61:FC:3D:16:2C:CF:B8:11:1B:59:E2:D6:3A:BD:F3:26:F6:2D:35:0F:82:C4:65:67:4B:DE:F5:8F:56',
            fingerprints
        )

    def test_abcd_nav_js_contains_google_search_fallback_and_no_exit_history_pop(self):
        """Verify abcd-nav.js has the Google search URL fallback and no history pop in exit."""
        import os
        from django.conf import settings
        js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'abcd-nav.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Predefined Google search query
        self.assertIn('ABCD Smart Campus Coaching And Library Ganj Basoda', content)
        self.assertIn('https://www.google.com/search?q=', content)

        # Android exit uses TWA postMessage communication (avoids Chrome external-app dialog and subframe scheme blocks)
        self.assertIn('_abcdTwaPort', content)
        self.assertIn('_abcdTwaDiag', content)
        self.assertIn("postMessage('exit'", content)

        # Verify doActualExit does NOT contain any history.go or history.back
        exit_method_start = content.find('doActualExit: function()')
        self.assertNotEqual(exit_method_start, -1)
        exit_method_end = content.find('showExitFallback: function()', exit_method_start)
        self.assertNotEqual(exit_method_end, -1)
        exit_method_code = content[exit_method_start:exit_method_end]
        self.assertNotIn('history.go', exit_method_code)
        self.assertNotIn('history.back', exit_method_code)

    def test_app_install_prompt_play_store_integration(self):
        """Verify app-install-prompt.js contains Play Store URL, market URI, and TWA suppression."""
        import os
        from django.conf import settings
        js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'app-install-prompt.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Play Store official URL and native market URI
        self.assertIn('https://play.google.com/store/apps/details?id=in.abcdcampus.app', content)
        self.assertIn('market://details?id=in.abcdcampus.app', content)

        # openPlayStore helper exists and handles Android native launch + fallback
        self.assertIn('function openPlayStore()', content)
        self.assertIn('window.location.href = PLAY_STORE_MARKET_URI', content)

        # Suppressed when running inside app container
        self.assertIn('function isRunningInsideApp()', content)
        self.assertIn("sessionStorage.getItem('abcd_is_android_app') === '1'", content)

    def test_webmanifest_play_store_related_application(self):
        """Verify site.webmanifest includes in.abcdcampus.app in related_applications."""
        import os
        import json
        from django.conf import settings
        manifest_path = os.path.join(settings.BASE_DIR, 'static', 'data', 'favicon', 'site.webmanifest')
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        related = data.get('related_applications', [])
        play_apps = [app for app in related if app.get('platform') == 'play' and app.get('id') == 'in.abcdcampus.app']
        self.assertEqual(len(play_apps), 1)
        self.assertEqual(play_apps[0]['url'], 'https://play.google.com/store/apps/details?id=in.abcdcampus.app')

    def test_exit_intent_fallback_and_diagnostic_overlay(self):
        """Verify abcd-nav.js and template include intent fallback, real anchor tag, and debug overlay."""
        import os
        from django.conf import settings
        js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'abcd-nav.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Fix 6: Intent fallback URL and feature flag
        self.assertIn('intent://close#Intent;scheme=abcdexit;package=in.abcdcampus.app;end', content)
        self.assertIn('ABCD_EXIT_INTENT_FALLBACK', content)
        self.assertIn('fallback intent link used', content)

        # Fix 1 & 2: Hidden 5-tap debug trigger and copy log button
        self.assertIn('copyAbcdDebugLog', content)
        self.assertIn("sessionStorage.setItem('abcd_debug', '1')", content)
        self.assertIn('native log unavailable - channel not established', content)

        # Fast exit without port: immediate bind-time intent priming (no 3s or 2s wait)
        self.assertIn("els.confirmBtn.setAttribute('href', self.INTENT_FALLBACK_URL)", content)
        self.assertNotIn('waiting up to 2s', content)

        # Template check: Confirm exit button is rendered as a real anchor tag for natural user tap
        tmpl_path = os.path.join(settings.BASE_DIR, 'users', 'templates', 'partials', '_home_base_exit.html')
        with open(tmpl_path, 'r', encoding='utf-8') as f:
            tmpl_content = f.read()
        self.assertIn('<a href="#" id="abcdExitConfirmBtn" role="button"', tmpl_content)

    def test_browser_and_pwa_exit_screen_and_guard(self):
        """Verify browser and PWA exit guard, full-screen exit screen, and 3-Back limit."""
        import os
        from django.conf import settings
        js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'abcd-nav.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 1. abcd_exited flag set before Google redirect with fallback storage
        self.assertIn("sessionStorage.setItem('abcd_exited', '1')", content)
        self.assertIn("window.name", content)

        # 2. Exit guard present and checks back_forward navigation type & pageshow persisted
        self.assertIn('function checkExitGuard', content)
        self.assertIn('back_forward', content)
        self.assertIn('event.persisted', content)

        # 3. 3-Back limit constant on exit screen
        self.assertIn('MAX_EXIT_BACK_COUNT', content)
        self.assertIn('MAX_EXIT_BACK_COUNT = 3', content)
        self.assertIn('Use the tip above to close this tab', content)

        # 4. PWA branch does not navigate to Google
        self.assertIn('detectPwa', content)
        self.assertIn('showExitScreen', content)
        pwa_exit_idx = content.find('if (isPwaMode)')
        self.assertNotEqual(pwa_exit_idx, -1)
        pwa_block = content[pwa_exit_idx:pwa_exit_idx + 350]
        self.assertIn("showExitScreen('pwa')", pwa_block)
        self.assertNotIn("GOOGLE_SEARCH_FALLBACK_URL", pwa_block)

        # 5. No history.back / history.go in exit code
        self.assertNotIn('history.back()', pwa_block)
        self.assertNotIn('history.go(', pwa_block)

        # 6. TWA branch unchanged and excluded from the guard
        self.assertIn('if (isTwa())', content)
        self.assertIn('detectAndroidApp', content)
        self.assertIn("postMessage('exit')", content)


class NavigationBaseTrapInvariantTests(TestCase):
    """Automated tests for Part B Home Base Back Invariants & Part A Exit Lag Fix."""

    def setUp(self):
        self.client = Client()
        self.student_user = User.objects.create_user(username='trap_student', email='ts@test.com', password='Pwd123!')
        self.teacher_user = User.objects.create_superuser(username='trap_teacher', email='tt@test.com', password='Pwd123!')
        self.alumni_user = User.objects.create_user(username='trap_alumni', email='ta@test.com', password='Pwd123!')
        self.guest_user = User.objects.create_user(username='trap_guest', email='tg@test.com', password='Pwd123!')

        StudentProfile.objects.create(
            user=self.student_user, full_name='Trap Student', mobile_number='7777777777',
            dob=date(2002, 1, 1), status='admitted', is_admitted=True
        )

        StudentAchievement.objects.create(
            user=self.alumni_user, first_name='Trap', last_name='Alumni',
            about_yourself='Test', current_post='Test', selection_year=2024,
            working_city='Test', short_achievement='Test', gender='Male',
            dob=date(2000, 1, 1), services_used='library',
            experience_feedback='Good', abcd_feedback='Good', status='approved'
        )

    def test_all_base_pages_render_is_base_page_and_exit_modal(self):
        """Invariant: EVERY base page MUST have isBasePage: true and include the Exit Modal."""
        base_urls = [
            (reverse('users:home_page'), None),
            (reverse('users:guest_page'), 'trap_guest'),
            (reverse('users:student_dashboard'), 'trap_student'),
            (reverse('users:teacher_dashboard'), 'trap_teacher'),
            (reverse('users:alumni_dashboard'), 'trap_alumni'),
        ]

        for url, user in base_urls:
            c = Client()
            if user:
                c.login(username=user, password='Pwd123!')
            resp = c.get(url)
            self.assertEqual(resp.status_code, 200, f"Base page {url} returned {resp.status_code}")
            self.assertContains(resp, 'isBasePage: true', msg_prefix=f"{url} missing isBasePage: true")
            self.assertContains(resp, 'id="abcdExitModal"', msg_prefix=f"{url} missing abcdExitModal")

    def test_abcd_nav_js_implements_part_b_trap_invariants(self):
        """Verify abcd-nav.js source contains all invariant guarantees for Part B."""
        import os
        from django.conf import settings
        js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'abcd-nav.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Scenario 8: Instance ID reload detection in armTrap
        self.assertIn('instanceId: Date.now()', content)
        self.assertIn('currentState.instanceId !== this.instanceId', content)

        # Scenario 7 & 9: pageshow (persisted), visibilitychange, and focus re-arming
        self.assertIn("window.addEventListener('pageshow'", content)
        self.assertIn("document.addEventListener('visibilitychange'", content)
        self.assertIn("window.addEventListener('focus'", content)

        # Scenario 1, 4 & 10: onPopState on base page immediately re-pushes trap
        self.assertIn('if (self.config.isBasePage) {', content)
        self.assertIn('self.armTrap(true);', content)

        # Step 1: Closing in-page modal re-arms trap with force
        self.assertIn('self.armTrap(true);', content)

        # Scenario 4: onCancelExit re-arms trap
        self.assertIn('this.armTrap(true);', content)

    def test_abcd_nav_js_exit_lag_fix(self):
        """Verify abcd-nav.js exit lag fixes: single-send exit on port, no duplicate retry loop."""
        import os
        from django.conf import settings
        js_path = os.path.join(settings.BASE_DIR, 'static', 'js', 'abcd-nav.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Instant single-send when port exists (no self.doActualExit duplicate send)
        self.assertIn("port.postMessage('exit')", content)
        self.assertIn("port.postMessage(\"exit\") sent once", content)

        # Retry loop in doActualExit removed
        self.assertNotIn("var interval = setInterval(function() {\n                    attempts++;", content)
        self.assertNotIn("attempts >= 10", content)

