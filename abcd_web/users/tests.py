from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta, date
from users.models import Seat, StudentProfile, SeatAssignment
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
        today = timezone.now().date()
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






