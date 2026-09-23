import json
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta, date
from django.urls import reverse
from users.models import Seat, StudentProfile, SeatAssignment, StudentAchievement, SeatLeaveRequest, SeatHoldChangeRequest
from users.utils import process_expired_holds, process_birthday_wishes

User = get_user_model()

class SystemCoreTests(TestCase):
    def setUp(self):
        # Create test user
        self.user = User.objects.create_user(
            username='teststudent',
            password='Password123!',
            email='test@example.com'
        )
        # Create test seat
        self.seat = Seat.objects.create(
            seat_number='1',
            floor='Ground Floor',
            status='available'
        )
        # Create test student profile
        today_local = timezone.localtime().date()
        self.profile = StudentProfile.objects.create(
            user=self.user,
            full_name='Test Student',
            dob=date(2000, today_local.month, today_local.day),
            sex='male',
            service_type='Library',
            seat=self.seat,
            status='admitted',
            is_admitted=True
        )

    def test_seat_recalc_status(self):
        """Test that seat status correctly recalculates based on active assignments."""
        self.assertEqual(self.seat.status, 'available')
        
        assignment = SeatAssignment.objects.create(
            student=self.profile,
            seat=self.seat,
            shift_type='full',
            is_active=True
        )
        self.seat.recalc_status()
        self.assertEqual(self.seat.status, 'occupied')

    def test_birthday_wishes_processor(self):
        """Test that birthday wishes processor identifies today's birthdays and dispatches alerts."""
        count = process_birthday_wishes()
        self.assertGreaterEqual(count, 1)

    def test_future_hold_activation(self):
        """Test that future hold auto-activation transitions pending holds to active status."""
        today = timezone.localdate()
        assignment = SeatAssignment.objects.create(
            student=self.profile,
            seat=self.seat,
            shift_type='full',
            is_active=True,
            hold_status='pending',
            hold_start_date=today,
            hold_end_date=today + timedelta(days=5)
        )
        process_expired_holds()
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, 'on_hold')

    def test_seat_locking_and_assignment_protection(self):
        """Test that librarians can lock seats and locked seats block assignments."""
        # Lock seat
        self.seat.is_locked = True
        self.seat.locked_shifts = 'full'
        self.seat.save()

        self.assertTrue(self.seat.is_locked)

        # Attempt API assignment via client
        self.client.force_login(self.user)
        # Give staff status to test teacher action
        self.user.is_staff = True
        self.user.save()

        response = self.client.post(
            '/api/teacher/seat_action/',
            data={
                'floor': 'Ground Floor',
                'seat_number': '1',
                'action': 'assign',
                'student_id': self.profile.id,
                'payload': {'shift': 'full'}
            },
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("locked by the Librarian", response.json().get('message', ''))

    def test_deduplicate_request_form_post(self):
        """Test that deduplicate_request handles standard multipart/POST forms safely without RawPostDataException."""
        from users.db_utils import deduplicate_request
        from django.http import HttpResponse

        @deduplicate_request(timeout=5)
        def sample_view(request):
            return HttpResponse("OK")

        # Simulate form POST
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.post('/admission-form/', data={'full_name': 'Form Test Student', 'service_type': 'Library'})
        request.user = self.user

        # Must execute cleanly without RawPostDataException
        response = sample_view(request)
        self.assertEqual(response.status_code, 200)

    def test_email_routing_priority(self):
        """Test that get_user_notification_email prioritizes updated profile/achievement email while auth uses user.email."""
        from users.utils import get_user_notification_email

        # Standard user email
        self.assertEqual(self.user.email, 'test@example.com')
        self.assertEqual(get_user_notification_email(self.profile), 'test@example.com')

        # Update profile email via form/edit
        self.profile.email = 'updated_contact@example.com'
        self.profile.save()

        # Notification target email must return updated_contact@example.com
        self.assertEqual(get_user_notification_email(self.profile), 'updated_contact@example.com')
        self.assertEqual(get_user_notification_email(self.user), 'updated_contact@example.com')

        # Auth/security emails must still target user account email
        self.assertEqual(self.user.email, 'test@example.com')

    def test_course_favorite_and_archive_toggle(self):
        """Test toggling favorite and archive on courses and verifying tabs filtering and detail context."""
        from users.models import Course, StudentCourseInteraction

        course = Course.objects.create(
            title="Test Python Mastery",
            description="Complete Python Guide",
            target_public=True,
            is_active=True
        )

        self.client.force_login(self.user)

        # 1. Toggle Favorite
        res = self.client.post(
            f'/api/courses/{course.id}/interaction/',
            data={'action': 'favorite'},
            content_type='application/json'
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data['success'])
        self.assertTrue(data['is_favorite'])
        self.assertFalse(data['is_archived'])

        # Check DB
        interaction = StudentCourseInteraction.objects.get(student=self.profile, course=course)
        self.assertTrue(interaction.is_favorite)
        self.assertFalse(interaction.is_archived)

        # 2. Check courses favorites tab
        courses_res = self.client.get('/courses/?tab=favorites')
        self.assertEqual(courses_res.status_code, 200)
        self.assertIn(course, courses_res.context['courses'])

        # 3. Toggle Archive
        res_arch = self.client.post(
            f'/api/courses/{course.id}/interaction/',
            data={'action': 'archive'},
            content_type='application/json'
        )
        self.assertEqual(res_arch.status_code, 200)
        data_arch = res_arch.json()
        self.assertTrue(data_arch['is_archived'])

        # All tab should exclude archived course
        all_res = self.client.get('/courses/?tab=all')
        self.assertNotIn(course, all_res.context['courses'])

        # Archived tab should include it
        archived_res = self.client.get('/courses/?tab=archived')
        self.assertIn(course, archived_res.context['courses'])

        # 4. Check course detail view context has interaction
        detail_res = self.client.get(f'/courses/{course.id}/')
        self.assertEqual(detail_res.status_code, 200)
        self.assertIsNotNone(detail_res.context['interaction'])
        self.assertTrue(detail_res.context['interaction'].is_favorite)
        self.assertTrue(detail_res.context['interaction'].is_archived)

    def test_pending_student_course_access_and_guest_behavior(self):
        """Test that pending admission students are treated as guests (can access public courses, coaching courses locked)."""
        from users.models import Course
        from users.views import check_course_access

        # 1. Public course
        public_course = Course.objects.create(
            title="Public Intro Course",
            target_public=True,
            is_active=True
        )

        # 2. Coaching only course
        coaching_course = Course.objects.create(
            title="Coaching Exclusive Course",
            target_public=False,
            target_coaching=True,
            target_coaching_batches="all",
            is_active=True
        )

        # Create pending student
        pending_user = User.objects.create_user(
            username='pendingstudent',
            password='Password123!',
            email='pending@example.com'
        )
        pending_profile = StudentProfile.objects.create(
            user=pending_user,
            full_name='Pending Student',
            dob=date(2000, 1, 1),
            sex='female',
            service_type='Coaching',
            status='pending',
            is_admitted=False
        )

        # Check access helper directly
        self.assertTrue(check_course_access(pending_user, public_course))
        self.assertFalse(check_course_access(pending_user, coaching_course))

        self.client.force_login(pending_user)

        # Access public course -> should NOT be locked
        pub_res = self.client.get(f'/courses/{public_course.id}/')
        self.assertEqual(pub_res.status_code, 200)
        self.assertFalse(pub_res.context['is_locked'])

        # Access coaching course -> should BE locked and identify pending admission
        coach_res = self.client.get(f'/courses/{coaching_course.id}/')
        self.assertEqual(coach_res.status_code, 200)
        self.assertTrue(coach_res.context['is_locked'])
        self.assertTrue(coach_res.context['is_pending_student'])
        self.assertContains(coach_res, "Admission Pending")

        # Now approve student
        pending_profile.status = 'admitted'
        pending_profile.is_admitted = True
        pending_profile.save()

        # Now student has access to coaching course
        self.assertTrue(check_course_access(pending_user, coaching_course))
        coach_res_approved = self.client.get(f'/courses/{coaching_course.id}/')
        self.assertEqual(coach_res_approved.status_code, 200)
        self.assertFalse(coach_res_approved.context['is_locked'])

    def test_edit_student_profile_preserves_user_email(self):
        """Test that EditStudentProfileForm updates StudentProfile.email without modifying User.email."""
        from users.forms import EditStudentProfileForm

        # Initial state
        self.assertEqual(self.user.email, 'test@example.com')
        
        # Staff user editing student
        self.user.is_staff = True
        self.user.save()
        form_data = {
            'full_name': 'Test Student Updated',
            'sex': 'Male',
            'dob': '2000-01-01',
            'mobile_number': '9876543210',
            'whatsapp_number': '9876543210',
            'email': 'new_notifications@example.com',
            'service_type': 'Library',
            'status': 'admitted'
        }
        form = EditStudentProfileForm(data=form_data, instance=self.profile, user_editing=self.user)
        self.assertTrue(form.is_valid(), form.errors)
        saved_student = form.save()

        # Check that StudentProfile has the new notification email
        self.assertEqual(saved_student.email, 'new_notifications@example.com')
        # Check that User.email remained unchanged for login credentials
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'test@example.com')

    def test_update_contact_info_api_preserves_user_email(self):
        """Test that update_contact_info_api updates StudentProfile.email without altering User.email."""
        self.client.force_login(self.user)
        response = self.client.post(
            '/api/update_contact_info/',
            data={
                'email': 'api_contact@example.com',
                'whatsapp_number': '9876543210'
            },
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.email, 'api_contact@example.com')
        self.assertEqual(self.profile.whatsapp_number, '9876543210')
        
        # Credential email unchanged
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, 'test@example.com')

    def test_student_profile_form_initial_email_prepopulation(self):
        """Test that StudentProfileForm pre-populates email from user.email."""
        from users.forms import StudentProfileForm
        form = StudentProfileForm(user=self.user)
        self.assertEqual(form.initial.get('email'), 'test@example.com')

    def test_complaint_image_cleanup_after_5_days(self):
        """Test that resolved complaints older than 5 days have their attached images removed."""
        from users.models import Complaint
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.core.management import call_command
        from django.utils import timezone
        from datetime import timedelta

        test_img = SimpleUploadedFile("test_complaint.jpg", b"dummy image content", content_type="image/jpeg")
        complaint = Complaint.objects.create(
            student=self.profile,
            subject=Complaint.SUBJECT_OTHER,
            message="Test Description",
            status="resolved",
            image1=test_img
        )
        # Manually set resolved_at to 6 days ago
        Complaint.objects.filter(id=complaint.id).update(resolved_at=timezone.now() - timedelta(days=6))

        call_command('cleanup_complaint_images')
        complaint.refresh_from_db()
        self.assertFalse(bool(complaint.image1))

    def test_broadcast_cleanup_after_20_days(self):
        """Test that broadcasts older than 20 days are permanently deleted."""
        from users.models import BroadcastMessage
        from django.core.management import call_command
        from django.utils import timezone
        from datetime import timedelta

        b = BroadcastMessage.objects.create(
            sender=self.user,
            subject="Old Announcement",
            message="Old broadcast message",
            target_group="all"
        )
        BroadcastMessage.objects.filter(id=b.id).update(created_at=timezone.now() - timedelta(days=22))

        call_command('cleanup_broadcasts')
        self.assertFalse(BroadcastMessage.objects.filter(id=b.id).exists())

    def test_guidy_chat_media_purge_10_days(self):
        """Test that Guidy chat attachments older than 10 days are physically purged."""
        from users.models import Message, ChatSession
        from users.views import purge_expired_media
        from django.core.files.uploadedfile import SimpleUploadedFile
        from django.utils import timezone
        from datetime import timedelta

        session = ChatSession.objects.create(user_one=self.user, user_two=self.user)
        test_file = SimpleUploadedFile("voice.mp3", b"audio data", content_type="audio/mpeg")
        msg = Message.objects.create(
            session=session,
            sender=self.user,
            message_type="audio",
            file=test_file
        )
        Message.objects.filter(id=msg.id).update(timestamp=timezone.now() - timedelta(days=12))

        purge_expired_media()
        msg.refresh_from_db()
        self.assertTrue(msg.media_expired)
        self.assertFalse(bool(msg.file))

    def test_guidy_group_deletion_lifecycle_and_early_purge(self):
        """Test Guidy group deletion by admin, banner status, member-side deletion, and early purge when all clear."""
        from users.models import GroupChatSession
        from django.utils import timezone

        # Create members
        u1 = self.user
        u2 = User.objects.create_user(username="member2", password="Password123!", email="m2@example.com")
        u3 = User.objects.create_user(username="member3", password="Password123!", email="m3@example.com")

        group = GroupChatSession.objects.create(
            name="Study Circle",
            created_by=u1
        )
        group.members.add(u1, u2, u3)

        # 1. Admin deletes the group
        self.client.force_login(u1)
        res = self.client.post(
            f'/guidy/groups/{group.id}/members/manage/',
            data={'action': 'delete', 'member_id': u1.id}
        )
        self.assertEqual(res.status_code, 200)
        group.refresh_from_db()
        self.assertFalse(group.is_active)
        self.assertEqual(group.deleted_by_user, u1)
        self.assertIn(u1, group.deleted_for_users.all())
        # Group still exists in DB because u2 and u3 haven't cleared it yet
        self.assertTrue(GroupChatSession.objects.filter(id=group.id).exists())

        # 2. Member 2 clears group from their end
        self.client.force_login(u2)
        res2 = self.client.post(f'/guidy/groups/{group.id}/delete-for-user/')
        self.assertEqual(res2.status_code, 200)
        group.refresh_from_db()
        self.assertIn(u2, group.deleted_for_users.all())
        self.assertTrue(GroupChatSession.objects.filter(id=group.id).exists())

        # 3. Member 3 clears group from their end -> ALL members have cleared -> Master purge triggered!
        self.client.force_login(u3)
        res3 = self.client.post(f'/guidy/groups/{group.id}/delete-for-user/')
        self.assertEqual(res3.status_code, 200)
        # Group must now be completely purged from database
        self.assertFalse(GroupChatSession.objects.filter(id=group.id).exists())

    def test_ping_and_keepalive(self):
        """Verify that /ping/ and /healthz/ respond with 200 OK and valid JSON."""
        res = self.client.get('/ping/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('service'), 'ABCD Smart Campus')

        res_h = self.client.get('/healthz/')
        self.assertEqual(res_h.status_code, 200)
        data_h = res_h.json()
        self.assertEqual(data_h.get('status'), 'ok')

    def test_cron_maintenance_webhook(self):
        """Verify authentication and execution of /api/cron/maintenance/ webhook."""
        # 1. Unauthorized request without key
        res_unauth = self.client.get('/api/cron/maintenance/')
        self.assertEqual(res_unauth.status_code, 403)
        self.assertEqual(res_unauth.json().get('status'), 'error')

        # 2. Authorized request with valid key
        res_auth = self.client.get('/api/cron/maintenance/?key=abcd_smart_campus_cron_2026&mode=high_frequency')
        self.assertEqual(res_auth.status_code, 200)
        data = res_auth.json()
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('report', data)
        self.assertEqual(data['report'].get('mode'), 'high_frequency')
        self.assertIn('high_frequency', data['report'])

    def test_admission_and_achievement_form_profile_sync_and_photo_isolation(self):
        """Verify that common fields in StudentProfileForm and StudentAchievementForm are editable,
        cross-sync across models, and strictly preserve separate photo lifecycles."""
        from users.forms import StudentProfileForm, StudentAchievementForm
        from users.models import StudentAchievement
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Ensure form fields are not disabled
        profile_form = StudentProfileForm(user=self.user)
        self.assertFalse(profile_form.fields['first_name'].disabled)
        self.assertFalse(profile_form.fields['last_name'].disabled)
        self.assertFalse(profile_form.fields['sex'].disabled)
        self.assertFalse(profile_form.fields['dob'].disabled)

        ach_form = StudentAchievementForm(user=self.user)
        self.assertFalse(ach_form.fields['first_name'].disabled)
        self.assertFalse(ach_form.fields['last_name'].disabled)
        self.assertFalse(ach_form.fields['gender'].disabled)
        self.assertFalse(ach_form.fields['dob'].disabled)

        # Set a dummy student photo
        dummy_student_photo = SimpleUploadedFile("student_dummy.jpg", b"student_photo_bytes", content_type="image/jpeg")
        self.profile.photo = dummy_student_photo
        self.profile.save()
        self.assertIn('student_photos', self.profile.photo.name)

        # Create an achievement for the user with an achievement photo
        dummy_ach_photo = SimpleUploadedFile("ach_dummy.jpg", b"ach_photo_bytes", content_type="image/jpeg")
        achievement = StudentAchievement.objects.create(
            user=self.user,
            first_name='Test',
            last_name='Student',
            about_yourself='Positive student',
            current_post='Officer',
            selection_year=2023,
            working_city='Indore',
            short_achievement='Officer Post',
            gender='Male',
            dob=date(2000, 1, 1),
            services_used='library',
            photo=dummy_ach_photo,
            status='approved'
        )
        self.assertIn('achievements', achievement.photo.name)

        # Update profile with new name and details
        self.profile.full_name = 'Vikram Sharma'
        self.profile.sex = 'Male'
        self.profile.dob = date(1999, 5, 20)
        self.profile.mobile_number = '9876543210'
        self.profile.whatsapp_number = '9876543210'
        self.profile.email = 'vikram@example.com'
        self.profile.save()

        # Check that achievement synced common details without touching photo
        achievement.refresh_from_db()
        self.assertEqual(achievement.first_name, 'Vikram')
        self.assertEqual(achievement.last_name, 'Sharma')
        self.assertEqual(achievement.gender, 'Male')
        self.assertEqual(achievement.dob, date(1999, 5, 20))
        self.assertEqual(achievement.mobile_number, '9876543210')
        self.assertEqual(achievement.email, 'vikram@example.com')
        self.assertIn('achievements', achievement.photo.name)
        self.assertNotIn('student_photos', achievement.photo.name)

        # Now update from achievement side
        achievement.first_name = 'Vikramaditya'
        achievement.last_name = 'Rathore'
        achievement.gender = 'Male'
        achievement.dob = date(1998, 12, 15)
        achievement.mobile_number = '9123456789'
        achievement.email = 'rathore@example.com'
        achievement.save()

        # Check that StudentProfile synced common details without touching its photo
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.full_name, 'Vikramaditya Rathore')
        self.assertEqual(self.profile.sex, 'Male')
        self.assertEqual(self.profile.dob, date(1998, 12, 15))
        self.assertEqual(self.profile.mobile_number, '9123456789')
        self.assertEqual(self.profile.email, 'rathore@example.com')
        self.assertIn('student_photos', self.profile.photo.name)
        self.assertNotIn('achievements', self.profile.photo.name)


class DualRoleDashboardSwitchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='dualuser',
            password='Password123!',
            email='dual@example.com'
        )
        self.profile = StudentProfile.objects.create(
            user=self.user,
            full_name='Dual User',
            dob=date(2001, 1, 1),
            sex='male',
            service_type='Library',
            status='admitted',
            is_admitted=True
        )
        self.achievement = StudentAchievement.objects.create(
            user=self.user,
            first_name='Dual',
            last_name='User',
            about_yourself='Bio',
            current_post='Officer',
            selection_year=2024,
            working_city='Indore',
            short_achievement='Cleared exam',
            gender='Male',
            dob=date(2001, 1, 1),
            services_used='library',
            status='approved'
        )
        self.client.login(username='dualuser', password='Password123!')

    def test_switch_to_alumni_and_smart_back(self):
        """Switching to alumni sets session and routes smart_back to alumni dashboard."""
        resp = self.client.get(reverse('users:switch_dashboard', kwargs={'role': 'alumni'}))
        self.assertRedirects(resp, reverse('users:alumni_dashboard'))
        self.assertEqual(self.client.session.get('active_dashboard'), 'alumni')

        # Smart back router should now return to alumni dashboard
        back_resp = self.client.get(reverse('users:smart_back_router'))
        self.assertRedirects(back_resp, reverse('users:alumni_dashboard'))

    def test_switch_to_student_and_smart_back(self):
        """Switching to student sets session and routes smart_back to student dashboard."""
        resp = self.client.get(reverse('users:switch_dashboard', kwargs={'role': 'student'}))
        self.assertRedirects(resp, reverse('users:student_dashboard'))
        self.assertEqual(self.client.session.get('active_dashboard'), 'student')

        # Smart back router should now return to student dashboard
        back_resp = self.client.get(reverse('users:smart_back_router'))
        self.assertRedirects(back_resp, reverse('users:student_dashboard'))

    def test_subpage_navigation_preserves_active_dashboard(self):
        """Visiting student profile while in alumni mode does NOT overwrite active_dashboard."""
        session = self.client.session
        session['active_dashboard'] = 'alumni'
        session.save()

        # Visit student details page
        self.client.get(reverse('users:student_details_S'))
        # Session should still be alumni
        self.assertEqual(self.client.session.get('active_dashboard'), 'alumni')

        # Visit achievement detail page
        self.client.get(reverse('users:achievement_detail', kwargs={'pk': self.achievement.pk}))
        # Session should still be alumni
        self.assertEqual(self.client.session.get('active_dashboard'), 'alumni')

    def test_switcher_only_renders_for_dual_users(self):
        """Profile switcher popover must render ONLY for dual users, never for single-profile users."""
        # 1. Dual user: popover MUST be present
        resp = self.client.get(reverse('users:student_dashboard'))
        self.assertTrue(resp.context.get('is_dual_user'))
        self.assertContains(resp, 'id="profileSwitcherPopover"')

        # 2. Single Student user: popover must NOT be present
        single_student = User.objects.create_user(
            username='singlestudent',
            password='Password123!',
            email='single_student@example.com'
        )
        StudentProfile.objects.create(
            user=single_student,
            full_name='Single Student',
            dob=date(2002, 2, 2),
            sex='female',
            service_type='Library',
            status='admitted',
            is_admitted=True
        )
        self.client.login(username='singlestudent', password='Password123!')
        resp_student = self.client.get(reverse('users:student_dashboard'))
        self.assertFalse(resp_student.context.get('is_dual_user'))
        self.assertNotContains(resp_student, 'id="profileSwitcherPopover"')

        # 3. Single Alumni user: popover must NOT be present
        single_alumni = User.objects.create_user(
            username='singlealumni',
            password='Password123!',
            email='single_alumni@example.com'
        )
        StudentAchievement.objects.create(
            user=single_alumni,
            first_name='Single',
            last_name='Alumni',
            about_yourself='Bio',
            current_post='Officer',
            selection_year=2024,
            working_city='Indore',
            short_achievement='Officer',
            gender='Female',
            dob=date(1998, 8, 8),
            services_used='library',
            status='approved'
        )
        self.client.login(username='singlealumni', password='Password123!')
        resp_alumni = self.client.get(reverse('users:alumni_dashboard'))
        self.assertFalse(resp_alumni.context.get('is_dual_user'))
        self.assertNotContains(resp_alumni, 'id="profileSwitcherPopover"')


class TemporaryStudentAndSingleRequestTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username='staffteacher', password='Password123!', is_staff=True
        )
        self.temp_student_user = User.objects.create_user(
            username='tempstudent', password='Password123!'
        )
        self.perm_student_user = User.objects.create_user(
            username='permstudent', password='Password123!'
        )

        self.seat_g1 = Seat.objects.create(
            seat_number='01', floor='Ground Floor', is_shift_enabled=True, status='occupied'
        )
        self.seat_g2 = Seat.objects.create(
            seat_number='02', floor='Ground Floor', is_shift_enabled=True, status='available'
        )

        self.temp_profile = StudentProfile.objects.create(
            user=self.temp_student_user,
            full_name='Temp Student',
            dob=date(2002, 2, 2),
            sex='male',
            service_type='Library',
            status='admitted',
            is_admitted=True,
            seat=self.seat_g1,
            shift='morning'
        )

        self.perm_profile = StudentProfile.objects.create(
            user=self.perm_student_user,
            full_name='Perm Student',
            dob=date(2001, 1, 1),
            sex='male',
            service_type='Library',
            status='admitted',
            is_admitted=True,
            seat=self.seat_g2,
            shift='morning'
        )

        # Temp student has partial assignment on seat_g1
        self.temp_assignment = SeatAssignment.objects.create(
            student=self.temp_profile,
            seat=self.seat_g1,
            shift_type='morning',
            is_active=True,
            is_partial=True
        )

        # Perm student has permanent assignment on seat_g2
        self.perm_assignment = SeatAssignment.objects.create(
            student=self.perm_profile,
            seat=self.seat_g2,
            shift_type='morning',
            is_active=True,
            is_partial=False
        )

    def test_temporary_student_cannot_request_hold(self):
        """Temporary students cannot put seat or shift on hold."""
        self.client.login(username='tempstudent', password='Password123!')
        resp = self.client.post(
            reverse('users:api_request_seat_hold'),
            data=json.dumps({
                'start_date': (date.today() + timedelta(days=5)).strftime('%Y-%m-%d'),
                'duration': '1 month'
            }),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn('Temporary students cannot put seat or shift on hold', resp.json().get('message', ''))

    def test_temporary_student_can_request_leave(self):
        """Temporary students can submit a leave/withdraw request."""
        self.client.login(username='tempstudent', password='Password123!')
        resp = self.client.post(
            reverse('users:api_request_seat_leave'),
            data=json.dumps({'reason': 'Need to withdraw'}),
            content_type='application/json'
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get('status'), 'success')
        self.assertTrue(SeatLeaveRequest.objects.filter(student=self.temp_profile, status='pending').exists())

    def test_single_active_request_restriction(self):
        """Students cannot send another request when one is already pending."""
        self.client.login(username='tempstudent', password='Password123!')
        # Submit leave request
        self.client.post(reverse('users:api_request_seat_leave'), data=json.dumps({}), content_type='application/json')

        # Try to submit seat switch request
        switch_resp = self.client.post(
            reverse('users:api_request_seat_switch'),
            data=json.dumps({
                'seat_number': '02',
                'floor': 'Ground Floor',
                'shift': 'morning'
            }),
            content_type='application/json'
        )
        self.assertEqual(switch_resp.status_code, 400)
        self.assertIn('already have an active request', switch_resp.json().get('message', ''))

        # Cancel leave request
        cancel_resp = self.client.post(reverse('users:api_cancel_seat_leave'))
        self.assertEqual(cancel_resp.status_code, 200)

        # Now switch request should succeed
        switch_resp2 = self.client.post(
            reverse('users:api_request_seat_switch'),
            data=json.dumps({
                'seat_number': '02',
                'floor': 'Ground Floor',
                'shift': 'morning'
            }),
            content_type='application/json'
        )
        self.assertEqual(switch_resp2.status_code, 200)

    def test_teacher_approve_leave_request_frees_seat(self):
        """Teacher approving a leave request terminates temporary assignment and clears seat."""
        leave_req = SeatLeaveRequest.objects.create(
            student=self.temp_profile,
            seat=self.seat_g1,
            shift='morning',
            status='pending'
        )
        self.client.login(username='staffteacher', password='Password123!')
        resp = self.client.post(reverse('users:approve_seat_leave', kwargs={'pk': leave_req.pk}))
        self.assertEqual(resp.status_code, 200)

        self.temp_profile.refresh_from_db()
        self.temp_assignment.refresh_from_db()
        self.assertIsNone(self.temp_profile.seat)
        self.assertFalse(self.temp_assignment.is_active)

    def test_student_hold_change_request_and_teacher_approval(self):
        """Student on hold can request to expand/shorten hold, and teacher can approve."""
        # Put perm_student on hold first
        today = timezone.localdate()
        self.perm_assignment.hold_status = 'active'
        self.perm_assignment.hold_start_date = today - timedelta(days=5)
        self.perm_assignment.hold_end_date = today + timedelta(days=10)
        self.perm_assignment.save()
        self.perm_profile.status = 'on_hold'
        self.perm_profile.save()
        self.seat_g2.hold_status = 'active'
        self.seat_g2.hold_start_date = today - timedelta(days=5)
        self.seat_g2.hold_end_date = today + timedelta(days=10)
        self.seat_g2.save()

        self.client.login(username='permstudent', password='Password123!')

        # 1. Student on hold cannot request switch seat
        switch_resp = self.client.post(
            reverse('users:api_request_seat_switch'),
            data=json.dumps({
                'seat_number': '01',
                'floor': 'Ground Floor',
                'shift': 'morning'
            }),
            content_type='application/json'
        )
        self.assertEqual(switch_resp.status_code, 400)
        self.assertIn('on hold', switch_resp.json().get('message', '').lower())

        # 2. Date validation: cannot select date < 2 days
        too_soon_resp = self.client.post(
            reverse('users:api_request_hold_change'),
            data=json.dumps({
                'requested_end_date': (today + timedelta(days=1)).isoformat(),
                'reason': 'Want earlier'
            }),
            content_type='application/json'
        )
        self.assertEqual(too_soon_resp.status_code, 400)
        self.assertIn('less than 2 days', too_soon_resp.json().get('message', ''))

        # 3. Valid hold change request
        valid_date = today + timedelta(days=25)
        change_resp = self.client.post(
            reverse('users:api_request_hold_change'),
            data=json.dumps({
                'requested_end_date': valid_date.isoformat(),
                'reason': 'Extended exams'
            }),
            content_type='application/json'
        )
        self.assertEqual(change_resp.status_code, 200)

        req = SeatHoldChangeRequest.objects.filter(student=self.perm_profile, status='pending').first()
        self.assertIsNotNone(req)
        self.assertEqual(req.requested_end_date, valid_date)

        # 4. Single active request rule: cannot submit another request while hold change is pending
        change_resp2 = self.client.post(
            reverse('users:api_request_hold_change'),
            data=json.dumps({
                'requested_end_date': (today + timedelta(days=30)).isoformat()
            }),
            content_type='application/json'
        )
        self.assertEqual(change_resp2.status_code, 400)
        self.assertIn('already have an active request', change_resp2.json().get('message', ''))

        # 5. Teacher approves hold change
        self.client.login(username='staffteacher', password='Password123!')
        appr_resp = self.client.post(reverse('users:approve_hold_change', kwargs={'pk': req.pk}))
        self.assertEqual(appr_resp.status_code, 200)

        self.seat_g2.refresh_from_db()
        self.perm_assignment.refresh_from_db()
        self.assertEqual(self.seat_g2.hold_end_date, valid_date)
        self.assertEqual(self.perm_assignment.hold_end_date, valid_date)

    def test_teacher_direct_expand_shorten_hold(self):
        """Teacher can directly expand or shorten an active hold via seat action API."""
        today = timezone.localdate()
        self.perm_assignment.hold_status = 'active'
        self.perm_assignment.hold_start_date = today - timedelta(days=2)
        self.perm_assignment.hold_end_date = today + timedelta(days=5)
        self.perm_assignment.save()
        self.seat_g2.hold_status = 'active'
        self.seat_g2.hold_start_date = today - timedelta(days=2)
        self.seat_g2.hold_end_date = today + timedelta(days=5)
        self.seat_g2.save()

        self.client.login(username='staffteacher', password='Password123!')

        # 1. Cannot select today or past date
        past_resp = self.client.post(
            reverse('users:api_seat_action'),
            data=json.dumps({
                'action': 'expand_shorten_hold',
                'seat_number': '02',
                'floor': 'Ground Floor',
                'student_id': self.perm_profile.id,
                'new_end_date': today.isoformat()
            }),
            content_type='application/json'
        )
        self.assertEqual(past_resp.status_code, 400)
        self.assertIn('tomorrow', past_resp.json().get('message', '').lower())

        # 2. Select valid future date (tomorrow or later)
        new_end = today + timedelta(days=15)
        ok_resp = self.client.post(
            reverse('users:api_seat_action'),
            data=json.dumps({
                'action': 'expand_shorten_hold',
                'seat_number': '02',
                'floor': 'Ground Floor',
                'student_id': self.perm_profile.id,
                'new_end_date': new_end.isoformat()
            }),
            content_type='application/json'
        )
        self.assertEqual(ok_resp.status_code, 200)

        self.seat_g2.refresh_from_db()
        self.perm_assignment.refresh_from_db()
        self.assertEqual(self.seat_g2.hold_end_date, new_end)
        self.assertEqual(self.perm_assignment.hold_end_date, new_end)











