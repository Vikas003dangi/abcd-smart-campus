# users/utils.py

import os
from django.utils import timezone
from datetime import timedelta

from django.conf import settings
from django.urls import reverse
from .models import Seat, Course, VisitorIntent, StudentProfile, SeatAssignment, TodoTask
from .youtube_service import fetch_playlists, fetch_playlist_videos
from django.core.cache import cache
from .email_service import send_html_email
from .notifications import create_notification

# -------------------------------------------------------------------
# FLEXIBLE DATETIME PARSING & SCHEDULED BROADCAST AUTOMATION

def parse_flexible_datetime(dt_str):
    """
    Flexibly parses any date/time string (ISO, 12h AM/PM, 24h, date-only, slash-separated, etc.)
    and returns a timezone-aware datetime object (or None if unparseable).
    """
    if not dt_str or not str(dt_str).strip():
        return None
    val = str(dt_str).strip()

    # 1. Try dateutil parser (handles almost all standard formats)
    tz = timezone.get_current_timezone()
    try:
        from dateutil.parser import parse as parse_dateutil
        parsed = parse_dateutil(val)
        if not timezone.is_aware(parsed):
            parsed = timezone.make_aware(parsed, timezone=tz)
        else:
            parsed = parsed.astimezone(tz)
        return parsed
    except Exception:
        pass

    # 2. Try Django parse_datetime & parse_date
    try:
        from django.utils.dateparse import parse_datetime, parse_date
        parsed = parse_datetime(val)
        if parsed:
            if not timezone.is_aware(parsed):
                parsed = timezone.make_aware(parsed)
            return parsed
        d = parse_date(val)
        if d:
            from datetime import datetime as _dt
            parsed = timezone.make_aware(_dt(d.year, d.month, d.day, 0, 0, 0))
            return parsed
    except Exception:
        pass

    # 3. Explicit strptime fallbacks
    from datetime import datetime as _datetime
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %I:%M %p",
        "%Y-%m-%d %I:%M%p",
        "%Y-%m-%d %I:%M:%S %p",
        "%Y-%m-%d %I:%M:%S%p",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M",
        "%d-%m-%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d-%m-%Y %I:%M %p",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %I:%M %p",
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
    ]
    for fmt in formats:
        try:
            parsed = _datetime.strptime(val, fmt)
            if not timezone.is_aware(parsed):
                parsed = timezone.make_aware(parsed)
            return parsed
        except (ValueError, TypeError):
            continue

    return None


def process_scheduled_broadcasts():
    """
    Auto-processes any due scheduled broadcasts and banners (status='scheduled' and send_at <= now).
    Dispatches notifications/emails/WhatsApp and updates status to 'sent'.
    """
    from .models import BroadcastMessage, Notification, StudentAchievement
    from django.contrib.auth.models import User
    from django.db.models import Q
    from django.conf import settings
    from .email_service import send_html_email

    now = timezone.now()
    due_broadcasts = BroadcastMessage.objects.filter(
        status="scheduled",
        send_at__lte=now,
        is_draft=False
    )
    for b in due_broadcasts:
        try:
            b.status = "sent"
            b.is_sent = True
            b.save(update_fields=["status", "is_sent"])

            recipient_qs = User.objects.none()
            target_group = b.target_group
            selected_floors = b.floor.split(",") if b.floor else []
            selected_batches = b.batch.split(",") if b.batch else []

            if target_group == "everyone":
                recipient_qs = User.objects.filter(Q(profile__isnull=False) | Q(achievements__isnull=False))
            elif target_group == "all_students":
                recipient_qs = User.objects.filter(profile__isnull=False)
            elif target_group in ["library_students", "library"]:
                recipient_qs = User.objects.filter(profile__service_type="Library")
                if selected_floors:
                    recipient_qs = recipient_qs.filter(profile__seat__floor__in=selected_floors)
            elif target_group in ["coaching_students", "coaching"]:
                recipient_qs = User.objects.filter(profile__service_type="Coaching")
                if selected_batches:
                    recipient_qs = recipient_qs.filter(profile__batch__in=selected_batches)
            elif target_group == "alumni":
                recipient_qs = User.objects.filter(achievements__isnull=False)
            elif target_group in ["individual_selection", "individuals"]:
                if b.selected_ids:
                    recipient_qs = User.objects.filter(id__in=b.selected_ids)

            users = list(recipient_qs.filter(is_staff=False).distinct())

            site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")
            attachment_links = []
            for att in b.attachments.all():
                u = att.file.url
                full_url = u if u.startswith("http") else f"{site_url}{u}"
                attachment_links.append({
                    "name": os.path.basename(att.file.name),
                    "url": full_url
                })

            banner_img_url = None
            if b.banner_image:
                u = b.banner_image.url
                banner_img_url = u if u.startswith("http") else f"{site_url}{u}"
            elif attachment_links:
                for att in attachment_links:
                    u = att.get("url", "")
                    ext = os.path.splitext(u)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                        banner_img_url = u
                        break

            for user in users:
                Notification.objects.create(
                    user=user,
                    title=b.subject,
                    message=b.message,
                    category="general",
                    is_read=False
                )
                if b.send_email:
                    target_email = get_user_notification_email(user)
                    if target_email:
                        try:
                            send_html_email(
                                subject=b.subject,
                                to_email=target_email,
                                template="emails/broadcast_email.html",
                                context={
                                    "subject": b.subject,
                                    "message": b.message,
                                    "teacher_name": b.sender.get_full_name() or b.sender.username,
                                    "dashboard_url": f"{site_url}/student/dashboard/",
                                    "attachment_links": attachment_links,
                                    "banner_image_url": banner_img_url,
                                    "buttons": b.banner_buttons,
                                },
                                fail_silently=True,
                            )
                        except Exception:
                            pass

            if b.send_whatsapp:
                from .notifications import send_broadcast_whatsapp
                whatsapp_targets = []
                for user in users:
                    if hasattr(user, 'profile'):
                        whatsapp_targets.append(user.profile)
                    else:
                        ach = StudentAchievement.objects.filter(user=user).first()
                        if ach:
                            whatsapp_targets.append(ach)
                if whatsapp_targets:
                    send_broadcast_whatsapp(
                        whatsapp_targets,
                        b.subject,
                        b.message,
                        banner_image_url=banner_img_url,
                        attachments=attachment_links,
                        buttons=b.banner_buttons
                    )
        except Exception:
            pass


