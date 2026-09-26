# users/tests_account_deletion.py
import datetime
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from social_core.exceptions import AuthForbidden

from users.models import (
    StudentProfile,
    StudentAchievement,
    Seat,
    SeatAssignment,
    FeeTransaction,
    QuarantineIdentity,
    TodoTask,
    Notification,
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
