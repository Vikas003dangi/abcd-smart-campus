# users/account_deletion.py
"""
Secure Account Deletion & 7-Day Identity Quarantine Service Layer
================================================================
Handles self-service account deletion across Student, Alumni, and Guest users.
Enforces:
1. Exact confirmation text ("DELETE THIS PROFILE") + password or email OTP verification.
2. Complete personal data removal (profile, photos, messages, to-dos, subscriptions).
3. Statutory accounting & fee record preservation with aggressive personal data anonymization.
4. Clean seat detachment and real-time WebSocket seat grid broadcast.
5. External Cloudinary / local storage cleanup safely executed outside atomic DB transactions.
6. 7-Day username & email quarantine with automatic expiry.
7. Complete session invalidation.
"""

import logging
import uuid
from datetime import timedelta
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.core.cache import cache

from .models import (
    QuarantineIdentity,
    StudentProfile,
    StudentAchievement,
    Seat,
    SeatAssignment,
    SeatHoldRequest,
    SeatSwitchRequest,
    SeatLeaveRequest,
    SeatHoldChangeRequest,
    SeatSpecialRequest,
    Complaint,
    Payment,
    FeeTransaction,
    Notification,
    PushSubscription,
    TodoTask,
    LearningReminder,
    BannerViewLog,
    VisitorIntent,
    GuidanceRequest,
    ChatSession,
    DirectChatSession,
    Message,
    GroupChatSession,
    GroupMessage,
    GuidyBlock,
    BlockedGuidance,
    RestrictedStudent,
    CourseQuestion,
    CourseAnswer,
    CourseReview,
    CourseShare,
    StudentMaterialAccess,
    StudentCourseInteraction,
    StudentScore,
    safe_delete_file_field,
)

logger = logging.getLogger(__name__)

# Default quarantine duration in days
DEFAULT_QUARANTINE_DAYS = 7
EXACT_CONFIRMATION_TEXT = "DELETE THIS PROFILE"


# ===================================================================
# 1. QUARANTINE IDENTIFIERS & LOOKUP ENGINE
# ===================================================================

def normalize_identity(value: str) -> str:
    """Safely normalizes username or email to prevent bypasses."""
    if not value:
        return ""
    return value.strip().lower()


def is_identity_quarantined(username: str = None, email: str = None):
    """
    Checks if a username or email is currently quarantined.
    Returns (is_quarantined: bool, field_name: str | None).
    Auto-expires naturally when quarantine_until <= now.
    """
    now = timezone.now()

    if username:
        norm_u = normalize_identity(username)
        if norm_u and QuarantineIdentity.objects.filter(
            username_normalized=norm_u, quarantine_until__gt=now
        ).exists():
            return True, "username"

    if email:
        norm_e = normalize_identity(email)
        if norm_e and QuarantineIdentity.objects.filter(
            email_normalized=norm_e, quarantine_until__gt=now
        ).exists():
            return True, "email"

    return False, None


def quarantine_identity(username: str, email: str, role: str = "", days: int = DEFAULT_QUARANTINE_DAYS):
    """
    Quarantines an identity for the specified duration (default 7 days).
    Uses update_or_create to safely extend or record quarantine.
    """
    now = timezone.now()
    expiry = now + timedelta(days=days)
    norm_u = normalize_identity(username)
    norm_e = normalize_identity(email)

    if not norm_u and not norm_e:
        return None

    record, _ = QuarantineIdentity.objects.update_or_create(
        username_normalized=norm_u,
        defaults={
            'email_normalized': norm_e,
            'deleted_at': now,
            'quarantine_until': expiry,
            'user_role': role or "user",
        }
    )
    logger.info(
        f"[QUARANTINE] Identity {norm_u} / {norm_e} quarantined until {expiry.isoformat()} (Role: {role})"
    )
    return record


def cleanup_expired_quarantines():
    """
    Removes expired quarantine records.
    Can be invoked lazily during maintenance.
    """
    now = timezone.now()
    deleted_count, _ = QuarantineIdentity.objects.filter(quarantine_until__lte=now).delete()
    if deleted_count:
        logger.info(f"[QUARANTINE] Purged {deleted_count} expired quarantine records.")
    return deleted_count


# ===================================================================
# 2. COMPLETE ACCOUNT DELETION WORKFLOW
# ===================================================================