# -------------------------------------------------------------------
# YOUTUBE COURSE SYNCING

def sync_courses_from_youtube():
    channel_id = getattr(settings, "YOUTUBE_CHANNEL_ID", "")
    if not channel_id:
        raise RuntimeError("YOUTUBE_CHANNEL_ID is not configured in .env or environment variables.")

    playlists = fetch_playlists(channel_id)

    for pl in playlists:
        playlist_id = pl["id"]
        title = pl["snippet"]["title"]
        description = pl["snippet"].get("description", "")

        # 🎬 fetch videos to count
        videos = fetch_playlist_videos(playlist_id)
        video_count = len(videos)

        course, created = Course.objects.update_or_create(
            playlist_id=playlist_id,
            defaults={
                "title": title,
                "description": description,
                "video_count": video_count,
                "last_synced_at": timezone.now(),
            }
        )

        # Download thumbnail if course is new or has no thumbnail
        if not course.thumbnail:
            pl_thumbs = pl["snippet"].get("thumbnails", {})
            candidate_urls = [
                pl_thumbs.get("maxres", {}).get("url"),
                pl_thumbs.get("standard", {}).get("url"),
                pl_thumbs.get("high", {}).get("url"),
                pl_thumbs.get("medium", {}).get("url"),
                pl_thumbs.get("default", {}).get("url"),
            ]
            first_vid_id = None
            if videos:
                first_vid_id = videos[0].get("snippet", {}).get("resourceId", {}).get("videoId")
                if first_vid_id:
                    candidate_urls.extend([
                        f"https://img.youtube.com/vi/{first_vid_id}/maxresdefault.jpg",
                        f"https://img.youtube.com/vi/{first_vid_id}/hqdefault.jpg",
                        f"https://img.youtube.com/vi/{first_vid_id}/mqdefault.jpg",
                    ])

            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            for u in candidate_urls:
                if not u:
                    continue
                try:
                    import urllib.request
                    from django.core.files.base import ContentFile
                    req = urllib.request.Request(u, headers=headers)
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        if resp.status == 200:
                            data = resp.read()
                            if len(data) > 1000:
                                course.thumbnail.save(f"pl_{playlist_id}.jpg", ContentFile(data), save=True)
                                break
                except Exception:
                    continue

# -------------------------------------------------------------------
# YOUTUBE PLAYLIST VIDEO FETCHING WITH CACHING
def get_playlist_videos_for_course(playlist_id, cache_minutes=360):
    """
    Returns normalized video list for templates.
    Cached to avoid hitting YouTube API repeatedly.
    """
    cache_key = f"playlist_videos_{playlist_id}"
    cached = cache.get(cache_key)

    if cached:
        return cached

    items = fetch_playlist_videos(playlist_id)

    videos = []
    for item in items:
        snippet = item["snippet"]
        if snippet.get("resourceId"):
            # Robust thumbnail selection
            thumbs = snippet.get("thumbnails", {})
            best_thumb = thumbs.get("maxres", {}).get("url") or \
                         thumbs.get("high", {}).get("url") or \
                         thumbs.get("medium", {}).get("url") or \
                         thumbs.get("default", {}).get("url") or ""
            
            videos.append({
                "video_id": snippet["resourceId"]["videoId"],
                "title": snippet["title"],
                "thumbnail": best_thumb,
            })

    cache.set(cache_key, videos, cache_minutes * 60)
    return videos
def get_individual_videos_for_course(video_ids_str, cache_minutes=360):
    """
    Returns normalized video list for custom courses (comma-separated IDs).
    """
    if not video_ids_str:
        return []
        
    video_ids = [vid.strip() for vid in video_ids_str.split(",") if vid.strip()]
    if not video_ids:
        return []

    cache_key = f"custom_videos_{hash(video_ids_str)}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    # Fetch info for these specific IDs
    from .youtube_service import get_youtube_client
    yt = get_youtube_client()
    response = yt.videos().list(
        part="snippet",
        id=",".join(video_ids)
    ).execute()

    # Sort them back into the requested order
    items = response.get("items", [])
    videos = []
    for vid in video_ids:
        item = next((i for i in items if i["id"] == vid), None)
        if item:
            snippet = item["snippet"]
            # Robust thumbnail selection
            thumbs = snippet.get("thumbnails", {})
            best_thumb = thumbs.get("maxres", {}).get("url") or \
                         thumbs.get("high", {}).get("url") or \
                         thumbs.get("medium", {}).get("url") or \
                         thumbs.get("default", {}).get("url") or ""
                         
            videos.append({
                "video_id": item["id"],
                "title": snippet["title"],
                "thumbnail": best_thumb,
            })

    cache.set(cache_key, videos, cache_minutes * 60)
    return videos


# -------------------------------------------------------------------
# VISITOR INTENT TRACKING
# -------------------------------------------------------------------
def track_visitor_intent(user, intent_type, metadata=None):
    if not user.is_authenticated:
        return
    
    metadata = metadata or {}
    intent_scope = metadata.get("intent_scope", "general")

    # If user already has a student profile → IGNORE
    try:
        profile = StudentProfile.objects.get(user=user)
        if profile.status in ["admitted", "pending", "hold"]:
            return
    except StudentProfile.DoesNotExist:
        pass

    # Prevent duplicates (same intent + same scope)
    if VisitorIntent.objects.filter(
        user=user,
        intent_type=intent_type,
        intent_scope=intent_scope,
        reminder_sent=False,
        resolved=False
    ).exists():
        return

    VisitorIntent.objects.create(
        user=user,
        intent_type=intent_type,
        intent_scope=intent_scope,
        metadata=metadata
    )

# -------------------------------------------------------------------
# EMAIL NOTIFICATIONS   

def get_reminder_subject(intent):
    subjects = {
        "guest_browsed": "Start Your Journey with ABCD",
        "viewed_library": "Library Seats Are Available",
        "opened_admission": "Complete Your Admission at ABCD",
        "selected_coaching": "ABCD Coaching Is Waiting for You",
        "selected_library": "ABCD Library Seats Are Filling Fast",
        "selected_library_seat": "Your Preferred Library Seat Is Still Available",
    }
    return subjects.get(intent.intent_type, "ABCD Coaching & Library Update")


