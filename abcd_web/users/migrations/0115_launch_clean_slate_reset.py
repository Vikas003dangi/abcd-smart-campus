# Generated for ABCD Smart Campus - Official Launch Reset
# Runs once via 'python manage.py migrate' and is recorded in django_migrations,
# guaranteeing it never runs again on future deploys.

from django.db import migrations
from django.contrib.auth.hashers import make_password
from decouple import config
import logging

logger = logging.getLogger(__name__)


def launch_clean_slate_reset(apps, schema_editor):
    print("\n[Migration 0115] Starting Official Launch Clean-Slate Reset...")

    User = apps.get_model('auth', 'User')
    legit_emails = ['vd19055@gmail.com', 'abcd2013baq@gmail.com']

    # 1. Purge all non-admin user accounts
    deleted_users, _ = User.objects.exclude(email__in=legit_emails).exclude(username__in=['Vaku', 'Sandy']).delete()
    print(f"[Migration 0115] Purged {deleted_users} test/non-admin user accounts.")

    # 2. Purge all transactional, test, and historical data models
    models_to_clear = [
        # Student profiles & achievements
        'StudentAchievement', 'StudentProfile',
        # Courses, materials, and categories (clean fresh start for official courses)
        'CourseAnswer', 'CourseQuestion', 'CourseReview', 'CourseShare',
        'StudentMaterialAccess', 'StudentCourseInteraction', 'LearningReminder',
        'StudyMaterial', 'Course', 'CourseCategory',
        # Complaints & feedback
        'Complaint',
        # Notifications & push
        'Notification', 'PushSubscription', 'BroadcastMessage', 'VisitorIntent', 'BannerViewLog',
        # Library seat transactions
        'SeatAssignment', 'SeatSpecialRequest', 'SeatHoldRequest', 'SeatSwitchRequest',
        # Fees & payments
        'Payment', 'FeeTransaction', 'DismissedFeeAlert',
        # Performance records
        'PerformanceRecord', 'StudentScore',
        # Guidy chats, messages, and guidance requests
        'Message', 'GroupMessage',
        'ChatSession', 'DirectChatSession', 'GroupChatSession',
        'GuidanceRequest', 'BlockedGuidance', 'RestrictedStudent', 'GuidyBlock',
        # Todo tasks
        'TodoTask',
    ]

    for model_name in models_to_clear:
        try:
            m = apps.get_model('users', model_name)
            count, _ = m.objects.all().delete()
            if count > 0:
                print(f"[Migration 0115] Cleared {count} records from {model_name}.")
        except LookupError:
            pass
        except Exception as e:
            print(f"[Migration 0115] Notice on {model_name}: {e}")

    # 3. Clean social auth accounts for non-admin users
    try:
        UserSocialAuth = apps.get_model('social_django', 'UserSocialAuth')
        deleted_social, _ = UserSocialAuth.objects.exclude(user__email__in=legit_emails).delete()
        print(f"[Migration 0115] Purged {deleted_social} non-admin Social Auth records.")
    except (LookupError, Exception):
        pass

    # 4. Clear all existing user browser sessions
    try:
        Session = apps.get_model('sessions', 'Session')
        Session.objects.all().delete()
        print("[Migration 0115] Cleared all active browser sessions.")
    except (LookupError, Exception):
        pass

    # 5. Reset all library seats to clean 'available' status
    try:
        Seat = apps.get_model('users', 'Seat')
        Seat.objects.all().update(
            status='available',
            hold_student=None,
            hold_start_date=None,
            hold_end_date=None,
            hold_status='none',
            hold_request_date=None,
            hold_request_duration=None,
            is_locked=False,
            locked_shifts='',
            available_since=None
        )

        total_seats = Seat.objects.count()
        if total_seats == 0:
            for s in [str(i) for i in range(1, 54)]:
                shift_allowed = (40 <= int(s) <= 53)
                Seat.objects.create(
                    seat_number=s,
                    floor='Ground Floor',
                    status='available',
                    is_shift_enabled=shift_allowed
                )
            for s in [str(i) for i in range(1, 54)]:
                Seat.objects.create(
                    seat_number=s,
                    floor='1st Floor',
                    status='available',
                    is_shift_enabled=False
                )
            print("[Migration 0115] Initialized all 108 library seats.")
        else:
            Seat.objects.filter(floor='Ground Floor', seat_number__in=[str(i) for i in range(40, 54)]).update(is_shift_enabled=True)
            Seat.objects.filter(floor='Ground Floor').exclude(seat_number__in=[str(i) for i in range(40, 54)]).update(is_shift_enabled=False)
            Seat.objects.filter(floor='1st Floor').update(is_shift_enabled=False)
            print(f"[Migration 0115] Verified and reset {total_seats} library seats to available.")
    except Exception as e:
        print(f"[Migration 0115] Seat reset notice: {e}")

    # 6. Ensure Superusers Vaku & Sandy exist with proper credentials
    vaku_pass = config('VAKU_PASSWORD', default='VIK003@dan')
    vaku_user = User.objects.filter(email__iexact='vd19055@gmail.com').first()
    if not vaku_user:
        vaku_user = User.objects.filter(username__iexact='Vaku').first()
    if not vaku_user:
        vaku_user = User.objects.create(
            username='Vaku',
            email='vd19055@gmail.com',
            password=make_password(vaku_pass),
            first_name='Vikas',
            last_name='Dangi',
            is_superuser=True,
            is_staff=True,
            is_active=True
        )
        print("[Migration 0115] Created Superuser Vaku.")
    else:
        vaku_user.username = 'Vaku'
        vaku_user.email = 'vd19055@gmail.com'
        vaku_user.is_superuser = True
        vaku_user.is_staff = True
        vaku_user.is_active = True
        vaku_user.first_name = 'Vikas'
        vaku_user.last_name = 'Dangi'
        vaku_user.password = make_password(vaku_pass)
        vaku_user.save()
        print("[Migration 0115] Verified and updated Superuser Vaku.")

    sandy_pass = config('SANDY_PASSWORD', default='Sandeepanandajimaharaj')
    sandy_user = User.objects.filter(email__iexact='abcd2013baq@gmail.com').first()
    if not sandy_user:
        sandy_user = User.objects.filter(username__iexact='Sandy').first()
    if not sandy_user:
        sandy_user = User.objects.create(
            username='Sandy',
            email='abcd2013baq@gmail.com',
            password=make_password(sandy_pass),
            first_name='ABCD',
            last_name='Coaching & Library',
            is_superuser=True,
            is_staff=True,
            is_active=True
        )
        print("[Migration 0115] Created Superuser Sandy.")
    else:
        sandy_user.username = 'Sandy'
        sandy_user.email = 'abcd2013baq@gmail.com'
        sandy_user.is_superuser = True
        sandy_user.is_staff = True
        sandy_user.is_active = True
        sandy_user.first_name = 'ABCD'
        sandy_user.last_name = 'Coaching & Library'
        sandy_user.password = make_password(sandy_pass)
        sandy_user.save()
        print("[Migration 0115] Verified and updated Superuser Sandy.")

    # 7. Ensure TeacherProfiles for Sandy & Vaku
    try:
        TeacherProfile = apps.get_model('users', 'TeacherProfile')
        sandy_tp, _ = TeacherProfile.objects.get_or_create(user=sandy_user)
        sandy_tp.display_name = 'Sandeep Sir'
        sandy_tp.role_title = 'Teacher'
        sandy_tp.detail1 = 'Founder & Head Faculty'
        sandy_tp.detail2 = 'English Grammar & Spoken Teacher'
        sandy_tp.detail3 = 'Library Owner'
        sandy_tp.about = 'Sandeep Sir is known for his clear explanations, disciplined teaching style and friendly nature. Since 2013, hundreds of students from Basoda and nearby areas have improved their grammar, written English and confidence with his guidance.'
        sandy_tp.save()

        vaku_tp, _ = TeacherProfile.objects.get_or_create(user=vaku_user)
        vaku_tp.display_name = 'ABCD Asst.'
        vaku_tp.role_title = 'Vikas Dangi'
        vaku_tp.detail1 = 'Software Engg.'
        vaku_tp.detail2 = 'Tech Support / helpline of ABCD'
        vaku_tp.detail3 = 'Support Helpline'
        vaku_tp.about = 'Technical support and helpline assistant for ABCD. Contact for software, platform, or account issues.'
        vaku_tp.save()
        print("[Migration 0115] Teacher profiles verified for Sandy and Vaku.")
    except Exception as e:
        print(f"[Migration 0115] Teacher profile notice: {e}")

    print("[Migration 0115] Clean-slate launch reset completed successfully!\n")


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0114_todotask_todo_u_cat_tr_cr_idx_and_more'),
    ]

    operations = [
        migrations.RunPython(launch_clean_slate_reset, noop),
    ]
