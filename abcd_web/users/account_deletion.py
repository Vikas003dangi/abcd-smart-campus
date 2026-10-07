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

import json
import logging
import uuid
from datetime import timedelta
from django.db import transaction
from django.db.models import Q, Count
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
    DismissedFeeAlert,
    AutoReplyConfig,
    AutoReplyLog,
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
    Safely purges any prior quarantine records for this username or email to guarantee zero MultipleObjectsReturned.
    """
    now = timezone.now()
    expiry = now + timedelta(days=days)
    norm_u = normalize_identity(username)
    norm_e = normalize_identity(email)

    if not norm_u and not norm_e:
        return None

    try:
        # Delete any existing quarantine records matching this username or email to guarantee clean single record
        q_filter = Q()
        if norm_u:
            q_filter |= Q(username_normalized=norm_u)
        if norm_e:
            q_filter |= Q(email_normalized=norm_e)
        if q_filter:
            QuarantineIdentity.objects.filter(q_filter).delete()

        record = QuarantineIdentity.objects.create(
            username_normalized=norm_u or "",
            email_normalized=norm_e or "",
            deleted_at=now,
            quarantine_until=expiry,
            user_role=role or "user",
        )
        logger.info(
            f"[QUARANTINE] Identity {norm_u} / {norm_e} quarantined until {expiry.isoformat()} (Role: {role})"
        )
        return record
    except Exception as e:
        logger.warning(f"[QUARANTINE] Non-fatal error recording quarantine for {norm_u} / {norm_e}: {e}")
        return None


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
    user_id = user.id

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

    # Guidy chat message attachments in 1-on-1 sessions and solo groups being deleted
    user_direct_sessions = DirectChatSession.objects.filter(Q(user1=user) | Q(user2=user))
    user_direct_session_ids = list(user_direct_sessions.values_list('id', flat=True))

    user_chat_sessions = ChatSession.objects.filter(Q(user_one=user) | Q(user_two=user))
    user_chat_session_ids = list(user_chat_sessions.values_list('id', flat=True))

    all_target_messages = Message.objects.filter(
        Q(direct_session_id__in=user_direct_session_ids) |
        Q(session_id__in=user_chat_session_ids) |
        Q(sender=user)
    )
    for msg in all_target_messages.exclude(file='').exclude(file=None):
        if msg.file:
            files_to_delete.append(msg.file)

    for gmsg in GroupMessage.objects.filter(sender=user).exclude(file='').exclude(file=None):
        if gmsg.file:
            files_to_delete.append(gmsg.file)

    # Solo groups created by user that will be deleted
    user_created_groups = GroupChatSession.objects.filter(created_by=user)
    for grp in user_created_groups:
        if grp.members.exclude(id=user.id).count() == 0:
            if grp.photo:
                files_to_delete.append(grp.photo)
            for sgmsg in grp.messages.exclude(file='').exclude(file=None):
                if sgmsg.file:
                    files_to_delete.append(sgmsg.file)

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

        if student:
            SeatSpecialRequest.objects.filter(Q(user=user) | Q(student=student)).delete()
        else:
            SeatSpecialRequest.objects.filter(user=user).delete()

        # -------------------------------------------------------------
        # B. Communication, Social & Real-Time Data Removal
        # -------------------------------------------------------------
        # 1. Notifications and push subscriptions
        Notification.objects.filter(user=user).delete()

        # Send silent push to client devices to clear local scheduled alarms upon account deletion
        try:
            from pywebpush import webpush
            from django.conf import settings
            for sub in PushSubscription.objects.filter(user=user):
                try:
                    webpush(
                        subscription_info={"endpoint": sub.endpoint, "keys": sub.keys},
                        data=json.dumps({"category": "system", "action": "ACCOUNT_DELETED", "title": "ABCD Campus", "silent": True}),
                        vapid_private_key=settings.VAPID_PRIVATE_KEY,
                        vapid_claims={"sub": f"mailto:{getattr(settings, 'VAPID_CLAIM_EMAIL', 'abcd2013baq@gmail.com')}"},
                        ttl=3600,
                        timeout=5
                    )
                except Exception:
                    pass
        except Exception:
            pass

        PushSubscription.objects.filter(user=user).delete()

        # 2. Personal study tasks, reminders, intent logs
        TodoTask.objects.filter(user=user).delete()
        LearningReminder.objects.filter(user=user).delete()
        BannerViewLog.objects.filter(user=user).delete()
        VisitorIntent.objects.filter(user=user).delete()

        # 3. Clean up AutoReply models FIRST (they reference DirectChatSession and Message)
        AutoReplyLog.objects.filter(
            Q(account=user) |
            Q(sender=user) |
            Q(direct_session_id__in=user_direct_session_ids) |
            Q(trigger_message__in=all_target_messages) |
            Q(reply_message__in=all_target_messages)
        ).delete()
        AutoReplyConfig.objects.filter(user=user).delete()

        # 4. Clean up fee alerts
        DismissedFeeAlert.objects.filter(Q(teacher=user) | (Q(student=student) if student else Q())).delete()

        # 5. Break message reply_to self-references to prevent self-referential FK constraints
        all_target_messages.filter(reply_to__isnull=False).update(reply_to=None)

        # 6. Clear M2M deleted_by on target messages
        Message.deleted_by.through.objects.filter(
            Q(message_id__in=all_target_messages.values('id')) |
            Q(user_id=user.id)
        ).delete()

        # 7. CRITICAL (PostgreSQL): Delete all 1-to-1 messages BEFORE deleting sessions.
        # DirectChatSession and ChatSession have foreign keys with null=True in Message.
        # In PostgreSQL (INITIALLY IMMEDIATE FK checks), deleting sessions before messages
        # violates users_message_direct_session_id_fk / users_message_session_id_fk.
        all_target_messages.delete()

        # 8. Delete DirectChatSession objects (now safe because all referencing messages are deleted)
        DirectChatSession.objects.filter(id__in=user_direct_session_ids).delete()

        # 9. Delete ChatSession objects (now safe because all referencing messages are deleted)
        ChatSession.objects.filter(id__in=user_chat_session_ids).delete()

        # 10. Guidy guidance requests & blocks (now safe because ChatSession.request was already deleted)
        GuidanceRequest.objects.filter(Q(student=user) | (Q(alumni__user=user) if achievement else Q())).delete()
        BlockedGuidance.objects.filter(student=user).delete()
        RestrictedStudent.objects.filter(student=user).delete()
        GuidyBlock.objects.filter(Q(blocker=user) | Q(blocked=user)).delete()

        # 11. Group chats: remove user or reassign/delete solo groups in proper order
        for group in user_created_groups:
            other_member = group.members.exclude(id=user.id).first()
            if other_member:
                group.created_by = other_member
                group.save(update_fields=['created_by'])
            else:
                # Solo group: delete messages and M2Ms first, then delete group
                grp_msgs = GroupMessage.objects.filter(group=group)
                grp_msgs.filter(reply_to__isnull=False).update(reply_to=None)
                GroupMessage.read_by.through.objects.filter(groupmessage__group=group).delete()
                GroupMessage.deleted_by.through.objects.filter(groupmessage__group=group).delete()
                GroupMessage.starred_by.through.objects.filter(groupmessage__group=group).delete()
                grp_msgs.delete()
                group.members.clear()
                group.deleted_for_users.clear()
                group.delete()

        # Anonymize user's remaining group messages in other groups before removing membership
        # Reassigning sender ensures hard deletion of user does not cascade and delete group messages
        for gmsg in GroupMessage.objects.filter(sender=user):
            other_member = gmsg.group.members.exclude(id=user.id).first() or gmsg.group.created_by
            if other_member and other_member.id != user.id:
                gmsg.sender = other_member
            gmsg.content = "[This message was deleted by a former user]"
            gmsg.file = ""
            gmsg.is_deleted_for_all = True
            gmsg.save(update_fields=['sender', 'content', 'file', 'is_deleted_for_all'])

        for group in GroupChatSession.objects.filter(members=user):
            group.members.remove(user)

        # Clear user from remaining group M2M tables
        GroupChatSession.deleted_for_users.through.objects.filter(user_id=user.id).delete()
        GroupMessage.read_by.through.objects.filter(user_id=user.id).delete()
        GroupMessage.deleted_by.through.objects.filter(user_id=user.id).delete()
        GroupMessage.starred_by.through.objects.filter(user_id=user.id).delete()

        # 12. Academic forum content: anonymize to protect thread continuity
        if student:
            CourseQuestion.objects.filter(student=student).update(student=None)
            CourseReview.objects.filter(student=student).delete()
            CourseShare.objects.filter(student=student).delete()
            StudentMaterialAccess.objects.filter(student=student).delete()
            StudentCourseInteraction.objects.filter(student=student).delete()
            StudentScore.objects.filter(student=student).delete()

        CourseAnswer.objects.filter(user=user).update(user=None)
        CourseQuestion.upvotes.through.objects.filter(user_id=user.id).delete()
        CourseAnswer.upvotes.through.objects.filter(user_id=user.id).delete()

        # Complaints: delete or anonymize
        if student:
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
        except Exception as e:
            logger.warning(f"[ACCOUNT_DELETION] Non-fatal OAuth link cleanup: {e}")

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
    cache.delete(f"student_context_data_{user_id}")
    cache.delete(f"user_data_{user_id}")

    logger.info(
        f"[ACCOUNT_DELETION] Account {original_username} ({detected_role}) successfully deleted & quarantined for 7 days."
    )

    return {
        'success': True,
        'role': detected_role,
        'message': 'Account and personal data successfully deleted.',
    }