#  GENERAL VISITOR REMINDERS
# Delays before sending reminders

INTENT_DELAYS = {
    "guest_browsed": timedelta(hours=48),
    "viewed_library": timedelta(hours=24),
    "opened_admission": timedelta(hours=24),
    "selected_coaching": timedelta(hours=12),
    "selected_library": timedelta(hours=12),
}

def process_visitor_reminders():
    now = timezone.now()

    intents = VisitorIntent.objects.filter(
        reminder_sent=False,
        resolved=False,
        intent_scope="general"
    )

    for intent in intents:
        delay = INTENT_DELAYS.get(intent.intent_type)
        if not delay:
            continue

        if intent.created_at + delay <= now:
            subject = get_reminder_subject(intent)

            send_html_email(
                subject=subject,
                to_email=intent.user.email,
                template="emails/visitor_reminder.html",
                context={
                    "intent": intent,
                    "dashboard_url": settings.SITE_URL,
                    "action_url": f"{settings.SITE_URL}{reverse('users:admission_form')}",
                    "action_text": "Continue with ABCD",
                },
                fail_silently=True,
            )

            intent.mark_reminder_sent()

# -------------------------------------------------------------------
# SEAT AVAILABILITY REMINDERS

SEAT_REMINDER_DELAY = timedelta(days=3)

def process_seat_availability_reminders():
    now = timezone.now()

    # Seats that have been available long enough
    seats = Seat.objects.filter(
        status="available",
        available_since__isnull=False,
        available_since__lte=now - SEAT_REMINDER_DELAY
    )

    for seat in seats:
        intents = VisitorIntent.objects.filter(
            intent_type="selected_library_seat",
            intent_scope="specific",
            reminder_sent=False,
            resolved=False,
            metadata__seat_number=str(seat.seat_number),
            metadata__floor=seat.floor
        )

        for intent in intents:
            # Skip if user later became a student
            if hasattr(intent.user, 'studentprofile'):
                continue

            subject = "Your preferred library seat is now available"

            send_html_email(
                subject=subject,
                to_email=intent.user.email,
                template="emails/visitor_reminder.html",
                context={
                    "intent": intent,
                    "seat": seat,
                    "dashboard_url": settings.SITE_URL,
                    "action_url": f"{settings.SITE_URL}{reverse('users:admission_form')}",
                    "action_text": "Confirm Your Seat",
                },
                fail_silently=True,
            )

            intent.mark_reminder_sent()
# -------------------------------------------------------------------

# -------------------------------------------------------------------
# HOLD EXPIRY NOTIFICATIONS (NO AUTO SEAT CHANGE)
# -------------------------------------------------------------------

