# users/tests_account_deletion.py
import datetime
import json
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q
from social_core.exceptions import AuthForbidden

from unittest.mock import patch

from users.models import (
    StudentProfile,
    StudentAchievement,
    Seat,
    SeatAssignment,
    SeatSpecialRequest,
    FeeTransaction,
    QuarantineIdentity,
    TodoTask,
    Notification,
    Course,
    CourseQuestion,
    CourseAnswer,
    PushSubscription,
    Complaint,
    DirectChatSession,
    Message,
)
from users.forms import InitialRegisterForm
from users.account_deletion import (
    is_identity_quarantined,
    quarantine_identity,
    cleanup_expired_quarantines,
    perform_account_deletion,
    normalize_identity,
)
from users.views import link_existing_account_by_email


class AccountDeletionTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        # Create test seat
        self.seat = Seat.objects.create(
            seat_number="101",
            floor="Ground Floor",
            status="occupied"
        )


    def test_normalize_identity(self):
        self.assertEqual(normalize_identity("  TestUser  "), "testuser")
        self.assertEqual(normalize_identity("TEST@EXAMPLE.COM"), "test@example.com")
        self.assertEqual(normalize_identity(""), "")

    def test_quarantine_expiry_and_lookup(self):
        now = timezone.now()
        # Active quarantine
        quarantine_identity(username="activeuser", email="active@example.com", days=7)
        is_q_user, field_u = is_identity_quarantined(username="ActiveUser")
        is_q_email, field_e = is_identity_quarantined(email="ACTIVE@example.com")
        self.assertTrue(is_q_user)
        self.assertEqual(field_u, "username")
        self.assertTrue(is_q_email)
        self.assertEqual(field_e, "email")

        # Expired quarantine (manually shift expiry to the past)
        record = QuarantineIdentity.objects.get(username_normalized="activeuser")
        record.quarantine_until = now - datetime.timedelta(days=1)
        record.save()

        is_q_expired, _ = is_identity_quarantined(username="activeuser")
        self.assertFalse(is_q_expired)

        # Cleanup expired
        purged = cleanup_expired_quarantines()
        self.assertGreaterEqual(purged, 1)

    def test_guest_account_deletion(self):
        guest = User.objects.create_user(
            username="guestuser",
            email="guest@example.com",
            password="StrongPassword123!"
        )
        TodoTask.objects.create(user=guest, category="TASK", metadata={"text": "My Task"})
        Notification.objects.create(user=guest, title="Welcome", message="Welcome to ABCD")

        self.client.login(username="guestuser", password="StrongPassword123!")

        # 1. Invalid confirmation string rejected
        res = self.client.post(reverse("users:delete_account"), {
            "password": "StrongPassword123!",
            "confirmation_text": "delete profile"  # wrong text
        })
        self.assertEqual(res.status_code, 400)
        self.assertTrue(User.objects.filter(username="guestuser").exists())

        # 2. Invalid password rejected
        res = self.client.post(reverse("users:delete_account"), {
            "password": "WrongPassword!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 400)
        self.assertTrue(User.objects.filter(username="guestuser").exists())

        # 3. Successful deletion
        res = self.client.post(reverse("users:delete_account"), {
            "password": "StrongPassword123!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")

        # User is deleted from auth_user
        self.assertFalse(User.objects.filter(username="guestuser").exists())
        # To-Dos and notifications are deleted
        self.assertFalse(TodoTask.objects.filter(user=guest).exists())
        self.assertFalse(Notification.objects.filter(user=guest).exists())

        # Identity is quarantined
        is_q, _ = is_identity_quarantined(username="guestuser", email="guest@example.com")
        self.assertTrue(is_q)

    def test_student_account_deletion_with_seat_release(self):
        student_user = User.objects.create_user(
            username="studentalice",
            email="alice@example.com",
            password="AlicePassword123!"
        )
        profile = StudentProfile.objects.create(
            user=student_user,
            full_name="Alice Student",
            mobile_number="9876543210",
            service_type="Library",
            seat=self.seat
        )
        SeatAssignment.objects.create(
            seat=self.seat,
            student=profile,
            is_active=True
        )

        self.client.login(username="studentalice", password="AlicePassword123!")

        res = self.client.post(reverse("users:delete_account"), {
            "password": "AlicePassword123!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 200)

        # Seat is freed and recalculated to available
        self.seat.refresh_from_db()
        self.assertEqual(self.seat.status, "available")
        self.assertIsNone(self.seat.hold_student)

        # Student user and profile deleted (no fee history)
        self.assertFalse(User.objects.filter(username="studentalice").exists())
        self.assertFalse(StudentProfile.objects.filter(id=profile.id).exists())

        # Quarantined
        is_q, _ = is_identity_quarantined(username="studentalice", email="alice@example.com")
        self.assertTrue(is_q)

    def test_student_with_financial_history_is_anonymized_not_cascaded(self):
        student_user = User.objects.create_user(
            username="feepayingstudent",
            email="feepayer@example.com",
            password="FeePassword123!"
        )
        profile = StudentProfile.objects.create(
            user=student_user,
            full_name="Bob Payer",
            mobile_number="9876543211",
            whatsapp_number="9876543211",
            sex="Male",
            service_type="Coaching"
        )
        # Create an official fee transaction
        fee_tx = FeeTransaction.objects.create(
            student=profile,
            receipt_number="ABCD_26/999999",
            payment_date=timezone.localdate(),
            service_snapshot="Coaching Full Batch",
            months_snapshot=[{"month": "January", "amount": 1500, "status": "Paid"}],
            total_amount=1500.00
        )

        self.client.login(username="feepayingstudent", password="FeePassword123!")

        res = self.client.post(reverse("users:delete_account"), {
            "password": "FeePassword123!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 200)

        # FeeTransaction MUST STILL EXIST (statutory retention)
        self.assertTrue(FeeTransaction.objects.filter(id=fee_tx.id).exists())

        # StudentProfile MUST BE ANONYMIZED
        profile.refresh_from_db()
        self.assertEqual(profile.full_name, "Former Student")
        self.assertEqual(profile.mobile_number, "")
        self.assertEqual(profile.whatsapp_number, "")
        self.assertEqual(profile.sex, "Other")
        self.assertEqual(profile.status, "deleted")

        # User account is deactivated and scrambled
        student_user.refresh_from_db()
        self.assertFalse(student_user.is_active)
        self.assertTrue(student_user.username.startswith("deleted_"))
        self.assertFalse(student_user.has_usable_password())

        # Original username and email quarantined
        is_q, _ = is_identity_quarantined(username="feepayingstudent", email="feepayer@example.com")
        self.assertTrue(is_q)

    def test_alumni_account_deletion(self):
        alumni_user = User.objects.create_user(
            username="alumnijohn",
            email="alumni@example.com",
            password="AlumniPassword123!"
        )
        achievement = StudentAchievement.objects.create(
            user=alumni_user,
            first_name="John",
            last_name="Doe",
            current_post="Civil Services",
            selection_year=2025,
            dob=datetime.date(2000, 1, 1),
            status="approved"
        )


        self.client.login(username="alumnijohn", password="AlumniPassword123!")

        res = self.client.post(reverse("users:delete_account"), {
            "password": "AlumniPassword123!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 200)

        self.assertFalse(User.objects.filter(username="alumnijohn").exists())
        self.assertFalse(StudentAchievement.objects.filter(id=achievement.id).exists())
        is_q, _ = is_identity_quarantined(username="alumnijohn")
        self.assertTrue(is_q)

    def test_registration_form_blocks_quarantined_identity(self):
        quarantine_identity(username="quarantineduser", email="quarantined@example.com", days=7)

        # Case variations on username
        form1 = InitialRegisterForm(data={
            "username": "QuarantinedUser",
            "email": "fresh@example.com",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!"
        })
        self.assertFalse(form1.is_valid())
        self.assertIn("username is temporarily reserved", str(form1.errors.get("username")))

        # Case variations on email
        form2 = InitialRegisterForm(data={
            "username": "freshuser",
            "email": "QUARANTINED@EXAMPLE.COM",
            "password1": "StrongPass123!",
            "password2": "StrongPass123!"
        })
        self.assertFalse(form2.is_valid())
        self.assertIn("email address is temporarily reserved", str(form2.errors.get("email")))

    def test_google_oauth_pipeline_rejects_quarantined_email(self):
        quarantine_identity(username="oauthquarantine", email="oauthq@example.com", days=7)

        class DummyBackend:
            name = 'google-oauth2'

        with self.assertRaises(AuthForbidden):
            link_existing_account_by_email(
                backend=DummyBackend(),
                details={"email": "OAUTHQ@EXAMPLE.COM"}
            )

    def test_staff_cannot_self_delete(self):
        staff = User.objects.create_user(
            username="staffadmin",
            email="staff@example.com",
            password="AdminPassword123!",
            is_staff=True
        )
        self.client.login(username="staffadmin", password="AdminPassword123!")

        res = self.client.post(reverse("users:delete_account"), {
            "password": "AdminPassword123!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 403)
        self.assertTrue(User.objects.filter(username="staffadmin").exists())

    def test_security_constraints(self):
        # 1. Anonymous user blocked
        res = self.client.post(reverse("users:delete_account"), {
            "password": "AnyPassword",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 302)  # redirect to login

        # 2. GET method blocked
        test_user = User.objects.create_user(
            username="gettester",
            email="get@example.com",
            password="Pass!"
        )
        self.client.login(username="gettester", password="Pass!")
        get_res = self.client.get(reverse("users:delete_account"))
        self.assertEqual(get_res.status_code, 405)  # Method Not Allowed

    def test_public_pages_load(self):
        res1 = self.client.get(reverse("users:delete_account_info"))
        self.assertEqual(res1.status_code, 200)
        self.assertContains(res1, "Account Deletion Policy")
        self.assertContains(res1, "Certain financial or accounting records may be retained")

        res2 = self.client.get(reverse("users:account_deleted"))
        self.assertEqual(res2.status_code, 200)
        self.assertContains(res2, "Account Successfully Deleted")

    @patch('users.email_service.send_html_email')
    @patch('pywebpush.webpush')
    def test_student_deletion_with_course_questions_and_answers_regression(self, mock_webpush, mock_email):
        """Verify student deletion does NOT crash with IntegrityError on Q&A models."""
        course = Course.objects.create(title="History 101", description="Test Course")
        student_user = User.objects.create_user(
            username="qa_student",
            email="qa_student@example.com",
            password="QAPassword123!"
        )
        profile = StudentProfile.objects.create(
            user=student_user,
            full_name="QA Student",
            mobile_number="9876543299",
            service_type="Coaching"
        )
        question = CourseQuestion.objects.create(
            course=course,
            student=profile,
            question="What is the syllabus timeline?"
        )
        answer = CourseAnswer.objects.create(
            question=question,
            user=student_user,
            answer_text="Here is my question follow up."
        )

        self.client.login(username="qa_student", password="QAPassword123!")
        res = self.client.post(reverse("users:delete_account"), {
            "password": "QAPassword123!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")

        # Question is preserved with student=None
        question.refresh_from_db()
        self.assertIsNone(question.student)
        self.assertEqual(question.author_name, "Deleted user")
        self.assertIn("Deleted user", str(question))

        # Answer is preserved with user=None
        answer.refresh_from_db()
        self.assertIsNone(answer.user)
        self.assertEqual(answer.author_name, "Deleted user")
        self.assertIn("Deleted user", str(answer))

        # Non-staff cannot delete orphaned QA item
        other_user = User.objects.create_user(
            username="other_stud",
            email="other@example.com",
            password="OtherPassword123!"
        )
        self.client.login(username="other_stud", password="OtherPassword123!")
        del_qa_res = self.client.post(
            reverse("users:delete_qa_item"),
            data=json.dumps({"type": "question", "id": question.id}),
            content_type="application/json"
        )
        self.assertEqual(del_qa_res.status_code, 403)

    @patch('users.email_service.send_html_email')
    def test_guest_deletion_does_not_wipe_unrelated_guest_seat_requests_regression(self, mock_email):
        """Verify guest deletion only purges their own SeatSpecialRequest without wiping other guests."""
        guest_a = User.objects.create_user(username="guest_a", email="ga@test.com", password="PassA123!")
        guest_b = User.objects.create_user(username="guest_b", email="gb@test.com", password="PassB123!")

        req_a = SeatSpecialRequest.objects.create(
            user=guest_a,
            student=None,
            seat=self.seat,
            requested_shift="morning"
        )
        req_b = SeatSpecialRequest.objects.create(
            user=guest_b,
            student=None,
            seat=self.seat,
            requested_shift="morning"
        )

        self.client.login(username="guest_a", password="PassA123!")
        res = self.client.post(reverse("users:delete_account"), {
            "password": "PassA123!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 200)

        # req_a deleted, req_b preserved
        self.assertFalse(SeatSpecialRequest.objects.filter(id=req_a.id).exists())
        self.assertTrue(SeatSpecialRequest.objects.filter(id=req_b.id).exists())

    @patch('users.email_service.send_html_email')
    @patch('pywebpush.webpush')
    def test_student_deletion_with_push_and_json_import_regression(self, mock_webpush, mock_email):
        """Verify silent push runs without NameError: name 'json' is not defined."""
        user = User.objects.create_user(username="push_user", email="push@test.com", password="PushPass123!")
        StudentProfile.objects.create(user=user, full_name="Push User", mobile_number="9876543201")
        PushSubscription.objects.create(
            user=user,
            endpoint="https://example.com/push/test",
            keys={"p256dh": "key1", "auth": "auth1"}
        )

        self.client.login(username="push_user", password="PushPass123!")
        res = self.client.post(reverse("users:delete_account"), {
            "password": "PushPass123!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")
        self.assertFalse(PushSubscription.objects.filter(user=user).exists())

    @patch('users.account_deletion.perform_account_deletion')
    def test_unexpected_error_logs_and_returns_generic_message(self, mock_perform):
        """Verify unhandled exceptions return 500 with generic message and release concurrency lock."""
        from django.db import DatabaseError
        mock_perform.side_effect = DatabaseError("Simulated Neon DB connection timeout")

        user = User.objects.create_user(username="err_user", email="err@test.com", password="ErrPass123!")
        self.client.login(username="err_user", password="ErrPass123!")

        res = self.client.post(reverse("users:delete_account"), {
            "password": "ErrPass123!",
            "confirmation_text": "DELETE THIS PROFILE"
        })
        self.assertEqual(res.status_code, 500)
        self.assertEqual(
            res.json().get("message"),
            "An unexpected error occurred during account deletion. Please try again or contact support."
        )

        # Lock was cleared
        from django.core.cache import cache
        self.assertIsNone(cache.get(f"account_deletion_lock_{user.id}"))

    @patch('users.email_service.send_html_email')
    def test_deletion_otp_uses_correct_template_and_no_registration_wording(self, mock_email):
        """Verify request_delete_account_otp sends account_deletion_otp.html without registration wording."""
        from django.template.loader import render_to_string

        user = User.objects.create_user(
            username="otp_test_user",
            email="otp_test@example.com",
            password="TestPassword123!"
        )
        self.client.login(username="otp_test_user", password="TestPassword123!")

        res = self.client.post(reverse("users:request_delete_account_otp"))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json().get("status"), "ok")

        # Verify send_html_email was called with account_deletion_otp.html
        self.assertTrue(mock_email.called)
        call_kwargs = mock_email.call_args.kwargs
        self.assertEqual(call_kwargs.get("template"), "emails/account_deletion_otp.html")
        self.assertEqual(call_kwargs.get("to_email"), "otp_test@example.com")

        context = call_kwargs.get("context", {})
        rendered_html = render_to_string("emails/account_deletion_otp.html", context)

        # Assert registration wording is completely absent
        self.assertNotIn("Register Verification", rendered_html)
        self.assertNotIn("Complete Registration", rendered_html)
        self.assertNotIn("Thank you for registering", rendered_html)

        # Assert deletion content is present
        self.assertIn("Account Deletion Request", rendered_html)
        self.assertIn("Not you? Contact ABCD Asst.", rendered_html)
        self.assertIn("fee transactions", rendered_html)
        self.assertIn("Valid for <strong>10 minutes</strong>", rendered_html)
        self.assertIn(context.get("otp"), rendered_html)

    def test_guidy_deep_link_chat_with(self):
        """Verify /guidy/?chat_with=<id> opens direct chat and redirects logged-out users."""
        asst = User.objects.create_superuser(
            username="asst_admin",
            email="vd19055@gmail.com",
            password="AdminPassword123!"
        )
        student_user = User.objects.create_user(
            username="deep_link_stud",
            email="dl@test.com",
            password="StudPassword123!"
        )

        # 1. Logged-out user is redirected to login with next param
        self.client.logout()
        res_logged_out = self.client.get(f"{reverse('users:guidy_home')}?chat_with={asst.id}")
        self.assertEqual(res_logged_out.status_code, 302)
        self.assertIn(reverse('users:login'), res_logged_out.url)
        self.assertIn("chat_with", res_logged_out.url)

        # 2. Logged-in user has DirectChatSession created and loaded
        self.client.login(username="deep_link_stud", password="StudPassword123!")
        res_logged_in = self.client.get(f"{reverse('users:guidy_home')}?chat_with={asst.id}")
        self.assertEqual(res_logged_in.status_code, 200)

        # Verify DirectChatSession exists
        from users.models import DirectChatSession
        session = DirectChatSession.objects.filter(
            (Q(user1=student_user, user2=asst) | Q(user1=asst, user2=student_user))
        ).first()
        self.assertIsNotNone(session)
        self.assertTrue(session.is_active)