def perform_account_deletion(user, role=None):
    """
    Executes complete deletion of a user account.
    Returns:
        dict: {'success': bool, 'role': str, 'message': str}
    """
    if not user or not user.is_authenticated:
        return {'success': False, 'role': 'unknown', 'message': 'Authentication required.'}

    # Strict guard: Staff and Superuser accounts cannot self-delete via this endpoint
    if user.is_staff or user.is_superuser:
        return {'success': False, 'role': 'staff', 'message': 'Staff and administrative accounts cannot be deleted self-service.'}

    original_username = user.username
    original_email = user.email or ""

    # Detect user role if not provided
    from .utils import get_user_dashboard_type
    detected_role = role or get_user_dashboard_type(user) or "guest"

    # Pre-gather files to delete outside the database transaction
    files_to_delete = []

    # StudentProfile references
    student = getattr(user, 'profile', None)
    if student:
        if student.photo:
            files_to_delete.append(student.photo)
        if not original_email and student.email:
            original_email = student.email

        # Complaint attachments
        for complaint in Complaint.objects.filter(student=student):
            if complaint.image1: files_to_delete.append(complaint.image1)
            if complaint.image2: files_to_delete.append(complaint.image2)
            if complaint.image3: files_to_delete.append(complaint.image3)

    # Alumni achievement references
    achievement = StudentAchievement.objects.filter(user=user).first()
    if achievement:
        if achievement.photo:
            files_to_delete.append(achievement.photo)
        if not original_email and achievement.email:
            original_email = achievement.email

    # Guidy chat message attachments sent by this user
    for msg in Message.objects.filter(sender=user).exclude(file='').exclude(file=None):
        if msg.file:
            files_to_delete.append(msg.file)
    for gmsg in GroupMessage.objects.filter(sender=user).exclude(file='').exclude(file=None):
        if gmsg.file:
            files_to_delete.append(gmsg.file)

    involved_seat_ids = set()

    with transaction.atomic():
        # -------------------------------------------------------------
        # A. Seat Management & Physical Facility Disassociation
        # -------------------------------------------------------------
        if student:
            # 1. Release active holds
            held_seats = Seat.objects.filter(hold_student=student)
            for hs in held_seats:
                involved_seat_ids.add(hs.id)
            held_seats.update(
                hold_student=None,
                status='available',
                hold_status='none',
                hold_start_date=None,
                hold_end_date=None,
            )

            # 2. Deactivate seat assignments
            assignments = SeatAssignment.objects.filter(student=student)
            for sa in assignments:
                involved_seat_ids.add(sa.seat_id)
                sa.deactivate()
            assignments.delete()

            # 3. Disassociate primary seat
            if student.seat_id:
                involved_seat_ids.add(student.seat_id)
                student.seat = None
                student.save(update_fields=['seat'])

            # 4. Clear pending seat requests
            SeatHoldRequest.objects.filter(student=student).delete()
            SeatSwitchRequest.objects.filter(student=student).delete()
            SeatLeaveRequest.objects.filter(student=student).delete()
            SeatHoldChangeRequest.objects.filter(student=student).delete()

        SeatSpecialRequest.objects.filter(Q(user=user) | Q(student=student)).delete()

        # -------------------------------------------------------------
        # B. Communication, Social & Real-Time Data Removal
        # -------------------------------------------------------------
        # Notifications and push subscriptions
        Notification.objects.filter(user=user).delete()
        PushSubscription.objects.filter(user=user).delete()

        # Personal study tasks, reminders, intent logs
        TodoTask.objects.filter(user=user).delete()
        LearningReminder.objects.filter(user=user).delete()
        BannerViewLog.objects.filter(user=user).delete()
        VisitorIntent.objects.filter(user=user).delete()

        # Guidy 1-to-1 chats and guidance
        GuidanceRequest.objects.filter(Q(student=user) | (Q(alumni__user=user) if achievement else Q())).delete()
        BlockedGuidance.objects.filter(student=user).delete()
        RestrictedStudent.objects.filter(student=user).delete()
        GuidyBlock.objects.filter(Q(blocker=user) | Q(blocked=user)).delete()

        # Delete direct chat sessions and 1-to-1 messages
        DirectChatSession.objects.filter(Q(user1=user) | Q(user2=user)).delete()
        ChatSession.objects.filter(Q(user_one=user) | Q(user_two=user)).delete()
        Message.objects.filter(sender=user).delete()

        # Group chats: remove user from membership; anonymize sent group messages
        for group in GroupChatSession.objects.filter(members=user):
            group.members.remove(user)
            if group.created_by == user:
                # If group has other members, reassign creator to staff or next member
                other_member = group.members.exclude(id=user.id).first()
                if other_member:
                    group.created_by = other_member
                    group.save(update_fields=['created_by'])
                else:
                    group.delete()

        GroupMessage.objects.filter(sender=user).update(
            content="[This message was deleted by a former user]",
            file="",
            is_deleted_for_all=True,
        )


        # Academic forum content: anonymize to protect thread continuity
        if student:
            CourseQuestion.objects.filter(student=student).update(student=None)
            CourseReview.objects.filter(student=student).delete()
            CourseShare.objects.filter(student=student).delete()
            StudentMaterialAccess.objects.filter(student=student).delete()
            StudentCourseInteraction.objects.filter(student=student).delete()
            StudentScore.objects.filter(student=student).delete()

        CourseAnswer.objects.filter(user=user).update(user=None)

        # Complaints: delete or anonymize
        if student:
            # Anonymize complaint details while preserving basic metrics if needed
            Complaint.objects.filter(student=student).update(
                message="[User account and personal grievance details deleted]",
                feedback="[Account deleted]",
                image1="",
                image2="",
                image3="",
            )

        # Alumni achievement
        if achievement:
            achievement.delete()

        # Third-party OAuth links
        try:
            from social_django.models import UserSocialAuth
            UserSocialAuth.objects.filter(user=user).delete()
        except Exception:
            pass

        # -------------------------------------------------------------
        # C. Financial Retention & Core Identity Erasure / Anonymization
        # -------------------------------------------------------------
        has_financial_records = False
        if student:
            has_financial_records = (
                student.fee_transactions.exists() or student.payments.exists()
            )

        if has_financial_records and student:
            # Statutory financial retention: scrub all PII from StudentProfile
            student.full_name = "Former Student"
            student.mobile_number = ""
            student.whatsapp_number = ""
            student.dob = None
            student.sex = "Other"
            student.sex_other = "Deleted"


            student.photo = None
            student.email = ""
            student.status = "deleted"
            student.coaching_pending = False
            student.library_pending = False
            student.save()

            # Anonymize User account so it cannot log in or be used
            anon_suffix = uuid.uuid4().hex[:12]
            user.username = f"deleted_{anon_suffix}"
            user.email = f"deleted_{anon_suffix}@deleted.local"
            user.first_name = "Former"
            user.last_name = "User"
            user.is_active = False
            user.set_unusable_password()
            user.save()
        else:
            # No financial/accounting retention needed: hard delete StudentProfile and User
            if student:
                student.delete()
            user.delete()

        # -------------------------------------------------------------
        # D. Identity Quarantine (7 Days)
        # -------------------------------------------------------------
        quarantine_identity(
            username=original_username,
            email=original_email,
            role=detected_role,
            days=DEFAULT_QUARANTINE_DAYS,
        )

    # -------------------------------------------------------------
    # E. Safe External Cleanup (Outside DB Transaction)
    # -------------------------------------------------------------
    for f in files_to_delete:
        try:
            safe_delete_file_field(f)
        except Exception as e:
            logger.warning(f"[ACCOUNT_DELETION] Non-fatal error cleaning file: {e}")

    # Recalculate freed seats & broadcast live grid
    for sid in involved_seat_ids:
        try:
            s = Seat.objects.get(id=sid)
            s.recalculate_status()
        except Exception:
            pass

    if involved_seat_ids:
        try:
            from . import notifications
            notifications.broadcast_seat_update()
        except Exception:
            pass

    # Clear cached context for the user
    cache.delete(f"student_context_data_{user.id}")
    cache.delete(f"user_data_{user.id}")

    logger.info(
        f"[ACCOUNT_DELETION] Account {original_username} ({detected_role}) successfully deleted & quarantined for 7 days."
    )

    return {
        'success': True,
        'role': detected_role,
        'message': 'Account and personal data successfully deleted.',
    }