def process_expired_seat_holds():
    """
    Detect expired seat holds and notify:
    - Student who placed the hold
    - Teacher (staff)

    IMPORTANT:
    - Does NOT free seat
    - Does NOT modify SeatAssignment
    - Seat remains ON_HOLD until teacher decides
    """

    today = timezone.localtime(timezone.now()).date()

    expired_seats = Seat.objects.filter(
        status='on_hold',
        hold_end_date__isnull=False,
        hold_end_date__lt=today
    ).select_related('hold_student')

    for seat in expired_seats:
        student = seat.hold_student

        # -------------------------------
        # Notify Student
        # -------------------------------
        target_email = get_user_notification_email(student)
        if student and target_email:
            send_html_email(
                subject="Your Seat Hold Has Expired",
                to_email=target_email,
                template="emails/seat_hold_expired_student.html",
                context={
                    "student": student,
                    "seat": seat,
                    "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                },
                fail_silently=True,
            )

        # -------------------------------
        # Notify Teacher/Admin
        # -------------------------------
        send_html_email(
            subject="Seat Hold Expired – Action Required",
            to_email=settings.ADMIN_EMAIL,
            template="emails/seat_hold_expired_teacher.html",
            context={
                "seat": seat,
                "student": student,
                "dashboard_url": f"{settings.SITE_URL}{reverse('users:teacher_dashboard')}",
            },
            fail_silently=True,
        )
# -------------------------------------------------------------------

def process_seat_hold_lifecycle():
    """
    DAILY JOB (CRON / Celery):
    - Notify when 2 days remain
    - Detect expired holds
    - DO NOT auto-free seat
    """

    today = timezone.localtime(timezone.now()).date()
    two_days_from_now = today + timedelta(days=2)

    # --------------------------------------------
    # 1) HOLDS EXPIRING IN 2 DAYS (WARNING)
    # --------------------------------------------
    expiring_soon = Seat.objects.filter(
        status='on_hold',
        hold_end_date=two_days_from_now
    ).select_related('hold_student')

    for seat in expiring_soon:
        student = seat.hold_student

        # Student notification
        if student and student.user:
            create_notification(
                user=student.user,
                title="Seat Hold Expiring Soon",
                message=(
                    f"Your seat {seat.seat_number} will expire in 2 days. "
                    f"Please contact the library if you need an extension."
                ),
                category="seat"
            )

        # Teacher notification
        create_notification(
            user=None,
            title="Seat Hold Expiring in 2 Days",
            message=f"Seat {seat.seat_number} hold expires in 2 days.",
            category="seat"
        )

    # --------------------------------------------
    # 2) HOLDS THAT HAVE EXPIRED (T < TODAY)
    # --------------------------------------------
    expired_holds = Seat.objects.filter(
        status='on_hold',
        hold_end_date__lt=today
    ).select_related('hold_student')

    for seat in expired_holds:
        student = seat.hold_student

        # Notify student
        if student and student.user:
            create_notification(
                user=student.user,
                title="Seat Hold Expired",
                message=(
                    f"Your hold on seat {seat.seat_number} has expired. "
                    f"Please contact the teacher."
                ),
                category="seat"
            )

        # Notify teacher
        create_notification(
            user=None,
            title="Seat Hold Expired – Action Required",
            message=f"Seat {seat.seat_number} hold expired. Review required.",
            category="seat"
        )
# -------------------------------------------------------------------
def sync_active_holds():
    """
    Transitions approved future holds into active holds when the start date meets today.
    """
    from django.utils import timezone
    from dateutil.relativedelta import relativedelta
    from .models import SeatHoldRequest, SeatAssignment
    import re

    today = timezone.localtime(timezone.now()).date()
    approved_requests = SeatHoldRequest.objects.filter(status='approved')

    for req in approved_requests:
        start_date = req.start_date
        if start_date > today:
            continue

        duration_str = req.duration_text.lower()
        months = 0
        days = 0

        m = re.match(r'^(\d+)\s*month(s)?(?:\s+(\d+)\s*day(s)?)?$', duration_str)
        if m:
            months = int(m.group(1))
            if m.group(3):
                days = int(m.group(3))
        else:
            d = re.match(r'^(\d+)\s*day(s)?$', duration_str)
            if d:
                days = int(d.group(1))
            else:
                days = 15

        end_date = start_date + relativedelta(months=months, days=days)
        if end_date < today:
            continue

        seat = req.seat
        student = req.student

        # Activate hold on Seat
        seat.status = 'on_hold'
        seat.hold_status = 'active'
        seat.hold_student = student
        seat.hold_start_date = start_date
        seat.hold_end_date = end_date
        seat.save()

        # Activate hold on Assignment
        owner_assignment = SeatAssignment.objects.filter(
            seat=seat,
            student=student,
            is_active=True
        ).first()

        if owner_assignment:
            owner_assignment.hold_status = 'active'
            owner_assignment.hold_start_date = start_date
            owner_assignment.hold_end_date = end_date
            owner_assignment.save()

            # Sync student status
            student.status = 'on_hold'
            student.save(update_fields=['status'])

            # Recalculate fee expiry with hold extension
            from .views import _recalc_fee_expiry_with_hold
            _recalc_fee_expiry_with_hold(student)

# -------------------------------------------------------------------
def process_expired_holds():
    """
    4-Stage Seat Hold Lifecycle & Grace Period Processor:
    Stage 0: Auto-start holds whose hold_start_date arrives today.
    Stage 1: 1-Day Pre-Expiry Warning (today == hold_end_date - 1).
    Stage 2: Hold End Date & 3-Day Grace Period Start (today == hold_end_date).
             DO NOT RELEASE IMMEDIATELY. Dispatch urgent Email, WhatsApp, & In-App warnings with interactive action buttons.
    Stage 3: 3-Day Grace Expiration (today >= hold_end_date + 3).
             Release original student, and AUTOMATICALLY PROMOTE any temporary student on that seat/shift to permanent occupant.
    """
    from datetime import timedelta
    from django.contrib.auth import get_user_model
    User = get_user_model()
    staff_users = list(User.objects.filter(is_staff=True, is_active=True))
    teacher_phone = "9827662450"

    today = timezone.localtime(timezone.now()).date()
    now_dt = timezone.now()
    print(f"--- Running 4-Stage Hold Lifecycle Check for {today} ---")

    # =========================================================
    # STAGE 0: FUTURE HOLD AUTO-ACTIVATION (today >= hold_start_date)
    # =========================================================
    pending_start_assignments = SeatAssignment.objects.filter(
        is_active=True,
        hold_status='pending',
        hold_start_date__lte=today
    ).select_related('seat', 'student')

    for assign in pending_start_assignments:
        assign.hold_status = 'active'
        assign.save(update_fields=['hold_status'])
        assign.student.status = 'on_hold'
        assign.student.save(update_fields=['status'])
        
        from .views import _recalc_fee_expiry_with_hold
        _recalc_fee_expiry_with_hold(assign.student)

        create_notification(
            user=assign.student.user,
            title="Seat Hold Active Today",
            message=f"Your hold on Seat {assign.seat.seat_number} ({assign.shift_type}) has started today.",
            category="seat"
        )
        print(f" > Auto-activated hold for {assign.student.full_name} on Seat {assign.seat.seat_number}")

    # =========================================================
    # STAGE 1: 1-DAY PRE-EXPIRY WARNING (today == hold_end_date - 1)
    # =========================================================
    pre_warning_assignments = SeatAssignment.objects.filter(
        is_active=True,
        hold_status='active',
        hold_end_date=today + timedelta(days=1)
    ).select_related('seat', 'student')

    for assign in pre_warning_assignments:
        cooldown_key = f"hold_pre_warn_{assign.id}_{today}"
        recent_notif = Notification.objects.filter(
            user=assign.student.user,
            category="seat",
            created_at__date=today,
            meta__cooldown_key=cooldown_key
        ).exists()

        if not recent_notif:
            seat_desc = f"{assign.seat.floor} Seat {assign.seat.seat_number} ({assign.shift_type})"
            create_notification(
                user=assign.student.user,
                title="Seat Hold Expires Tomorrow",
                message=f"Your seat hold on {seat_desc} expires tomorrow ({assign.hold_end_date.strftime('%d %b %Y')}). Please contact your teacher if you need an extension.",
                category="seat",
                meta={"cooldown_key": cooldown_key}
            )
            print(f" > Sent 1-day pre-expiry warning to {assign.student.full_name}")

    # =========================================================
    # STAGE 2: HOLD END DATE & 3-DAY GRACE START (today == hold_end_date)
    # =========================================================
    grace_start_assignments = SeatAssignment.objects.filter(
        is_active=True,
        hold_status='active',
        hold_end_date=today
    ).select_related('seat', 'student')

    from .notifications import send_hold_warning_whatsapp_student, send_hold_warning_whatsapp_teacher
    from .email_service import send_html_email

    for assign in grace_start_assignments:
        student = assign.student
        seat = assign.seat
        seat_desc = f"{seat.floor} Seat {seat.seat_number} ({assign.shift_type})"
        cooldown_key = f"hold_grace_start_{assign.id}_{today}"

        already_sent = Notification.objects.filter(
            user=student.user,
            category="seat",
            created_at__date=today,
            meta__cooldown_key=cooldown_key
        ).exists()

        if not already_sent:
            # 1. Student In-App Notification with CTA Meta Buttons
            create_notification(
                user=student.user,
                title="⚠️ URGENT: 3-Day Seat Hold Grace Period",
                message=f"Your hold on {seat_desc} ended today ({today.strftime('%d %b %Y')}). You have 3 days to contact your teacher! Otherwise, your seat will be automatically freed and lost.",
                link=f"{settings.SITE_URL}{reverse('users:your_seat_status')}",
                category="seat",
                meta={
                    "cooldown_key": cooldown_key,
                    "actions": [
                        {"label": "📞 Call Teacher", "url": f"tel:{teacher_phone}", "type": "call"},
                        {"label": "💬 Message WhatsApp", "url": f"https://wa.me/91{teacher_phone}?text=Hello%20Teacher,%20regarding%20my%20seat%20hold%20on%20{seat_desc}", "type": "whatsapp"},
                        {"label": "🛑 End Hold", "url": f"{settings.SITE_URL}{reverse('users:your_seat_status')}", "type": "end_hold"}
                    ]
                }
            )

            # 2. Student Email with Interactive CTA Buttons
            student_email = get_user_notification_email(student)
            if student_email:
                try:
                    send_html_email(
                        subject="URGENT: Your Seat Hold Ends Today - 3 Days Grace Period",
                        to_email=student_email,
                        template="emails/hold_grace_warning.html",
                        context={
                            "title": "Seat Hold Ending & 3-Day Grace Period",
                            "student": student,
                            "seat_details": seat_desc,
                            "hold_end_date": today.strftime('%d %b %Y'),
                            "teacher_phone": teacher_phone,
                            "dashboard_url": f"{settings.SITE_URL}{reverse('users:your_seat_status')}",
                        },
                        fail_silently=True
                    )
                except Exception as e:
                    print(f"Failed student grace warning email: {e}")

            # 3. Student WhatsApp Warning
            send_hold_warning_whatsapp_student(student, seat_desc, teacher_phone)

            # 4. Teacher Alerts (In-App + Email + WhatsApp)
            for staff in staff_users:
                create_notification(
                    user=staff,
                    title=f"Hold Expiry Grace Start: {student.full_name}",
                    message=f"Student {student.full_name}'s hold on {seat_desc} reached end date. 3-day grace period active.",
                    link=f"{settings.SITE_URL}{reverse('users:teacher_dashboard')}",
                    category="seat_teacher",
                    meta={
                        "actions": [
                            {"label": "🛑 Open Dashboard / End Hold", "url": f"{settings.SITE_URL}{reverse('users:teacher_dashboard')}"}
                        ]
                    }
                )
                if staff.email:
                    try:
                        send_html_email(
                            subject=f"Hold Notice: {student.full_name} Seat Hold Grace Period",
                            to_email=staff.email,
                            template="emails/hold_grace_teacher.html",
                            context={
                                "title": f"Hold Grace Start: {student.full_name}",
                                "student": student,
                                "seat_details": seat_desc,
                                "dashboard_url": f"{settings.SITE_URL}{reverse('users:teacher_dashboard')}",
                            },
                            fail_silently=True
                        )
                    except Exception as e:
                        print(f"Failed teacher grace email: {e}")

                send_hold_warning_whatsapp_teacher(staff, student.full_name, seat_desc)

            print(f" > Fired 3-day grace period warnings (Email, WA, In-App) for {student.full_name}")

    # =========================================================
    # STAGE 3: 3-DAY GRACE EXPIRATION & TEMP STUDENT AUTO-PROMOTION
    # (today >= hold_end_date + 3 days)
    # =========================================================
    grace_cutoff = today - timedelta(days=3)
    expired_grace_assignments = SeatAssignment.objects.filter(
        is_active=True,
        hold_status='active',
        hold_end_date__lte=grace_cutoff
    ).select_related('seat', 'student')

    for owner_assign in expired_grace_assignments:
        seat = owner_assign.seat
        shift = owner_assign.shift_type
        owner_student = owner_assign.student

        print(f" > 3-Day Grace Expired: Seat {seat.seat_number} ({shift}) - {owner_student.full_name}")

        # A. Release Original Student
        owner_assign.deactivate()
        owner_student.seat = None
        owner_student.status = 'pending'
        owner_student.save(update_fields=['seat', 'status'])

        create_notification(
            user=owner_student.user,
            title="Seat Hold Released",
            message=f"Your 3-day hold grace period on Seat {seat.seat_number} ({shift}) has expired. Your seat has been freed.",
            category="seat"
        )

        # B. AUTOMATIC TEMPORARY STUDENT PROMOTION
        # Look for temporary tenant / assignment on this seat & shift
        temp_tenant = SeatAssignment.objects.filter(
            seat=seat,
            shift_type=shift,
            is_active=True,
            is_partial=True
        ).first()

        if temp_tenant:
            tenant_student = temp_tenant.student
            print(f"   - AUTO-PROMOTING Temporary Tenant to Permanent Occupant: {tenant_student.full_name}")

            # Promote temporary tenant to permanent
            temp_tenant.is_partial = False
            temp_tenant.allow_hold_override = False
            temp_tenant.save(update_fields=['is_partial', 'allow_hold_override'])

            tenant_student.seat = seat
            tenant_student.shift = shift
            tenant_student.status = 'admitted'
            tenant_student.save(update_fields=['seat', 'shift', 'status'])

            create_notification(
                user=tenant_student.user,
                title="🎉 Permanent Seat Allotted!",
                message=f"The hold on Seat {seat.seat_number} ({shift}) has ended! You have been automatically promoted from temporary allotment to permanent occupant of this seat.",
                link=f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                category="seat"
            )
        else:
            # Check for pending special requests
            special_req = SeatSpecialRequest.objects.filter(
                seat=seat,
                requested_shift=shift,
                status='pending',
                is_temporary=True
            ).first()

            if special_req:
                req_student = special_req.student
                print(f"   - AUTO-PROMOTING Pending Special Request Student: {req_student.full_name}")
                special_req.status = 'approved'
                special_req.save(update_fields=['status'])

                # Create permanent assignment
                SeatAssignment.objects.create(
                    student=req_student,
                    seat=seat,
                    shift_type=shift,
                    is_active=True,
                    is_partial=False
                )

                req_student.seat = seat
                req_student.shift = shift
                req_student.status = 'admitted'
                req_student.save(update_fields=['seat', 'shift', 'status'])

                create_notification(
                    user=req_student.user,
                    title="🎉 Permanent Seat Allotted!",
                    message=f"Your temporary request for Seat {seat.seat_number} ({shift}) has been automatically approved as permanent allotment!",
                    link=f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                    category="seat"
                )
            else:
                # No temporary occupant, recalculate seat availability
                seat.recalc_status()

    print("--- 4-Stage Hold Expiration Check Complete ---")



# ─────────────────────────────────────────────────────────────────────────────────
# TO-DO HUB — Isolated Notification Engine
# ─────────────────────────────────────────────────────────────────────────────────


def _fire_reminder(task, title, email_notify):
    """Module-level helper: fires a 'reminder' category notification and,
    when email_notify is True, sends a typed HTML email to the task owner."""
    create_notification(
        user=task.user,
        title=f"⏰ Reminder: {title}",
        message=f"Your reminder '{title}' is due now.",
        link='/todo/',
        category='reminder'
    )
    if email_notify and task.user:
        target_email = get_user_notification_email(task.user)
        if target_email:
            send_html_email(
                subject=f"Reminder: {title}",
                to_email=target_email,
            template="emails/todo_reminder.html",
            context={
                "title": title,
                "note": task.metadata.get('note', ''),
                "recurrence": task.metadata.get('recurrence', 'once'),
                "todo_url": f"{settings.SITE_URL}/todo/",
            },
            fail_silently=True
        )


def process_todo_notifications():
    """
    Background job to process TodoTask triggers.
    Logic:
    - Initial: 1 hour after creation.
    - Recurring (Auto-Delete OFF): Daily at original save time.
    - Recurring (Auto-Delete ON):
        * If duration < 48hrs: Notify 1 hour before expiry.
        * If duration > 48hrs: Notify daily at original save time.
    """
    from .models import TodoTask, Notification
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.localtime(timezone.now())
    tasks = TodoTask.objects.filter(is_done=False, is_trash=False)

    for task in tasks:
        created_at = timezone.localtime(task.created_at) if task.created_at else now

        # Handle REMINDER category
        if task.category == 'REMINDER':
            meta = task.metadata if isinstance(task.metadata, dict) else {}

            # ── Read all meta fields ──────────────────────────────────
            title          = meta.get('title', 'Reminder')
            recurrence     = meta.get('recurrence', 'once')
            email_notify   = meta.get('email_notify', False)
            time_str       = meta.get('time_str', '00:00')
            until_date_str = meta.get('until_date', None)

            # ── until_date: mark done when recurring task has expired ──
            if until_date_str:
                try:
                    from django.utils.dateparse import parse_date
                    until_d = parse_date(str(until_date_str))
                    if until_d and now.date() > until_d:
                        task.is_done = True
                        task.save(update_fields=['is_done'])
                        continue
                except Exception:
                    pass

            # ── Inline helper: build today's target datetime ──────────
            def _get_target_time(now_local, time_str):
                try:
                    hrs, mins = map(int, time_str.split(':'))
                    return now_local.replace(hour=hrs, minute=mins, second=0, microsecond=0)
                except Exception:
                    return now_local.replace(hour=0, minute=0, second=0, microsecond=0)

            # ── Dedup helper: has this task already fired today? ───────
            def _fired_today(task, now_local):
                return (
                    task.last_notified_at is not None
                    and timezone.localtime(task.last_notified_at).date() >= now_local.date()
                )

            # ── Recurrence dispatch ───────────────────────────────────
            if recurrence == 'once':
                if not task.initial_notified and task.delete_at and now >= task.delete_at:
                    _fire_reminder(task, title, email_notify)
                    task.is_done = True
                    task.initial_notified = True
                    task.save(update_fields=['is_done', 'initial_notified'])

            elif recurrence == 'daily':
                target = _get_target_time(now, time_str)
                if now >= target and not _fired_today(task, now):
                    _fire_reminder(task, title, email_notify)
                    task.last_notified_at = now
                    task.save(update_fields=['last_notified_at'])

            elif recurrence == 'weekly':
                days_of_week = meta.get('days_of_week', [])
                if now.weekday() in days_of_week:
                    target = _get_target_time(now, time_str)
                    if now >= target and not _fired_today(task, now):
                        _fire_reminder(task, title, email_notify)
                        task.last_notified_at = now
                        task.save(update_fields=['last_notified_at'])

            elif recurrence == 'monthly':
                day_of_month = meta.get('day_of_month', 1)
                if now.day == day_of_month:
                    target = _get_target_time(now, time_str)
                    if now >= target and not _fired_today(task, now):
                        _fire_reminder(task, title, email_notify)
                        task.last_notified_at = now
                        task.save(update_fields=['last_notified_at'])

            elif recurrence == 'every_n_days':
                interval_days = meta.get('interval_days', 1)
                baseline = task.last_notified_at if task.last_notified_at else task.created_at
                days_since = (now - baseline).days
                if days_since >= interval_days:
                    target = _get_target_time(now, time_str)
                    if now >= target and not _fired_today(task, now):
                        _fire_reminder(task, title, email_notify)
                        task.last_notified_at = now
                        task.save(update_fields=['last_notified_at'])

            continue

        
        # Handle Auto-Deletion/Trashing
        if task.auto_delete and task.delete_at and now >= task.delete_at:
            task.is_trash = True
            task.trashed_at = now
            task.save(update_fields=['is_trash', 'trashed_at'])
            send_todo_notification(task, f"To-Do Hub: '{task.get_category_display()}' task has expired and moved to Trash.")
            continue

        # 1. Initial Notification (Exactly 1 hour after saving)
        if not task.initial_notified:
            if now >= created_at + timedelta(hours=1):
                send_todo_notification(task, "To-Do Hub: You created a new scratchpad task an hour ago.")
                task.initial_notified = True
                task.last_notified_at = now
                task.save(update_fields=['initial_notified', 'last_notified_at'])
                continue

        # 2. Recurring Reminders
        if not task.auto_delete:
            # Recurring (Auto-Delete OFF): Daily at the original creation clock time
            last_notif = task.last_notified_at or (created_at + timedelta(hours=1))
            if now >= last_notif + timedelta(days=1):
                send_todo_notification(task, f"Daily Reminder: {task.get_category_display()} task is still pending.")
                task.last_notified_at = now
                task.save(update_fields=['last_notified_at'])
        else:
            # Recurring (Auto-Delete ON)
            if not task.delete_at:
                continue
                
            duration = task.delete_at - created_at
            
            if duration < timedelta(days=2):
                # If duration < 48 hours: Notify 1 hour before trashing
                if now >= task.delete_at - timedelta(hours=1):
                    if not task.last_notified_at or task.last_notified_at < task.delete_at - timedelta(hours=1.1):
                        send_todo_notification(task, f"Urgent: {task.get_category_display()} task will move to Trash in 1 hour.")
                        task.last_notified_at = now
                        task.save(update_fields=['last_notified_at'])
            else:
                # If duration >= 48 hours: Notify daily at original creation clock time
                last_notif = task.last_notified_at or (created_at + timedelta(hours=1))
                if now >= last_notif + timedelta(days=1):
                    send_todo_notification(task, f"Daily Reminder: {task.get_category_display()} task (Moving to Trash soon).")
                    task.last_notified_at = now
                    task.save(update_fields=['last_notified_at'])

def purge_todo_trash():
    """
    Permanently deletes TodoTasks that have been in the trash for more than 15 days.
    """
    cutoff = timezone.now() - timedelta(days=15)
    purged_count = TodoTask.objects.filter(is_trash=True, trashed_at__lt=cutoff).delete()[0]
    return purged_count



def send_todo_notification(task, message):
    """Isolated notification sender using 'general' category."""
    from .models import Notification
    Notification.objects.create(
        user=task.user,
        title="To-Do Hub Alert",
        message=message,
        link='/todo/',
        category='general'
    )


def process_offline_learning_reminders():
    """
    Background worker to process LearningReminder records for offline users.
    Dispatches In-App notifications and HTML emails for due study reminders.
    """
    from .models import LearningReminder
    from .email_service import send_html_email
    from django.db.models import Q
    from datetime import datetime

    now = timezone.now()
    now_local = timezone.localtime(now)
    today_date = now_local.date()
    current_time = now_local.time()
    current_weekday = str(now_local.weekday())

    # 1. Once-off reminders
    due_once = LearningReminder.objects.filter(
        recurrence_type='once',
        reminder_time__lte=now,
        is_sent=False
    ).select_related('user', 'course')

    for r in due_once:
        r.is_sent = True
        r.last_sent_at = now
        r.save(update_fields=['is_sent', 'last_sent_at'])
        
        create_notification(
            user=r.user,
            title="Study Reminder",
            message=f"Time to study {r.course.title}!",
            link=f"{settings.SITE_URL}/courses/{r.course.id}/",
            category="general"
        )
        target_email = get_user_notification_email(r.user)
        if target_email:
            try:
                send_html_email(
                    subject=f"Study Reminder: {r.course.title}",
                    to_email=target_email,
                    template="emails/learning_reminder_email.html",
                    context={
                        "user": r.user,
                        "title": r.title,
                        "course": r.course,
                        "course_url": f"{settings.SITE_URL}/courses/{r.course.id}/"
                    },
                    fail_silently=True
                )
            except Exception as e:
                print(f"Learning reminder email failed: {e}")

    # 2. Recurring reminders
    recurring = LearningReminder.objects.exclude(recurrence_type='once').filter(
        reminder_time_daily__lte=current_time
    ).filter(
        Q(last_sent_at__isnull=True) | Q(last_sent_at__lt=timezone.make_aware(datetime.combine(today_date, datetime.min.time())))
    ).select_related('user', 'course')

    for r in recurring:
        should_send = False
        if r.recurrence_type == 'daily':
            should_send = True
        elif r.recurrence_type == 'weekly':
            if current_weekday in ['5', '6']:
                should_send = True
        elif r.recurrence_type == 'custom':
            if r.days_of_week and current_weekday in r.days_of_week.split(','):
                should_send = True

        if should_send:
            r.last_sent_at = now
            r.save(update_fields=['last_sent_at'])
            
            create_notification(
                user=r.user,
                title="Daily Study Reminder",
                message=f"Time for your scheduled study session on {r.course.title}!",
                link=f"{settings.SITE_URL}/courses/{r.course.id}/",
                category="general"
            )
            target_email = get_user_notification_email(r.user)
            if target_email:
                try:
                    send_html_email(
                        subject=f"Scheduled Study Reminder: {r.course.title}",
                        to_email=target_email,
                        template="emails/learning_reminder_email.html",
                        context={
                            "user": r.user,
                            "title": r.title,
                            "course": r.course,
                            "course_url": f"{settings.SITE_URL}/courses/{r.course.id}/"
                        },
                        fail_silently=True
                    )
                except Exception as e:
                    print(f"Recurring learning reminder email failed: {e}")


def process_birthday_wishes():
    """
    Daily background processor: Checks for students/alumni whose DOB matches today.
    Dispatches In-App notifications and celebratory HTML Emails.
    """
    from .models import StudentProfile, Notification
    from .email_service import send_html_email

    today = timezone.localtime(timezone.now()).date()
    print(f"--- Running Daily Birthday Wish Check for {today} ---")

    birthday_students = StudentProfile.objects.filter(
        dob__month=today.month,
        dob__day=today.day
    ).select_related('user')

    sent_count = 0
    for student in birthday_students:
        cooldown_key = f"birthday_{student.id}_{today.year}"
        already_sent = Notification.objects.filter(
            user=student.user,
            category="general",
            created_at__date=today,
            meta__cooldown_key=cooldown_key
        ).exists()

        if not already_sent:
            create_notification(
                user=student.user,
                title=f"🎂 Happy Birthday, {student.full_name}! 🎉",
                message=f"Team ABCD wishes you a very Happy Birthday! May your day be filled with joy and your year with grand success! 🎈🎁",
                link=f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                category="general",
                meta={"cooldown_key": cooldown_key}
            )

            student_email = get_user_notification_email(student)
            if student_email:
                try:
                    send_html_email(
                        subject=f"🎂 Happy Birthday from Team ABCD, {student.full_name}! 🎉",
                        to_email=student_email,
                        template="emails/birthday_wish_email.html",
                        context={
                            "student": student,
                            "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}"
                        },
                        fail_silently=True
                    )
                except Exception as e:
                    print(f"Birthday email failed for {student.full_name}: {e}")

            sent_count += 1
            print(f" > Sent Birthday Wish to {student.full_name}")

    print(f"--- Birthday Check Complete. Sent {sent_count} wishes. ---")
    return sent_count




def get_user_dashboard_type(user):
    """
    Returns 'teacher', 'student', 'alumni', or None/guest.
    - teacher:  is_staff or is_superuser
    - student:  has StudentProfile
    - alumni:   has StudentAchievement
    - guest:    no dashboard
    If the user has both profiles, the "first profile" is determined by their
    approval status, falling back to the creation timestamp.
    """
    if not user or not user.is_authenticated:
        return None
    # Teacher check
    if user.is_staff or user.is_superuser:
        return 'teacher'

    from .models import StudentProfile, StudentAchievement
    profile = StudentProfile.objects.filter(user=user).first()
    achievement = StudentAchievement.objects.filter(user=user).first()

    if profile and achievement:
        profile_approved = (profile.status == 'admitted')
        achievement_approved = (achievement.status == 'approved')

        if profile_approved and not achievement_approved:
            return 'student'
        elif achievement_approved and not profile_approved:
            return 'alumni'
        elif profile_approved and achievement_approved:
            # Both approved: compare approved_at timestamps, fallback to created_at
            p_app = profile.approved_at
            a_app = achievement.approved_at
            if p_app and a_app:
                if p_app < a_app:
                    return 'student'
                else:
                    return 'alumni'
            elif p_app:
                return 'student'
            elif a_app:
                return 'alumni'
            else:
                if profile.created_at < achievement.created_at:
                    return 'student'
                else:
                    return 'alumni'
        else:
            # Both pending: compare creation timestamps
            if profile.created_at < achievement.created_at:
                return 'student'
            else:
                return 'alumni'
    elif profile:
        return 'student'
    elif achievement:
        return 'alumni'
    return 'guest'


def get_profile_photo_url(user):
    """
    Centralized profile photo selector enforcing Priority Cascade:
    1. Uploaded photo in DB (StudentProfile/StudentAchievement) with cache-buster.
    2. Google OAuth picture.
    3. Default UI-Avatar.
    """
    if not user or not user.is_authenticated:
        return "/static/data/user.png"

    # Priority 0: Teacher Photo overrides
    from .models import TeacherProfile
    teacher_prof = TeacherProfile.objects.filter(user=user).first()
    if teacher_prof and teacher_prof.photo:
        try:
            return teacher_prof.photo.url
        except Exception:
            pass

    email_clean = (user.email or '').strip().lower()
    username_clean = (user.username or '').strip().lower()
    if email_clean == 'abcd2013baq@gmail.com' or username_clean in ['sandy', 'sandeep', 'sandeepananda', 'abcd2013baq']:
        return "/static/data/sandeep sir photo.jpeg"
    elif email_clean == 'vd19055@gmail.com' or username_clean in ['vaku', 'vikas', 'vd19055']:
        return "/static/data/favicon/web-app-manifest-512x512.png"

    # Priority 1: StudentProfile Photo / StudentAchievement Photo
    from .models import StudentProfile, StudentAchievement
    profile = StudentProfile.objects.filter(user=user).first()
    if profile and profile.photo:
        try:
            p_url = profile.photo.url
            if p_url:
                return p_url
        except Exception:
            pass

    achievement = StudentAchievement.objects.filter(user=user).first()
    if achievement and achievement.photo:
        try:
            a_url = achievement.photo.url
            if a_url:
                return a_url
        except Exception:
            pass

    # Priority 2: Google OAuth picture
    try:
        from social_django.models import UserSocialAuth
        social_user = UserSocialAuth.objects.filter(user=user, provider='google-oauth2').first()
        if social_user:
            pic_url = social_user.extra_data.get('picture') or social_user.extra_data.get('image')
            if pic_url:
                return pic_url
    except Exception:
        pass

    # Priority 3: Default UI-Avatar
    import urllib.parse
    name = user.get_full_name() or user.username
    encoded_name = urllib.parse.quote_plus(name)
    return f"https://ui-avatars.com/api/?name={encoded_name}&background=random"


def get_user_display_name(user):
    """
    Resolves the display name for any user:
    1. Hardcoded priority emails (Sandeep Sir, ABCD Asst.)
    2. Teacher: check TeacherProfile or defaults
    3. Alumni: check StudentAchievement (approved)
    4. Student: check StudentProfile (admitted)
    5. Guest fallback: user.get_full_name() or username
    """
    if not user:
        return ""
    
    email_clean = (user.email or '').strip().lower()
    # 1. Teacher check
    from .models import TeacherProfile
    t_prof = TeacherProfile.objects.filter(user=user).first()
    if t_prof and t_prof.display_name and t_prof.display_name.strip():
        return t_prof.display_name.strip()
    if user.is_staff or user.is_superuser:
        if email_clean == 'abcd2013baq@gmail.com':
            return 'Sandeep Sir'
        elif email_clean == 'vd19055@gmail.com':
            return 'ABCD Asst.'
        return user.get_full_name() or user.username
        
    # 2. Alumni check
    from .models import StudentAchievement
    ach = StudentAchievement.objects.filter(user=user, status='approved').first()
    if ach:
        return ach.full_name
        
    # 3. Student check
    from .models import StudentProfile
    sp = StudentProfile.objects.filter(user=user, status='admitted').first()
    if sp:
        return sp.full_name
        
    # 4. Guest / Fallback
    return user.get_full_name() or user.username


def get_user_notification_email(user_or_student):
    """
    Get the email address where service notifications should be sent:
    1. If student profile / achievement has custom email (profile.email or student.email), use it.
    2. If alumni profile / achievement has custom email, use it.
    3. Fall back to user.email.
    """
    if not user_or_student:
        return None

    from .models import StudentProfile, StudentAchievement

    # If StudentProfile or StudentAchievement passed directly
    if isinstance(user_or_student, (StudentProfile, StudentAchievement)):
        direct_email = (getattr(user_or_student, 'email', None) or '').strip()
        if direct_email:
            return direct_email
        user = getattr(user_or_student, 'user', None)
        if user and user.email:
            return user.email.strip()
        return None

    # If a User instance was passed
    user = getattr(user_or_student, 'user', None)
    if not user and hasattr(user_or_student, 'username'):
        user = user_or_student

    if user:
        # 1. Prioritize attached StudentProfile email if present
        prof = StudentProfile.objects.filter(user=user).exclude(email='').first()
        if prof and prof.email and prof.email.strip():
            return prof.email.strip()

        # 2. Check attached StudentAchievement email
        ach = StudentAchievement.objects.filter(user=user).exclude(email='').first()
        if ach and ach.email and ach.email.strip():
            return ach.email.strip()

        # 3. Fall back to user account email
        user_email = (getattr(user, 'email', None) or '').strip()
        if user_email:
            return user_email

    direct_email = (getattr(user_or_student, 'email', None) or '').strip()
    return direct_email or None



