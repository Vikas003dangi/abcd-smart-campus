# users/views.py
import requests, os, re, datetime, json, random, threading, time
from django.db.models import F, Q, Avg, Count
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.views.decorators.http import require_POST, require_http_methods
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.forms import SetPasswordForm
from django.views.decorators.cache import never_cache
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden, FileResponse, Http404
from django.urls import reverse
from django.conf import settings
from .models import TodoTask, StudentAchievement, PushSubscription, Seat, SeatSpecialRequest, SeatSwitchRequest, StudentProfile, Payment, Complaint, StudyMaterial, Course, CourseCategory, Notification, BroadcastMessage, VisitorIntent, SeatHoldRequest, CourseQuestion, CourseAnswer, CourseReview, CourseShare, StudentMaterialAccess, LearningReminder, FeeTransaction, StudentCourseInteraction, abcd_format_name
from .forms import StudentAchievementForm, EditStudentProfileForm, EditAlumniProfileForm, InitialRegisterForm, StudentProfileForm, ComplaintForm, ComplaintRatingForm
from collections import defaultdict
from django.contrib.auth.models import User
from django.urls import reverse
from django.core.cache import cache
from django.utils import timezone 
from django.utils.timezone import is_aware, make_aware, localtime
from django.utils.dateparse import parse_datetime, parse_date
from datetime import datetime, timedelta
from . import notifications
from .notifications import create_notification
from django.db import transaction, models, OperationalError
from dateutil.relativedelta import relativedelta
from .utils import parse_flexible_datetime, process_scheduled_broadcasts
from django.utils.timesince import timesince
from .utils import get_playlist_videos_for_course, sync_courses_from_youtube, track_visitor_intent, sync_active_holds, get_user_notification_email
from .youtube_service import fetch_playlists, fetch_playlist_videos, fetch_channel_videos
from users.email_service import send_html_email
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from users.models import SeatAssignment
from users.db_utils import safe_atomic_transaction, deduplicate_request, safe_db_operation, retry_on_db_lock
def _send_push_bg(user_target, title, body, url):
    from users.notifications import send_push
    from django.db import close_old_connections
    
    close_old_connections() # Clean state before starting
    try:
        send_push(user_target, title, body, url)
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"BG Push Error: {e}")
    finally:
        close_old_connections() # CRITICAL: Close DB connection so the server doesn't crash


def send_realtime_notification(user_id, notification_data):
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                f"user_{user_id}",
                {
                    "type": "send_notification",
                    "notification": notification_data,
                }
            )
    except Exception:
        pass


def send_realtime_broadcast(broadcast_data):
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                "broadcast_all",
                {
                    "type": "send_broadcast",
                    "broadcast": broadcast_data,
                }
            )
    except Exception:
        pass

# -------------------------------------------------------------------


def is_teacher(user):
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def get_available_seats_count():
    from .models import Seat
    seats = Seat.objects.prefetch_related('assignments')
    today = timezone.now().date()
    available_count = 0
    
    for seat in seats:
        # Enforce shift definition
        is_shift = (seat.floor == 'Ground Floor' and seat.seat_number.isdigit() and 40 <= int(seat.seat_number) <= 53)
        
        active_assignments = [a for a in seat.assignments.all() if a.is_active]
        shifts = {a.shift_type for a in active_assignments}
        
        # Check hold
        morning_hold = False
        evening_hold = False
        full_day_hold = False
        for a in active_assignments:
            if a.hold_status == 'active':
                if a.shift_type == 'morning':
                    morning_hold = True
                elif a.shift_type == 'evening':
                    evening_hold = True
                elif a.shift_type == 'full':
                    full_day_hold = True
        
        if full_day_hold:
            morning_hold = True
            evening_hold = True

        # Check temporary allotments
        morning_temp_allotted = False
        evening_temp_allotted = False
        for a in active_assignments:
            if a.is_partial:
                if a.shift_type == 'morning':
                    morning_temp_allotted = True
                elif a.shift_type == 'evening':
                    evening_temp_allotted = True
                elif a.shift_type == 'full':
                    morning_temp_allotted = True
                    evening_temp_allotted = True

        # Determine visual_status
        visual_status = seat.status
        if visual_status == 'pending':
            visual_status = 'occupied'

        is_temporarily_occupied = (
            (not is_shift and (seat.status == 'on_hold' or full_day_hold) and morning_temp_allotted) or
            (is_shift and (morning_temp_allotted or evening_temp_allotted))
        )

        if is_temporarily_occupied:
            visual_status = 'partial'
        elif seat.status == 'on_hold' or full_day_hold or morning_hold or evening_hold:
            visual_status = 'on_hold'
        elif 'full' in shifts or ('morning' in shifts and 'evening' in shifts):
            visual_status = 'occupied'
        elif is_shift and ('morning' in shifts or 'evening' in shifts):
            visual_status = 'partial'
        else:
            visual_status = 'available'

        if visual_status == 'available':
            available_count += 1
            
    return available_count


#  The home page view
def home_page_view(request):
    
    """
    Renders the main landing page of the site.
    """
    youtube_videos = get_latest_youtube_videos()
    preview_courses = get_accessible_courses(request.user)[:3]    
    
    # If user is already logged in, send them where they belong
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('users:teacher_dashboard')
        
        active_dash = request.session.get('active_dashboard')
        if active_dash == 'student':
            return redirect('users:student_dashboard')
        elif active_dash == 'alumni':
            return redirect('users:alumni_dashboard')

        profile = StudentProfile.objects.filter(user=request.user).first()
        achievement = StudentAchievement.objects.filter(user=request.user).first()

        # Priority 1: Real Student (Admitted or with form details)
        if profile and (profile.is_admitted or profile.dob):
            request.session['active_dashboard'] = 'student'
            return redirect('users:student_dashboard')
        
        # Priority 2: Alumni
        if achievement:
            request.session['active_dashboard'] = 'alumni'
            return redirect('users:alumni_dashboard')
        
        # Priority 3: Pending Student (if any)
        if profile:
            request.session['active_dashboard'] = 'student'
            return redirect('users:student_dashboard')

        return redirect('users:guest_page')
        
    _ach_pool = list(
        StudentAchievement.objects.filter(status='approved')
        .order_by('-id')[:50]
    )
    achievements = random.sample(_ach_pool, min(len(_ach_pool), 8))
    resolved_complaints_count = Complaint.objects.filter(status='resolved').count()
    
    return render(request, 'home_page.html', {
        "youtube_videos": youtube_videos,
        "preview_courses": preview_courses,
        "achievements": achievements,
        "res_count": resolved_complaints_count,
        "avail_seats_count": get_available_seats_count(),
        "courses_count": get_accessible_courses(request.user).count(),
    })


#  The About Us page view
def about_us_view(request):
    """
    Simple About Us page for SEO and information.
    """
    return render(request, 'users/about_us.html')


# The Services page view
def services_view(request):
    """Public Services page."""
    return render(request, 'users/services.html')


# The Contact page view
def contact_view(request):
    return render(request, 'users/contact.html')


# --- YOUTUBE VIDEOS FETCHER ---
def get_latest_youtube_videos(limit=6):
    channel_url = "https://www.youtube.com/@englishekkhoz8279"
    api_key = getattr(settings, 'YOUTUBE_API_KEY', '').strip()
    channel_id = getattr(settings, 'YOUTUBE_CHANNEL_ID', '').strip()

    fallback_videos = [
        {
            "video_id": "PESBR2XSGuE",
            "title": "Prepositions By, till, Until .. | English Ek Khoz",
            "thumbnail": "https://img.youtube.com/vi/PESBR2XSGuE/mqdefault.jpg",
        },
        {
            "video_id": "ajyB8JR0kfQ",
            "title": "Class Room Teaching & Spoken English Practice",
            "thumbnail": "https://img.youtube.com/vi/ajyB8JR0kfQ/mqdefault.jpg",
        },
        {
            "video_id": "dDHEd_EXiaI",
            "title": "English Learning & Grammar Mastery Part-2",
            "thumbnail": "https://img.youtube.com/vi/dDHEd_EXiaI/mqdefault.jpg",
        },
        {
            "video_id": "K0H13vImmOE",
            "title": "A Movie Scene Recreation & Fluency Practice",
            "thumbnail": "https://img.youtube.com/vi/K0H13vImmOE/mqdefault.jpg",
        },
        {
            "video_id": "P_BDvohvONM",
            "title": "English Grammar & Conversation Mastery Part-3",
            "thumbnail": "https://img.youtube.com/vi/P_BDvohvONM/mqdefault.jpg",
        },
        {
            "video_id": "hJtIK8J4gFg",
            "title": "A Discussion on Youth Potential & Guidance",
            "thumbnail": "https://img.youtube.com/vi/hJtIK8J4gFg/mqdefault.jpg",
        }
    ]

    cache_key = "latest_youtube_videos"
    try:
        videos = cache.get(cache_key)
        if videos and len(videos) > 0:
            return videos
    except Exception:
        videos = None

    try:
        url = "https://www.googleapis.com/youtube/v3/search"
        params = {
            "part": "snippet",
            "channelId": channel_id,
            "maxResults": limit,
            "order": "date",
            "type": "video",
            "key": api_key,
        }
        res = requests.get(url, params=params, timeout=4)
        if res.status_code == 200:
            data = res.json()
            fetched_videos = []
            for item in data.get("items", []):
                vid_id = item.get("id", {}).get("videoId")
                if vid_id:
                    fetched_videos.append({
                        "video_id": vid_id,
                        "title": item.get("snippet", {}).get("title", "English Ek Khoz Video"),
                        "thumbnail": item.get("snippet", {}).get("thumbnails", {}).get("medium", {}).get("url", f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg"),
                    })
            if fetched_videos:
                try:
                    cache.set(cache_key, fetched_videos, 15 * 60)
                except Exception:
                    pass
                return fetched_videos
        return fallback_videos[:limit]
    except Exception:
        return fallback_videos[:limit]

# -------------------------------------------------------------------
# ============================
# COURSE ACCESS HELPERS
# ============================
def get_accessible_courses(user, dashboard_type=None):
    """
    Returns the queryset of Course objects that the given user has access to.
    - Public courses: accessible to all (guests, pending students, admitted students, alumni).
    - Coaching / Library courses: accessible ONLY to admitted students (status == 'admitted').
      Pending students are treated as guest users for course access.
    - Alumni courses: accessible ONLY to approved alumni.
    """
    if user.is_authenticated and (user.is_staff or user.is_superuser):
        return Course.objects.all()

    base_qs = Course.objects.filter(is_active=True)
    q_filter = Q(target_public=True)

    if not user.is_authenticated:
        return base_qs.filter(q_filter).distinct()

    profile = getattr(user, 'profile', None) or StudentProfile.objects.filter(user=user).first()
    # ONLY admitted students get coaching/library courses:
    if profile and profile.status == 'admitted' and (dashboard_type is None or dashboard_type == 'student'):
        if profile.service_type == 'Coaching':
            if profile.batch:
                q_filter |= Q(target_coaching=True) & (Q(target_coaching_batches__icontains='all') | Q(target_coaching_batches__icontains=profile.batch))
            else:
                q_filter |= Q(target_coaching=True) & Q(target_coaching_batches__icontains='all')
        elif profile.service_type == 'Library':
            floor = profile.seat.floor if profile.seat else None
            if floor:
                q_filter |= Q(target_library=True) & (Q(target_library_floors__icontains='both') | Q(target_library_floors__icontains=floor))
            else:
                q_filter |= Q(target_library=True) & Q(target_library_floors__icontains='both')
        elif profile.service_type == 'Both':
            floor = profile.seat.floor if profile.seat else None
            lib_q = Q(target_library=True)
            if floor:
                lib_q = lib_q & (Q(target_library_floors__icontains='both') | Q(target_library_floors__icontains=floor))
            else:
                lib_q = lib_q & Q(target_library_floors__icontains='both')
                
            coach_q = Q(target_coaching=True)
            if profile.batch:
                coach_q = coach_q & (Q(target_coaching_batches__icontains='all') | Q(target_coaching_batches__icontains=profile.batch))
            else:
                coach_q = coach_q & Q(target_coaching_batches__icontains='all')
                
            q_filter |= lib_q | coach_q

    is_approved_alumni = StudentAchievement.objects.filter(user=user, status='approved').exists()
    if is_approved_alumni and (dashboard_type is None or dashboard_type == 'alumni'):
        q_filter |= Q(target_alumni=True)

    return base_qs.filter(q_filter).distinct()


def check_course_access(user, course, dashboard_type=None):
    """
    Returns True if the given user is allowed to access/view the given course, False otherwise.
    """
    if user.is_authenticated and (user.is_staff or user.is_superuser):
        return True

    if not course.is_active:
        return False

    # Public/Guest courses are accessible by everyone (including pending students and guests)
    if course.target_public:
        return True

    if course.target_private:
        return False

    if not user.is_authenticated:
        return False

    return get_accessible_courses(user, dashboard_type=dashboard_type).filter(id=course.id).exists()


# ============================
# COURSES LIST PAGE
# ============================
def courses_view(request):

    is_authenticated = request.user.is_authenticated
    is_staff = is_authenticated and request.user.is_staff

    student = None
    is_student = False
    is_admitted = False
    is_pending_student = False

    if is_authenticated:
        try:
            student = getattr(request.user, 'profile', None) or StudentProfile.objects.filter(user=request.user).first()
            if student:
                is_student = not is_staff
                is_admitted = student.status == "admitted"
                is_pending_student = student.status == "pending"
        except (StudentProfile.DoesNotExist, AttributeError, Exception):
            student = None

    is_alumni = StudentAchievement.objects.filter(user=request.user).exists() if is_authenticated else False
    is_approved_alumni = StudentAchievement.objects.filter(user=request.user, status='approved').exists() if is_authenticated else False
    is_pending_alumni = is_alumni and not is_approved_alumni

    # -------------------------------
    # COURSE QUERY (Filtered by Interaction)
    # -------------------------------
    active_tab = request.GET.get('tab', 'all')
    dashboard_type = request.session.get('active_dashboard', 'student')
    
    # We display all active courses in the catalog, tagging locked ones for pending/guest users
    courses = Course.objects.filter(is_active=True).exclude(target_private=True).annotate(
        avg_rating=Avg('reviews__rating'),
        total_reviews=Count('reviews')
    ).order_by("-created_at")

    accessible_course_ids = set(get_accessible_courses(request.user, dashboard_type=dashboard_type).values_list('id', flat=True))

    if student:
        # Fetch student interactions
        interactions = StudentCourseInteraction.objects.filter(student=student)
        fav_ids = set(interactions.filter(is_favorite=True).values_list('course_id', flat=True))
        archived_ids = set(interactions.filter(is_archived=True).values_list('course_id', flat=True))

        if active_tab == 'favorites':
            courses = courses.filter(id__in=fav_ids)
        elif active_tab == 'archived':
            courses = courses.filter(id__in=archived_ids)
        else:
            # 'all' tab should hide archived courses unless explicitly in 'archived' tab
            courses = courses.exclude(id__in=archived_ids)

        # Calculate progress and attach interaction & lock flags
        for course in courses:
            course.is_favorite = course.id in fav_ids
            course.is_archived = course.id in archived_ids
            course.has_access = course.id in accessible_course_ids
            course.is_locked = not course.has_access

            total_materials = StudyMaterial.objects.filter(course=course).count()
            if total_materials > 0:
                completed = StudentMaterialAccess.objects.filter(student=student, material__course=course).count()
                course.progress_percent = int((completed / total_materials) * 100)
            else:
                course.progress_percent = 0
    else:
        for course in courses:
            course.is_favorite = False
            course.is_archived = False
            course.has_access = course.id in accessible_course_ids
            course.is_locked = not course.has_access
            course.progress_percent = 0

    return render(request, "users/courses.html", {
        "courses": courses,
        "is_authenticated": is_authenticated,
        "is_student": is_student,
        "is_admitted": is_admitted,
        "is_pending_student": is_pending_student,
        "is_pending_alumni": is_pending_alumni,
        "active_tab": active_tab,
    })

# ============================
# COURSE DETAIL PAGE
# ============================
def course_detail_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)

    # -------------------------------
    # ACCESS FLAGS
    # -------------------------------
    is_authenticated = request.user.is_authenticated
    is_staff = is_authenticated and request.user.is_staff

    student = None
    is_student = False
    is_admitted = False
    is_pending_student = False

    if is_authenticated:
        try:
            student = getattr(request.user, 'profile', None) or StudentProfile.objects.filter(user=request.user).first()
            if student:
                is_student = not is_staff
                is_admitted = student.status == "admitted"
                is_pending_student = student.status == "pending"
        except (StudentProfile.DoesNotExist, AttributeError, Exception):
            student = None

    is_alumni = StudentAchievement.objects.filter(user=request.user).exists() if is_authenticated else False
    is_approved_alumni = StudentAchievement.objects.filter(user=request.user, status='approved').exists() if is_authenticated else False
    is_pending_alumni = is_alumni and not is_approved_alumni

    dashboard_type = request.session.get('active_dashboard', 'student')
    user_has_access = check_course_access(request.user, course, dashboard_type=dashboard_type)

    # is_locked is True ONLY if the user does NOT have permission/access to view this course
    is_locked = not user_has_access

    # -------------------------------
    # FETCH CURRICULUM (Unified)
    # -------------------------------
    curriculum = course.materials.all().order_by('id')
    first_video = curriculum.filter(material_type='video').first()

    # Q&A AND REVIEWS DATA
    # -------------------------------
    reviews = course.reviews.all().order_by('-created_at')
    # Rating Stats (5, 4, 3, 2, 1 stars)
    rating_stats = reviews.values('rating').annotate(count=Count('rating')).order_by('-rating')
    stats_dict = {i: 0 for i in range(1, 6)}
    for s in rating_stats:
        stats_dict[s['rating']] = s['count']
    
    total_reviews = reviews.count()
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0

    questions = course.questions.all().prefetch_related('answers', 'answers__user', 'student').order_by('-created_at')

    # -------------------------------
    # STUDENT PROGRESS & INTERACTION
    # -------------------------------
    completed_material_ids = []
    progress_percent = 0
    interaction = None
    if student:
        completed_material_ids = list(StudentMaterialAccess.objects.filter(student=student).values_list('material_id', flat=True))
        all_material_count = curriculum.count()
        if all_material_count > 0:
            progress_percent = int((len(completed_material_ids) / all_material_count) * 100)
        
        interaction, _ = StudentCourseInteraction.objects.get_or_create(student=student, course=course)

    reminders = []
    if is_authenticated:
        reminders = LearningReminder.objects.filter(user=request.user, course=course).order_by('reminder_time')

    context = {
        "course": course,
        "curriculum": curriculum,
        "first_video": first_video,
        "is_locked": is_locked,
        "is_authenticated": is_authenticated,
        "is_student": is_student,
        "is_admitted": is_admitted,
        "is_pending_student": is_pending_student,
        "is_pending_alumni": is_pending_alumni,
        "profile": student,
        "interaction": interaction,
        "reviews": reviews,
        "questions": questions,
        "rating_stats": stats_dict,
        "total_reviews": total_reviews,
        "avg_rating": round(avg_rating, 1),
        "completed_ids": completed_material_ids,
        "progress_percent": progress_percent,
        "reminders": reminders,
    }
    return render(request, "users/course_detail.html", context)

# --- INTERACTIVE ENDPOINTS ---

@login_required
@require_POST
def save_learning_reminder(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    try:
        data = json.loads(request.body)
        title = data.get('title', f"Study {course.title}")
        recurrence = data.get('recurrence', 'once')
        
        params = {
            'user': request.user,
            'course': course,
            'title': title,
            'recurrence_type': recurrence
        }

        if recurrence == 'once':
            reminder_time_str = data.get('reminder_time')
            if not reminder_time_str:
                return JsonResponse({'success': False, 'error': 'Reminder time is required'})
            
            dt = parse_datetime(reminder_time_str)
            if dt is None:
                try:
                    dt = datetime.fromisoformat(reminder_time_str)
                except Exception:
                    return JsonResponse({'success': False, 'error': 'Invalid reminder time format.'})

            if not is_aware(dt):
                dt = make_aware(dt)

            params['reminder_time'] = dt
            if params['reminder_time'] <= timezone.now():
                return JsonResponse({'success': False, 'error': 'Reminder time must be in the future.'})
        else:
            time_str = data.get('reminder_time_daily')
            if not time_str:
                return JsonResponse({'success': False, 'error': 'Daily time is required'})
            params['reminder_time_daily'] = time_str
            
            if recurrence == 'custom':
                days = data.get('days_of_week') # e.g. [0, 2, 4]
                if not days:
                    return JsonResponse({'success': False, 'error': 'At least one day must be selected'})
                params['days_of_week'] = ",".join(map(str, days))

        LearningReminder.objects.create(**params)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def delete_learning_reminder(request, reminder_id):
    """Deletes/cancels a LearningReminder."""
    reminder = get_object_or_404(LearningReminder, id=reminder_id, user=request.user)
    reminder.delete()
    return JsonResponse({'success': True})

@login_required
def get_due_reminders(request):
    """
    Fetches reminders that are due but haven't been sent yet.
    Handles once-off and recurring schedules.
    """
    now = timezone.now()
    now_local = timezone.localtime(now)
    today_date = now_local.date()
    current_time = now_local.time()
    current_weekday = str(now_local.weekday()) # 0=Mon, 6=Sun

    # 1. Once-off reminders
    due_once = LearningReminder.objects.filter(
        user=request.user, 
        recurrence_type='once',
        reminder_time__lte=now, 
        is_sent=False
    )

    # 2. Recurring reminders (daily, weekly, custom)
    # We check if it's time AND hasn't been sent today
    recurring = LearningReminder.objects.filter(
        user=request.user
    ).exclude(recurrence_type='once').filter(
        reminder_time_daily__lte=current_time
    ).filter(
        Q(last_sent_at__isnull=True) | Q(last_sent_at__lt=timezone.make_aware(datetime.combine(today_date, datetime.min.time()), timezone.get_current_timezone()))
    )

    data = []
    
    # Process Once-off
    for r in due_once:
        data.append({'id': r.id, 'title': r.title, 'message': f"Time to study {r.course.title}!", 'url': f"/courses/{r.course.id}/"})
        r.is_sent = True
        r.last_sent_at = now
        r.save()
        create_dashboard_notification(request.user, r)

    # Process Recurring
    for r in recurring:
        should_send = False
        if r.recurrence_type == 'daily':
            should_send = True
        elif r.recurrence_type == 'weekly':
            # Sat (5) or Sun (6)
            if current_weekday in ['5', '6']:
                should_send = True
        elif r.recurrence_type == 'custom':
            if current_weekday in r.days_of_week.split(','):
                should_send = True
        
        if should_send:
            data.append({'id': r.id, 'title': r.title, 'message': f"Daily Reminder: {r.course.title}!", 'url': f"/courses/{r.course.id}/"})
            r.last_sent_at = now
            r.save()
            create_dashboard_notification(request.user, r)
        
    return JsonResponse({'success': True, 'reminders': data})

def create_dashboard_notification(user, reminder):
    Notification.objects.create(
        user=user,
        title=reminder.title,
        message=f"Scheduled reminder for {reminder.course.title}",
        link=f"/courses/{reminder.course.id}/",
        category="course"
    )

@require_POST
def submit_course_review(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    rating = request.POST.get('rating')
    comment = request.POST.get('comment', '')

    if not rating:
        return JsonResponse({"success": False, "error": "Rating is required."})

    try:
        rating_val = int(rating)
        if not (1 <= rating_val <= 5):
            return JsonResponse({"success": False, "error": "Rating must be between 1 and 5."})
    except ValueError:
        return JsonResponse({"success": False, "error": "Invalid rating format."})

    if request.user.is_authenticated:
        try:
            student = request.user.profile
        except AttributeError:
            return JsonResponse({"success": False, "error": "Only students can leave reviews."})

        review, created = CourseReview.objects.update_or_create(
            course=course,
            student=student,
            defaults={'rating': rating_val, 'comment': comment, 'guest_name': None}
        )
    else:
        guest_name = request.POST.get('guest_name', '').strip() or 'Unknown'
        CourseReview.objects.create(
            course=course,
            student=None,
            rating=rating_val,
            comment=comment,
            guest_name=guest_name
        )

    messages.success(request, "Review submitted successfully.")
    return JsonResponse({"success": True})

@login_required
@require_POST
def toggle_course_interaction(request, course_id):
    """AJAX: Toggle Favorite or Archive status for a course."""
    try:
        student = getattr(request.user, 'profile', None) or StudentProfile.objects.filter(user=request.user).first()
        if not student:
            student, _ = StudentProfile.objects.get_or_create(
                user=request.user,
                defaults={
                    'full_name': request.user.get_full_name() or request.user.username,
                    'mobile_number': '0000000000',
                    'whatsapp_number': '0000000000',
                    'service_type': 'Coaching',
                    'status': 'admitted' if request.user.is_staff else 'pending'
                }
            )

        course = get_object_or_404(Course, id=course_id)
        interaction, created = StudentCourseInteraction.objects.get_or_create(student=student, course=course)
        
        body = json.loads(request.body)
        action = body.get('action') # 'favorite' or 'archive'
        
        if action == 'favorite':
            interaction.is_favorite = not interaction.is_favorite
        elif action == 'archive':
            interaction.is_archived = not interaction.is_archived
        else:
            return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)
            
        interaction.save()
        return JsonResponse({
            'success': True,
            'is_favorite': interaction.is_favorite,
            'is_archived': interaction.is_archived,
            'action': action,
            'course_id': course.id,
            'course_title': course.title
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_POST
def submit_course_question(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    try:
        student = request.user.profile
    except AttributeError:
        return JsonResponse({"success": False, "error": "Only students can ask questions."})

    text = request.POST.get('question')
    material_id = request.POST.get('material_id')
    
    if not text:
        return JsonResponse({"success": False, "error": "Question text is required."})

    material = None
    if material_id:
        material = StudyMaterial.objects.filter(id=material_id).first()

    CourseQuestion.objects.create(
        course=course, student=student, material=material, question=text
    )
    return JsonResponse({"success": True, "message": "Question posted!"})

@login_required
@require_POST
def submit_course_answer(request, question_id):
    try:
        question = get_object_or_404(CourseQuestion, id=question_id)
        text = request.POST.get('answer')
        parent_id = request.POST.get('parent_id')
        
        if not text:
            return JsonResponse({'success': False, 'error': 'No answer text provided'})
            
        is_teacher = request.user.is_staff or request.user.is_superuser
        
        parent = None
        if parent_id:
            parent = get_object_or_404(CourseAnswer, id=parent_id)
        
        CourseAnswer.objects.create(
            question=question,
            user=request.user,
            answer_text=text,
            is_teacher_answer=is_teacher,
            parent=parent
        )
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Server Error: {str(e)}'}, status=500)

@login_required
@require_POST
def delete_qa_item(request):
    """API to delete a question or answer."""
    try:
        data = json.loads(request.body)
        target_type = data.get('type') # 'question' or 'answer'
        target_id = data.get('id')
        
        if target_type == 'question':
            item = get_object_or_404(CourseQuestion, id=target_id)
            # Permission: Owner or Staff
            if request.user != item.student.user and not request.user.is_staff:
                return JsonResponse({"success": False, "error": "Permission denied"}, status=403)
        elif target_type == 'answer':
            item = get_object_or_404(CourseAnswer, id=target_id)
            # Permission: Owner or Staff
            if request.user != item.user and not request.user.is_staff:
                return JsonResponse({"success": False, "error": "Permission denied"}, status=403)
        else:
            return JsonResponse({"success": False, "error": "Invalid target type"}, status=400)
            
        item.delete()
        return JsonResponse({"success": True, "message": "Item deleted successfully"})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

@login_required
@require_POST
def upvote_qa_api(request):
    """API to toggle upvotes for questions or answers."""
    try:
        data = json.loads(request.body)
        target_type = data.get('type') # 'question' or 'answer'
        target_id = data.get('id')
        
        if target_type == 'question':
            target = get_object_or_404(CourseQuestion, id=target_id)
        elif target_type == 'answer':
            target = get_object_or_404(CourseAnswer, id=target_id)
        else:
            return JsonResponse({"success": False, "error": "Invalid target type"}, status=400)
            
        if request.user in target.upvotes.all():
            target.upvotes.remove(request.user)
            action = 'removed'
        else:
            target.upvotes.add(request.user)
            action = 'added'
            
        return JsonResponse({
            "success": True, 
            "action": action, 
            "count": target.upvotes.count()
        })
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

# ============================
# DOWNLOAD STUDY MATERIAL
# ============================
def download_study_material_view(request, material_id):

    material = get_object_or_404(StudyMaterial, id=material_id)
    course = material.course

    dashboard_type = request.session.get('active_dashboard', 'student')
    if not check_course_access(request.user, course, dashboard_type=dashboard_type):
        messages.warning(request, "You do not have access to this study material.")
        return redirect("users:courses")

    # ✅ Teacher / staff → full access
    if request.user.is_authenticated and request.user.is_staff:
        return FileResponse(material.file.open(), as_attachment=True)

    # ❌ Guest user
    if not request.user.is_authenticated:
        messages.warning(request, "Please login to download study materials.")
        return redirect("users:login")

    # Logged in → check admission safely
    try:
        student = request.user.profile  # ✅ correct
    except (StudentProfile.DoesNotExist, AttributeError):
        messages.warning(
            request,
            "Please complete your admission to access this material."
        )
        return redirect("users:course_detail", course_id=course.id)

    if student.status != "admitted":
        messages.warning(
            request,
            "Complete your admission to unlock all study materials."
        )
        return redirect("users:course_detail", course_id=course.id)

    # ✅ Admitted student → allow download
    return FileResponse(material.file.open(), as_attachment=True)

# -------------------------------------------------------------------
# TEACHER – COURSE MANAGEMENT VIEWS
# -------------------------------------------------------------------
@login_required
@user_passes_test(is_teacher)
def teacher_courses_view(request):
    courses = (
        Course.objects
        .all()
        .order_by("-created_at")
        .prefetch_related("materials")
    )
    return render(request, "users/teacher_courses.html", {
        "courses": courses,
        "BATCH_CHOICES": StudentProfile.BATCH_CHOICES,
    })


@login_required
@user_passes_test(is_teacher)
def teacher_course_preview_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    curriculum = StudyMaterial.objects.filter(course=course).order_by('order', 'created_at')
    
    questions = CourseQuestion.objects.filter(course=course).order_by('-created_at')
    reviews = CourseReview.objects.filter(course=course).order_by('-created_at')
    
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg'] or 0
    enrolled_count = StudentProfile.objects.filter(status='admitted').count() # Simple count for now
    
    # --- REAL ENGAGEMENT METRICS ---
    share_count = course.shares.count()
    
    # Calculate unique student access per material
    # We'll attach a 'unique_students' attribute to each item in curriculum
    leaderboard_data = []
    max_students = 0
    
    for item in curriculum:
        count = StudentMaterialAccess.objects.filter(material=item).count()
        item.unique_students = count
        leaderboard_data.append(item)
        if count > max_students:
            max_students = count
    
    # Sort leaderboard by students descending
    leaderboard_data.sort(key=lambda x: x.unique_students, reverse=True)
    
    first_video = curriculum.filter(material_type='video').first()

    # Rating Stats for distribution bars
    rating_stats = reviews.values('rating').annotate(count=Count('rating')).order_by('-rating')
    stats_dict = {i: 0 for i in range(1, 6)}
    for s in rating_stats:
        stats_dict[s['rating']] = s['count']
    total_reviews = reviews.count()

    return render(request, "users/teacher_course_preview.html", {
        "course": course,
        "curriculum": curriculum,
        "leaderboard_data": leaderboard_data,
        "first_video": first_video,
        "questions": questions,
        "reviews": reviews,
        "avg_rating": round(avg_rating, 1),
        "rating_stats": stats_dict,
        "total_reviews": total_reviews,
        "enrolled_count": enrolled_count,
        "share_count": share_count,
        "max_students": max_students if max_students > 0 else 1,
    })

@csrf_exempt
@login_required
def track_engagement_api(request):
    """API endpoint to track course shares and material access."""
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)
    
    try:
        data = json.loads(request.body)
        action = data.get("action") # 'share' or 'access'
        
        student = None
        if hasattr(request.user, 'profile'):
            student = request.user.profile

        if action == 'share':
            course_id = data.get("course_id")
            course = get_object_or_404(Course, id=course_id)
            CourseShare.objects.create(
                course=course,
                student=student,
                platform=data.get("platform", "generic")
            )
            return JsonResponse({"success": True})
            
        elif action == 'access':
            material_id = data.get("material_id")
            material = get_object_or_404(StudyMaterial, id=material_id)
            
            if not student:
                return JsonResponse({"error": "Only students can track access"}, status=403)
                
            # unique_together ensures we only have one record per student-material
            StudentMaterialAccess.objects.get_or_create(
                student=student,
                material=material
            )
            return JsonResponse({"success": True})
            
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=400)
    
    return JsonResponse({"error": "Invalid action"}, status=400)


@login_required
@require_POST
@user_passes_test(is_teacher)
def add_course_view(request):

    if not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect("users:teacher_courses")

    title = request.POST.get("title")
    description = request.POST.get("description", "")
    is_active = request.POST.get("is_active") == "1"
    thumbnail = request.FILES.get("thumbnail")

    if not title:
        messages.error(request, "Course title is required.")
        return redirect("users:teacher_courses")

    cropped_data = request.POST.get("cropped_thumbnail")

    # Target audience extraction
    target_public = request.POST.get("target_public") == "1"
    target_coaching = request.POST.get("target_coaching") == "1"
    target_alumni = request.POST.get("target_alumni") == "1"
    target_library = request.POST.get("target_library") == "1"
    target_private = request.POST.get("target_private") == "1"

    coaching_batches_list = request.POST.getlist("coaching_batches")
    library_floors_list = request.POST.getlist("library_floors")

    if target_private:
        target_public = False
        target_coaching = False
        target_alumni = False
        target_library = False
    elif target_public:
        target_coaching = False
        target_alumni = False
        target_library = False

    course = Course(
        title=title,
        description=description,
        is_active=is_active,
        created_by=request.user,
        target_public=target_public,
        target_coaching=target_coaching,
        target_coaching_batches=",".join(coaching_batches_list),
        target_alumni=target_alumni,
        target_library=target_library,
        target_library_floors=",".join(library_floors_list),
        target_private=target_private,
    )

    if cropped_data and cropped_data.startswith("data:image"):
        try:
            import base64
            from django.core.files.base import ContentFile
            format, imgstr = cropped_data.split(';base64,')
            ext = format.split('/')[-1]
            data = ContentFile(base64.b64decode(imgstr), name=f"thumb_{timezone.now().timestamp()}.{ext}")
            course.thumbnail = data
        except Exception as e:
            if thumbnail: course.thumbnail = thumbnail
    elif thumbnail:
        course.thumbnail = thumbnail

    course.save()

    # 🔔 Notify all admitted students in background (non-blocking)
    threading.Thread(
        target=_send_new_course_notifications_bg,
        args=(course.id, title),
        daemon=True,
    ).start()

    messages.success(request, "Course created successfully.")
    return redirect("users:teacher_courses")

# ===================================================================
# BACKGROUND NOTIFICATION HELPERS (non-blocking email + notification)
# ===================================================================
import logging as _logging
_bg_logger = _logging.getLogger(__name__)

def _send_course_status_notifications_bg(course_id, is_active, course_title):
    """Send course status-change notifications & emails in a background thread."""
    from django.db import connection, close_old_connections
    close_old_connections()
    try:
        students = StudentProfile.objects.filter(status="admitted")
        status_text = "active" if is_active else "inactive"
        for student in students:
            try:
                create_notification(
                    user=student.user,
                    title="Course Status Updated",
                    message=f"Course '{course_title}' is now {status_text}.",
                    link=f"/courses/{course_id}/",
                    category="course"
                )
                send_html_email(
                    subject=f"Course Update: {course_title}",
                    to_email=get_user_notification_email(student.user),
                    template="emails/course_update.html",
                    context={
                        "title": "Course Status Updated",
                        "message": f"The status of course '{course_title}' has been updated to {status_text}.",
                        "course_name": course_title,
                        "action_url": f"{settings.SITE_URL}{reverse('users:courses')}",
                    },
                    fail_silently=True,
                )
            except Exception as e:
                _bg_logger.error(f"BG notify error (status) for {student.user.email}: {e}")
    except Exception as e:
        _bg_logger.error(f"BG course-status notification thread failed: {e}")
    finally:
        close_old_connections()


def _send_new_course_notifications_bg(course_id, course_title):
    """Send new-course notifications & emails in a background thread."""
    from django.db import connection, close_old_connections
    close_old_connections()
    try:
        students = StudentProfile.objects.filter(status="admitted")
        for student in students:
            try:
                create_notification(
                    user=student.user,
                    title="New Course Added",
                    message=f"A new course '{course_title}' has been added.",
                    link="/courses/",
                    category="course"
                )
                send_html_email(
                    subject=f"New Course Available: {course_title}",
                    to_email=get_user_notification_email(student.user),
                    template="emails/course_update.html",
                    context={
                        "title": "New Course Added!",
                        "message": f"A new course '{course_title}' has been added to the ABCD curriculum. Start learning today!",
                        "course_name": course_title,
                        "action_url": f"{settings.SITE_URL}{reverse('users:courses')}",
                    },
                    fail_silently=True,
                )
            except Exception as e:
                _bg_logger.error(f"BG notify error (new course) for {student.user.email}: {e}")
    except Exception as e:
        _bg_logger.error(f"BG new-course notification thread failed: {e}")
    finally:
        close_old_connections()


# TOGGLE COURSE ACTIVE/INACTIVE STATUS VIEW
@login_required
@user_passes_test(is_teacher)
def toggle_course_status(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    course.is_active = not course.is_active
    course.save()

    # Fire notifications in background thread – view returns immediately
    threading.Thread(
        target=_send_course_status_notifications_bg,
        args=(course.id, course.is_active, course.title),
        daemon=True,
    ).start()

    # AJAX request → JSON response (no page reload)
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"success": True, "is_active": course.is_active})

    return redirect("users:teacher_courses")


@login_required
@require_POST
@user_passes_test(is_teacher)
def edit_course_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    
    title = request.POST.get("title")
    description = request.POST.get("description", "")
    is_active = request.POST.get("is_active") == "1"
    thumbnail = request.FILES.get("thumbnail")
    cropped_data = request.POST.get("cropped_thumbnail")

    if not title:
        messages.error(request, "Title is required.")
        return redirect("users:teacher_courses")

    course.title = title
    course.description = description
    course.is_active = is_active

    # Target audience extraction and update
    target_public = request.POST.get("target_public") == "1"
    target_coaching = request.POST.get("target_coaching") == "1"
    target_alumni = request.POST.get("target_alumni") == "1"
    target_library = request.POST.get("target_library") == "1"
    target_private = request.POST.get("target_private") == "1"

    coaching_batches_list = request.POST.getlist("coaching_batches")
    library_floors_list = request.POST.getlist("library_floors")

    if target_private:
        target_public = False
        target_coaching = False
        target_alumni = False
        target_library = False
    elif target_public:
        target_coaching = False
        target_alumni = False
        target_library = False

    course.target_public = target_public
    course.target_coaching = target_coaching
    course.target_coaching_batches = ",".join(coaching_batches_list)
    course.target_alumni = target_alumni
    course.target_library = target_library
    course.target_library_floors = ",".join(library_floors_list)
    course.target_private = target_private

    remove_thumb = request.POST.get("remove_thumbnail") == "1"

    if remove_thumb:
        course.thumbnail = None
    elif cropped_data and cropped_data.startswith("data:image"):
        try:
            import base64
            from django.core.files.base import ContentFile
            format, imgstr = cropped_data.split(';base64,')
            ext = format.split('/')[-1]
            data = ContentFile(base64.b64decode(imgstr), name=f"thumb_edit_{timezone.now().timestamp()}.{ext}")
            course.thumbnail = data
        except Exception:
            if thumbnail: course.thumbnail = thumbnail
    elif thumbnail:
        course.thumbnail = thumbnail

    course.save()
    messages.success(request, "Course updated successfully.")
    return redirect("users:teacher_courses")


# SYNC COURSES VIEW
@login_required
@user_passes_test(lambda u: u.is_superuser)
def sync_courses_view(request):
    if request.method == "POST":
        try:
            sync_courses_from_youtube()
            messages.success(request, "YouTube courses synced successfully.")
        except Exception as e:
            messages.error(request, f"Sync failed: {e}")
    return redirect("users:teacher_courses")


# ===================================================================
# YOUTUBE SYNC WIZARD – AJAX API ENDPOINTS
# ===================================================================

@login_required
@require_http_methods(["GET"])
def yt_fetch_playlists_api(request):
    """Return all playlists from the configured YouTube channel."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Permission denied"}, status=403)

    channel_id = getattr(settings, "YOUTUBE_CHANNEL_ID", "").strip()
    if not channel_id:
        return JsonResponse({"error": "YOUTUBE_CHANNEL_ID is not configured in environment variables or .env"}, status=400)

    try:
        playlists = fetch_playlists(channel_id)
        data = []
        for pl in playlists:
            snippet = pl.get("snippet", {})
            thumbs = snippet.get("thumbnails", {})
            thumb_url = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
            data.append({
                "id": pl["id"],
                "title": snippet.get("title", ""),
                "description": snippet.get("description", "")[:150],
                "thumbnail": thumb_url,
                "itemCount": pl.get("contentDetails", {}).get("itemCount", "?"),
            })
        return JsonResponse({"playlists": data})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def yt_fetch_videos_api(request):
    """Return all uploaded videos from the configured YouTube channel."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Permission denied"}, status=403)

    channel_id = getattr(settings, "YOUTUBE_CHANNEL_ID", "").strip()
    if not channel_id:
        return JsonResponse({"error": "YOUTUBE_CHANNEL_ID is not configured in environment variables or .env"}, status=400)

    try:
        videos = fetch_channel_videos(channel_id, max_results=100)
        data = []
        for v in videos:
            snippet = v.get("snippet", {})
            vid_id = v.get("id", {})
            if isinstance(vid_id, dict):
                video_id = vid_id.get("videoId", "")
            else:
                video_id = str(vid_id)
            thumbs = snippet.get("thumbnails", {})
            thumb_url = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
            data.append({
                "videoId": video_id,
                "title": snippet.get("title", ""),
                "thumbnail": thumb_url,
                "publishedAt": snippet.get("publishedAt", ""),
            })
        return JsonResponse({"videos": data})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def yt_import_playlist_api(request):
    """Import a YouTube playlist as a course."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    playlist_id = body.get("playlist_id")
    if not playlist_id:
        return JsonResponse({"error": "playlist_id is required"}, status=400)

    # Check if already imported
    existing = Course.objects.filter(playlist_id=playlist_id).first()
    if existing:
        return JsonResponse({"error": f"Playlist already imported as '{existing.title}'"}, status=409)

    use_pl_thumb = body.get("use_playlist_thumbnail", False)
    custom_thumb_data = body.get("custom_thumbnail_data")

    try:
        channel_id = getattr(settings, "YOUTUBE_CHANNEL_ID", "").strip()
        if not channel_id:
            return JsonResponse({"error": "YOUTUBE_CHANNEL_ID is not configured in environment variables or .env"}, status=400)
        playlists = fetch_playlists(channel_id)
        pl_data = next((p for p in playlists if p["id"] == playlist_id), None)
        if not pl_data:
            return JsonResponse({"error": "Playlist not found"}, status=404)

        snippet = pl_data["snippet"]
        videos = fetch_playlist_videos(playlist_id)

        target_public = body.get("target_public", True)
        target_coaching = body.get("target_coaching", False)
        target_alumni = body.get("target_alumni", False)
        target_library = body.get("target_library", False)
        target_private = body.get("target_private", False)

        coaching_batches_list = body.get("coaching_batches", [])
        library_floors_list = body.get("library_floors", [])

        if target_private:
            target_public = False
            target_coaching = False
            target_alumni = False
            target_library = False
        elif target_public:
            target_coaching = False
            target_alumni = False
            target_library = False

        course = Course(
            title=snippet.get("title", "Untitled"),
            description=snippet.get("description", ""),
            playlist_id=playlist_id,
            video_count=len(videos),
            is_active=True,
            created_by=request.user,
            last_synced_at=timezone.now(),
            target_public=target_public,
            target_coaching=target_coaching,
            target_coaching_batches=",".join(coaching_batches_list),
            target_alumni=target_alumni,
            target_library=target_library,
            target_library_floors=",".join(library_floors_list),
            target_private=target_private,
        )

        # 🖼 THUMBNAIL LOGIC
        if custom_thumb_data and custom_thumb_data.startswith("data:image"):
            try:
                import base64
                from django.core.files.base import ContentFile
                format, imgstr = custom_thumb_data.split(';base64,')
                ext = format.split('/')[-1]
                data = ContentFile(base64.b64decode(imgstr), name=f"yt_pl_{timezone.now().timestamp()}.{ext}")
                course.thumbnail = data
            except Exception: pass
        
        elif use_pl_thumb:
            thumb_url = snippet.get("thumbnails", {}).get("maxres", {}).get("url") or \
                        snippet.get("thumbnails", {}).get("high", {}).get("url")
            if thumb_url:
                try:
                    import urllib.request
                    from django.core.files import File
                    from django.core.files.temp import NamedTemporaryFile
                    tmp = NamedTemporaryFile(delete=False, suffix='.jpg')
                    tmp_path = tmp.name
                    tmp.close()
                    urllib.request.urlretrieve(thumb_url, tmp_path)
                    with open(tmp_path, 'rb') as f:
                        course.thumbnail.save(f"pl_{playlist_id}.jpg", File(f), save=False)
                    import os
                    os.remove(tmp_path)
                except Exception: pass

        course.save()

        # ✅ NEW: Create StudyMaterial entries for each video to allow unified ordering
        for index, vid in enumerate(videos):
            StudyMaterial.objects.create(
                course=course,
                title=vid.get("title", f"Video {index + 1}"),
                external_url=f"https://www.youtube.com/watch?v={vid['video_id']}",
                material_type='video',
                order=index + 1
            )

        # Notify students in background (non-blocking)
        threading.Thread(
            target=_send_new_course_notifications_bg,
            args=(course.id, course.title),
            daemon=True,
        ).start()

        return JsonResponse({"success": True, "course_id": course.id, "title": course.title})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


@login_required
@require_POST
def yt_create_custom_course_api(request):
    """Create a course from hand-picked YouTube videos."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    title = body.get("title", "").strip()
    video_ids = body.get("video_ids", [])
    use_first_thumb = body.get("use_first_thumbnail", False)
    custom_thumb_data = body.get("custom_thumbnail_data")

    if not title:
        return JsonResponse({"error": "Course title is required"}, status=400)
    if not video_ids or len(video_ids) == 0:
        return JsonResponse({"error": "Select at least one video"}, status=400)

    try:
        # Build a comma-separated video ID string for storage
        # We'll store them in a custom field or use description
        video_id_str = ",".join(video_ids)

        target_public = body.get("target_public", True)
        target_coaching = body.get("target_coaching", False)
        target_alumni = body.get("target_alumni", False)
        target_library = body.get("target_library", False)
        target_private = body.get("target_private", False)

        coaching_batches_list = body.get("coaching_batches", [])
        library_floors_list = body.get("library_floors", [])

        if target_private:
            target_public = False
            target_coaching = False
            target_alumni = False
            target_library = False
        elif target_public:
            target_coaching = False
            target_alumni = False
            target_library = False

        course = Course(
            title=title,
            description=f"Custom course with {len(video_ids)} selected videos.",
            video_ids=video_id_str, # ✅ SAVE HERE
            video_count=len(video_ids),
            is_active=True,
            created_by=request.user,
            last_synced_at=timezone.now(),
            target_public=target_public,
            target_coaching=target_coaching,
            target_coaching_batches=",".join(coaching_batches_list),
            target_alumni=target_alumni,
            target_library=target_library,
            target_library_floors=",".join(library_floors_list),
            target_private=target_private,
        )

        # 🖼 THUMBNAIL LOGIC
        if custom_thumb_data and custom_thumb_data.startswith("data:image"):
            try:
                import base64
                from django.core.files.base import ContentFile
                format, imgstr = custom_thumb_data.split(';base64,')
                ext = format.split('/')[-1]
                data = ContentFile(base64.b64decode(imgstr), name=f"yt_custom_{timezone.now().timestamp()}.{ext}")
                course.thumbnail = data
            except Exception:
                pass
        
        elif use_first_thumb and video_ids:
            safe_vid = re.sub(r'[^a-zA-Z0-9_-]', '', video_ids[0])
            if safe_vid:
                # Try multiple qualities
                thumb_urls = [
                    f"https://img.youtube.com/vi/{safe_vid}/maxresdefault.jpg",
                    f"https://img.youtube.com/vi/{safe_vid}/hqdefault.jpg",
                    f"https://img.youtube.com/vi/{safe_vid}/mqdefault.jpg"
                ]
                
                for t_url in thumb_urls:
                    try:
                        import urllib.request
                        from django.core.files import File
                        from django.core.files.temp import NamedTemporaryFile
                        
                        # Check if URL exists
                        req = urllib.request.Request(t_url, method='HEAD')
                        with urllib.request.urlopen(req) as r:
                            if r.status == 200:
                                tmp = NamedTemporaryFile(delete=False, suffix='.jpg')
                                tmp_path = tmp.name
                                tmp.close()
                                urllib.request.urlretrieve(t_url, tmp_path)
                                with open(tmp_path, 'rb') as f:
                                    course.thumbnail.save(f"yt_{safe_vid}.jpg", File(f), save=False)
                                os.remove(tmp_path)
                                break
                    except Exception:
                        continue

        course.save()

        # ✅ NEW: Create StudyMaterial entries for each selected video
        for index, vid_id in enumerate(video_ids):
            StudyMaterial.objects.create(
                course=course,
                title=f"Video {index + 1}",
                external_url=f"https://www.youtube.com/watch?v={vid_id}",
                material_type='video',
                order=index + 1
            )

        # Notify students in background (non-blocking)
        threading.Thread(
            target=_send_new_course_notifications_bg,
            args=(course.id, course.title),
            daemon=True,
        ).start()

        return JsonResponse({"success": True, "course_id": course.id, "title": course.title})
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


# DELETE COURSE VIEW
@login_required
@user_passes_test(is_teacher)
def delete_course(request, course_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Only admin can delete courses.")

    course = get_object_or_404(Course, id=course_id)
    
    # 1. Physically delete files for all associated study materials
    for mat in course.materials.all():
        if mat.file:
            try:
                mat.file.delete(save=False)
            except Exception as e:
                logger.error(f"Error deleting material file {mat.id}: {e}")

    # 2. Physically delete course thumbnail file
    if course.thumbnail:
        try:
            course.thumbnail.delete(save=False)
        except Exception as e:
            logger.error(f"Error deleting course thumbnail {course.id}: {e}")

    # 3. Delete course object (CASCADE deletes all related database records)
    course.delete()
    messages.success(request, "Course and all associated data/files deleted successfully.")
    return redirect("users:teacher_courses")

# Delete Study Materials
@login_required
@user_passes_test(is_teacher)
def delete_study_material(request, material_id):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Only admin can delete materials.")

    material = get_object_or_404(StudyMaterial, id=material_id)
    course_id = material.course.id
    if material.file:
        try:
            material.file.delete(save=False)  # deletes file physically from storage
        except Exception as e:
            logger.error(f"Error deleting material file {material.id}: {e}")
    material.delete()

    messages.success(request, "Study material deleted successfully.")
    return redirect("users:teacher_course_materials", course_id=course_id)


# COURSE MATERIALS MANAGEMENT VIEW
@login_required
@user_passes_test(is_teacher)
def teacher_course_materials_view(request, course_id):
    course = get_object_or_404(Course, id=course_id)
    # Fetch unified curriculum sorted by order
    materials = StudyMaterial.objects.filter(course=course).order_by('order', 'created_at')

    return render(request, "users/teacher_course_materials.html", {
        "course": course,
        "materials": materials,
    })
# -------------------------------------------------------------------
# add course materials
@login_required
@user_passes_test(is_teacher)
def add_material_view(request, course_id):
    if not request.user.is_staff:
        messages.error(request, "Permission denied.")
        return redirect("users:teacher_courses")

    course = get_object_or_404(Course, id=course_id)

    if request.method != "POST":
        return redirect("users:teacher_course_materials", course_id=course.id)

    title = request.POST.get("title")
    material_type = request.POST.get("material_type")
    uploaded_file = request.FILES.get("file")
    video_url = request.POST.get("video_url")
    external_url = request.POST.get("external_url")
    description = request.POST.get("description", "")

    # Intelligent naming if title is missing
    if not title:
        if material_type == "file" and uploaded_file:
            import os
            title = os.path.splitext(uploaded_file.name)[0].replace('_', ' ').replace('-', ' ').title()
        elif material_type == "video" and video_url:
            title = "YouTube Video " + str(StudyMaterial.objects.filter(course=course, material_type='video').count() + 1)
        elif material_type == "link" and external_url:
            title = "Link " + str(StudyMaterial.objects.filter(course=course, material_type='link').count() + 1)
        else:
            title = "Untitled Material"

    # Get current max order
    max_order = StudyMaterial.objects.filter(course=course).aggregate(models.Max('order'))['order__max'] or 0
    next_order = max_order + 1

    # FILE MATERIAL
    if material_type == "file":
        if not uploaded_file:
            messages.error(request, "Please select a file to upload.")
            return redirect("users:teacher_course_materials", course_id=course.id)
        
        # Determine specific type from file extension
        ext = uploaded_file.name.lower()
        m_type = 'document'
        if ext.endswith(('.jpg', '.jpeg', '.png', '.gif')):
            m_type = 'image'
        elif ext.endswith(('.mp4', '.webm', '.avi')):
            m_type = 'video'

        StudyMaterial.objects.create(
            course=course,
            title=title,
            description=description,
            file=uploaded_file,
            material_type=m_type,
            order=next_order,
            uploaded_by=request.user,
            is_public=False
        )

    # VIDEO LINK MATERIAL
    elif material_type == "video":
        if not video_url:
            messages.error(request, "Video URL is required.")
            return redirect("users:teacher_course_materials", course_id=course.id)

        StudyMaterial.objects.create(
            course=course,
            title=title,
            description=description,
            external_url=video_url,
            material_type='video',
            order=next_order,
            uploaded_by=request.user,
            is_public=False
        )

    # EXTERNAL LINK MATERIAL
    elif material_type == "link":
        if not external_url:
            messages.error(request, "External URL is required.")
            return redirect("users:teacher_course_materials", course_id=course.id)

        StudyMaterial.objects.create(
            course=course,
            title=title,
            description=description,
            external_url=external_url,
            material_type='link',
            order=next_order,
            uploaded_by=request.user,
            is_public=False
        )

    else:
        messages.error(request, "Invalid material type.")

    messages.success(request, "Material added successfully.")
    return redirect("users:teacher_course_materials", course_id=course.id)

@login_required
@user_passes_test(is_teacher)
def edit_material_view(request, material_id):
    """Update study material details via AJAX or POST."""
    material = get_object_or_404(StudyMaterial, id=material_id)
    if not request.user.is_staff:
         return JsonResponse({"error": "Permission denied"}, status=403)

    if request.method == "POST":
        material.title = request.POST.get("title", material.title)
        material.description = request.POST.get("description", material.description)
        # Handle file replacement if needed, but for now just title/desc
        material.save()
        
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"success": True})
            
        messages.success(request, "Material updated successfully.")
        return redirect("users:teacher_course_materials", course_id=material.course.id)
    
    return JsonResponse({
        "id": material.id,
        "title": material.title,
        "description": material.description or "",
    })


@login_required
@require_POST
def bulk_update_materials(request, course_id):
    """Handle batch deletion and reordering of course materials."""
    if not request.user.is_staff:
        return JsonResponse({"error": "Permission denied"}, status=403)

    try:
        body = json.loads(request.body)
        action = body.get("action")
        item_ids = body.get("item_ids", [])

        if action == "delete":
            mats = StudyMaterial.objects.filter(id__in=item_ids, course_id=course_id)
            for mat in mats:
                if mat.file:
                    try:
                        mat.file.delete(save=False)
                    except Exception as e:
                        logger.error(f"Error deleting bulk material file {mat.id}: {e}")
            mats.delete()
            return JsonResponse({"success": True, "message": f"Deleted {len(item_ids)} items."})

        elif action == "reorder":
            orders = body.get("orders", {}) # { "item_id": new_order }
            for item_id, new_order in orders.items():
                StudyMaterial.objects.filter(id=item_id, course_id=course_id).update(order=new_order)
            return JsonResponse({"success": True})

        return JsonResponse({"error": "Invalid action"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)

# --- REGISTER VIEW ---
@never_cache
def register(request):
    # If already authenticated, redirect to the appropriate destination
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('users:teacher_dashboard')
        if StudentProfile.objects.filter(user=request.user).exists():
            return redirect('users:student_dashboard')
        return redirect('users:guest_page')

    if request.method == 'POST':
        action = request.POST.get('action')
        
        # 1. SEND OTP ACTION
        if action == 'send_otp':
            form = InitialRegisterForm(request.POST)
            if form.is_valid():
                username = form.cleaned_data.get('username')
                email = form.cleaned_data.get('email')
                password = request.POST.get('password1') # raw password for user creation later

                user_ip = request.META.get('REMOTE_ADDR') or 'anonymous'
                
                # 24-hour outer rate limit: max 3 verification requests per day (86400s) per IP or Email
                daily_ip_key = f"verification_daily_ip_{user_ip}"
                daily_email_key = f"verification_daily_email_{email.lower()}"
                
                daily_ip_count = cache.get(daily_ip_key, 0)
                daily_email_count = cache.get(daily_email_key, 0)
                
                if daily_ip_count >= 3 or daily_email_count >= 3:
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Verification code request limit reached (max 3 per day). Please try again tomorrow.'
                    }, status=429)

                # Check cooldown/attempts
                counter_key = f"reg_otp_count_{user_ip}"
                cooldown_key = f"reg_otp_cooldown_{user_ip}"

                import time
                cooldown_expiry = cache.get(cooldown_key)
                if cooldown_expiry:
                    remaining = int(max(0, cooldown_expiry - time.time()))
                    if remaining > 0:
                        return JsonResponse({'status': 'error', 'message': f"Please wait {remaining}s"}, status=429)

                attempts = cache.get_or_set(counter_key, 0, timeout=18000)
                if attempts >= 5:
                    return JsonResponse({'status': 'error', 'message': 'Too many verification attempts from this IP. Please try again in 5 hours.'}, status=429)

                # Generate 6-digit OTP
                otp = f"{random.randint(100000, 999999)}"
                
                # Store registration data in session
                request.session['pending_registration'] = {
                    'username': username,
                    'email': email,
                    'password': password,
                    'otp': otp,
                    'expires': time.time() + 300
                }
                request.session.modified = True

                # Send email
                try:
                    send_html_email(
                        subject="Verify your email for ABCD registration",
                        to_email=email,
                        template="emails/otp_register.html",
                        context={
                            "username": username,
                            "otp": otp,
                            "subject": "Verify your email for ABCD registration",
                            "preheader": "Use this OTP to complete your ABCD registration",
                            "login_url": f"{settings.SITE_URL}{reverse('users:login')}",
                        },
                        fail_silently=False
                    )
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': f"Error sending verification email: {e}"}, status=500)

                # Increment attempts, daily count and set 60s cooldown
                cache.set(counter_key, attempts + 1, timeout=18000)
                cache.set(cooldown_key, time.time() + 60, timeout=60)
                cache.set(daily_ip_key, daily_ip_count + 1, timeout=86400)
                cache.set(daily_email_key, daily_email_count + 1, timeout=86400)

                return JsonResponse({
                    'status': 'ok',
                    'message': 'Verification code sent to your email.',
                    'attempts': attempts + 1,
                    'cooldown_seconds': 60
                })
            else:
                errors = []
                for field in form:
                    for error in field.errors:
                        errors.append(error)
                for error in form.non_field_errors():
                    errors.append(error)
                return JsonResponse({'status': 'error', 'message': ' '.join(errors)}, status=400)

        # 2. RESEND OTP ACTION
        elif action == 'resend_otp':
            pending = request.session.get('pending_registration')
            if not pending:
                return JsonResponse({'status': 'error', 'message': 'Registration session expired. Please restart registration.'}, status=400)

            user_ip = request.META.get('REMOTE_ADDR') or 'anonymous'
            email = pending['email']

            # 24-hour outer rate limit: max 3 verification requests per day (86400s) per IP or Email
            daily_ip_key = f"verification_daily_ip_{user_ip}"
            daily_email_key = f"verification_daily_email_{email.lower()}"
            
            daily_ip_count = cache.get(daily_ip_key, 0)
            daily_email_count = cache.get(daily_email_key, 0)
            
            if daily_ip_count >= 3 or daily_email_count >= 3:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Verification code request limit reached (max 3 per day). Please try again tomorrow.'
                }, status=429)

            counter_key = f"reg_otp_count_{user_ip}"
            cooldown_key = f"reg_otp_cooldown_{user_ip}"

            import time
            cooldown_expiry = cache.get(cooldown_key)
            if cooldown_expiry:
                remaining = int(max(0, cooldown_expiry - time.time()))
                if remaining > 0:
                    return JsonResponse({'status': 'error', 'message': f"Please wait {remaining}s"}, status=429)

            attempts = cache.get(counter_key, 0)
            if attempts >= 5:
                return JsonResponse({'status': 'error', 'message': 'Too many verification attempts from this IP.'}, status=429)

            # Generate new OTP
            otp = f"{random.randint(100000, 999999)}"
            pending['otp'] = otp
            pending['expires'] = time.time() + 300
            request.session['pending_registration'] = pending
            request.session.modified = True

            # Send email
            try:
                send_html_email(
                    subject="Verify your email for ABCD registration",
                    to_email=pending['email'],
                    template="emails/otp_register.html",
                    context={
                        "username": pending['username'],
                        "otp": otp,
                        "subject": "Verify your email for ABCD registration",
                        "preheader": "Use this OTP to complete your ABCD registration",
                        "login_url": f"{settings.SITE_URL}{reverse('users:login')}",
                    },
                    fail_silently=False
                )
            except Exception as e:
                return JsonResponse({'status': 'error', 'message': f"Error sending verification email: {e}"}, status=500)

            cache.set(counter_key, attempts + 1, timeout=18000)
            cache.set(cooldown_key, time.time() + 60, timeout=60)
            cache.set(daily_ip_key, daily_ip_count + 1, timeout=86400)
            cache.set(daily_email_key, daily_email_count + 1, timeout=86400)

            return JsonResponse({
                'status': 'ok',
                'message': 'New verification code sent to your email.',
                'attempts': attempts + 1,
                'cooldown_seconds': 60
            })

        # 3. VERIFY OTP AND COMPLETE REGISTRATION
        elif action == 'verify_otp':
            user_ip = request.META.get('REMOTE_ADDR') or 'anonymous'
            
            # Account creation rate limit (max 3 per IP per hour)
            creation_count_key = f"account_creations_count_{user_ip}"
            creation_count = cache.get(creation_count_key, 0)
            if creation_count >= 3:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Too many accounts created from this IP. Limit is 3 per hour.'
                }, status=429)

            counter_key = f"reg_otp_count_{user_ip}"
            cooldown_key = f"reg_otp_cooldown_{user_ip}"

            pending = request.session.get('pending_registration')
            if not pending:
                return JsonResponse({'status': 'error', 'message': 'Verification session expired. Please register again.'}, status=400)

            import time
            if time.time() > pending.get('expires', 0):
                return JsonResponse({'status': 'error', 'message': 'OTP has expired. Please request a new one.'}, status=400)

            submitted_otp = (request.POST.get('otp') or "").strip()
            if submitted_otp == pending.get('otp'):
                username = pending['username']
                email = pending['email']
                password = pending['password']

                # Create user
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            username=username,
                            email=email,
                            password=password
                        )
                except Exception as e:
                    return JsonResponse({'status': 'error', 'message': f'Error creating account: {e}'}, status=500)

                # Log user in
                login(request, user, backend='django.contrib.auth.backends.ModelBackend')

                # Clear session
                try:
                    del request.session['pending_registration']
                except KeyError:
                    pass

                # Set session flag for registration success animation
                request.session['show_registration_animation'] = True

                # Clear IP block cache on success
                cache.delete(counter_key)
                cache.delete(cooldown_key)
                
                # Increment creations count
                cache.set(creation_count_key, creation_count + 1, timeout=3600)

                return JsonResponse({
                    'status': 'ok',
                    'message': 'Account created successfully!',
                    'redirect': reverse('users:post_login_router')
                })
            else:
                return JsonResponse({'status': 'error', 'message': 'Invalid OTP. Please try again.'}, status=400)

        # Fallback standard submission just in case (should not be reached with AJAX active)
        form = InitialRegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            email = form.cleaned_data.get('email')
            if email:
                user.email = email
            user.save()
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Account created for {user.username}! Please complete your admission details.')
            return redirect('users:guest_page')
        else:
            messages.error(request, 'Please correct the errors below.')
            return render(request, 'users/register.html', {
                'form': form,
                'registration_failed': True
            })
    else:
        form = InitialRegisterForm()
    return render(request, 'users/register.html', {'form': form})



def _register_failed_attempt(ip, username, user_obj=None):
    """
    Increments failed login attempts for IP and username, and sets lockouts if they exceed 5.
    Returns (is_locked_out, message_to_display)
    """
    import time
    
    # failed count in 15-minute window keys
    ip_failed_key = f"login_failed_ip_{ip}"
    user_failed_key = f"login_failed_user_{username}"

    # Increment failure counts
    ip_failed = cache.get(ip_failed_key, 0) + 1
    user_failed = cache.get(user_failed_key, 0) + 1

    cache.set(ip_failed_key, ip_failed, timeout=900) # 15 minutes window
    cache.set(user_failed_key, user_failed, timeout=900) # 15 minutes window

    # Check limits
    ip_locked = False
    user_locked = False
    
    if ip_failed >= 5:
        ip_locked = True
        phase_key = f"login_lock_phase_ip_{ip}"
        phase = cache.get(phase_key, 0) + 1
        cache.set(phase_key, phase, timeout=86400 * 7) # keep phase memory for 7 days
        
        # lock duration
        if phase == 1:
            duration = 300 # 5 mins
        elif phase == 2:
            duration = 900 # 15 mins
        else:
            duration = 86400 # 24 hours
            
        cache.set(f"login_lock_until_ip_{ip}", time.time() + duration, timeout=duration)
        cache.delete(ip_failed_key) # reset counter after lockout

    if user_failed >= 5:
        user_locked = True
        phase_key = f"login_lock_phase_user_{username}"
        phase = cache.get(phase_key, 0) + 1
        cache.set(phase_key, phase, timeout=86400 * 7)
        
        if phase == 1:
            duration = 300
        elif phase == 2:
            duration = 900
        else:
            duration = 86400
            
        cache.set(f"login_lock_until_user_{username}", time.time() + duration, timeout=duration)
        cache.delete(user_failed_key)

    # Maintain the original 24-hour limit too (5 attempts in 24 hours per user pk)
    # (keeps the already implemented features as requested by user)
    if user_obj:
        attempts_key = f"login_attempts_{user_obj.pk}"
        attempts = cache.get(attempts_key, 0) + 1
        cache.set(attempts_key, attempts, timeout=86400)
        remaining_24h = max(0, 5 - attempts)
    else:
        remaining_24h = 5

    # Determine feedback message
    if ip_locked or user_locked:
        # Lockout occurred
        phase = max(cache.get(f"login_lock_phase_ip_{ip}", 0), cache.get(f"login_lock_phase_user_{username}", 0))
        if phase == 1:
            duration_str = "5 minutes"
        elif phase == 2:
            duration_str = "15 minutes"
        else:
            duration_str = "24 hours"
        
        msg = f"Too many failed login attempts. This account/IP has been locked for {duration_str}."
        return True, msg
    else:
        # standard failure message
        remaining_15m = 5 - max(ip_failed, user_failed)
        remaining = min(remaining_15m, remaining_24h)
        if remaining > 0:
            msg = f"Incorrect password. You have {remaining} attempt{'s' if remaining != 1 else ''} left, or you can use 'Forgot Password'."
        else:
            msg = "Incorrect password. You have used all failed attempts. Account locked."
        return False, msg


@never_cache
def login_view(request):
    """
    Login with either username OR email + password.
    enforces 5 wrong-password attempts in 24 hours, plus 15m/progressive IP & username locks.
    """
    # If already logged in -> go straight where they belong
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('users:teacher_dashboard')
        if StudentProfile.objects.filter(user=request.user).exists():
            return redirect('users:student_dashboard')
        else:
            return redirect('users:guest_page')

    user_ip = request.META.get('REMOTE_ADDR') or 'anonymous'

    # 1. Check IP lockout
    ip_lock_key = f"login_lock_until_ip_{user_ip}"
    ip_lock_expiry = cache.get(ip_lock_key)
    if ip_lock_expiry:
        import time
        remaining = int(max(0, ip_lock_expiry - time.time()))
        if remaining > 0:
            minutes = remaining // 60
            seconds = remaining % 60
            time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
            messages.error(
                request,
                f"Too many failed attempts from this IP. Please try again in {time_str}."
            )
            return render(request, 'users/register.html', {'form': InitialRegisterForm()})

    if request.method == 'POST':
        # Same input box, but can contain username OR email
        identifier = (request.POST.get('username') or "").strip()
        password = request.POST.get('password') or ""

        if not identifier or not password:
            messages.error(request, "Please enter username/email & password.")
            return render(request, 'users/register.html', {
                'form': InitialRegisterForm()
            })

        # Try username
        user_obj = User.objects.filter(username__iexact=identifier).first()

        # Try email if not found
        if user_obj is None:
            user_obj = User.objects.filter(email__iexact=identifier).first()

        # If user exists, rate limit by their unique username key.
        # Otherwise, rate limit by the identifier string.
        username_key = user_obj.username.lower() if user_obj else identifier.lower()

        # 2. Check Username lockout
        user_lock_key = f"login_lock_until_user_{username_key}"
        user_lock_expiry = cache.get(user_lock_key)
        if user_lock_expiry:
            import time
            remaining = int(max(0, user_lock_expiry - time.time()))
            if remaining > 0:
                minutes = remaining // 60
                seconds = remaining % 60
                time_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"
                messages.error(
                    request,
                    f"This account is temporarily locked due to too many failed login attempts. Please try again in {time_str}."
                )
                return render(request, 'users/register.html', {'form': InitialRegisterForm()})

        # Not found anywhere
        if user_obj is None:
            _register_failed_attempt(user_ip, username_key)
            messages.error(
                request,
                "No account found with this username or email. "
                "If you are a new student, please register first."
            )
            return render(request, 'users/register.html', {
                'form': InitialRegisterForm()
            })
        
        # 2) Check failed attempts in last 24 hours (original limit)
        cache_key = f"login_attempts_{user_obj.pk}"
        attempts = cache.get(cache_key, 0)

        if attempts >= 5:
            messages.error(
                request,
                'You have reached the limit of 5 wrong password attempts '
                'in the last 24 hours. Please use "Forgot Password" to '
                'reset your account.'
            )
            return render(request, 'users/register.html', {
                'form': InitialRegisterForm()
            })

        # 2.5) Check if user exists but has no usable password (Google-only)
        if not user_obj.has_usable_password():
            _register_failed_attempt(user_ip, username_key)
            messages.error(
                request,
                "This account was created via Google Sign-In. "
                "Please click 'Sign in with Google' to log in, or use 'Forgot Password' to set a local password."
            )
            return render(request, 'users/register.html', {
                'form': InitialRegisterForm()
            })

        # 3) Authenticate using the *username* that belongs to that email/identifier
        user = authenticate(
            request,
            username=user_obj.username,
            password=password
        )

        if user is not None:
            # SUCCESS: reset attempt counters, lockout phases & log in
            cache.delete(f"login_failed_ip_{user_ip}")
            cache.delete(f"login_failed_user_{username_key}")
            cache.delete(f"login_lock_phase_ip_{user_ip}")
            cache.delete(f"login_lock_phase_user_{username_key}")
            
            cache.delete(cache_key) # original 24hr key
            login(request, user)

            # Optional: respect ?next= URL if present (validated to prevent open redirect)
            next_url = request.GET.get('next')
            if next_url:
                from django.urls import resolve, reverse, Resolver404
                try:
                    match = resolve(next_url)
                    # Reconstruct URL from resolved view name (not user input)
                    safe_url = reverse(match.view_name, args=match.args, kwargs=match.kwargs)
                    return redirect(safe_url)
                except (Resolver404, ValueError, Exception):
                    pass  # Invalid URL, fall through to default redirects

            if user.is_staff:
                return redirect('users:teacher_dashboard')
            else:
                if StudentProfile.objects.filter(user=user).exists():
                    return redirect('users:student_dashboard')
                else:
                    return redirect('users:guest_page')
        else:
            locked_out, msg = _register_failed_attempt(user_ip, username_key, user_obj)
            messages.error(request, msg)
            return render(request, 'users/register.html', {'form': InitialRegisterForm()})

    # GET → just show combined login/register page
    return render(request, 'users/register.html', {'form': InitialRegisterForm()})


# -----------------------------
# FORGOT PASSWORD VIEW
def forgot_password_request(request):
    """
    POST: expects {'email': '...'}
    Sends OTP + username to the user's email (if user exists).
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    email = (request.POST.get('email') or "").strip()
    if not email:
        return JsonResponse({'status': 'error', 'message': 'Email is required'}, status=400)

    try:
        # Assuming email is unique per user
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'No account found with this email. Please register first.'
        }, status=404)

    user_ip = request.META.get('REMOTE_ADDR') or 'anonymous'
    
    # 24-hour outer rate limit: max 3 verification requests per day (86400s) per IP or Email
    daily_ip_key = f"verification_daily_ip_{user_ip}"
    daily_email_key = f"verification_daily_email_{email.lower()}"
    
    daily_ip_count = cache.get(daily_ip_key, 0)
    daily_email_count = cache.get(daily_email_key, 0)
    
    if daily_ip_count >= 3 or daily_email_count >= 3:
        return JsonResponse({
            'status': 'error',
            'message': 'Verification code request limit reached (max 3 per day). Please try again tomorrow.'
        }, status=429)

    # SUCCESSFUL PASSWORD RESET COOLDOWN (1 hour)
    cooldown_key = f"pwreset_cooldown_{user.id}"
    if cache.get(cooldown_key):
        return JsonResponse({
            'status': 'error',
            'message': 'For security, you must wait 1 hour between password resets.'
        }, status=400)

    # Determine tracking identifier (logged-in vs anonymous)
    if request.user.is_authenticated:
        user_id = str(request.user.id)
    else:
        user_id = user_ip

    # Cache keys
    counter_key = f"otp_resend_count_{user_id}"
    cooldown_key = f"otp_cooldown_{user_id}"

    # 60s COOLDOWN BETWEEN OTP REQUESTS
    import time
    cooldown_expiry = cache.get(cooldown_key)
    if cooldown_expiry:
        remaining = int(max(0, cooldown_expiry - time.time()))
        if remaining > 0:
            return JsonResponse({
                'status': 'error',
                'message': f"Please wait {remaining}s"
            }, status=429)

    # 3 ATTEMPTS PER 5 HOURS LIMIT
    # Use get_or_set to initialize to 0 if it doesn't exist, timeout 5 hours (18000s)
    attempts = cache.get_or_set(counter_key, 0, timeout=18000)
    if attempts >= 3:
        return JsonResponse({
            'status': 'error',
            'message': 'Too many attempts'
        }, status=429)

    # Generate 6-digit OTP
    otp = f"{random.randint(100000, 999999)}"
    cache_key = f"pwreset_otp_{user.pk}"
    cache.set(cache_key, otp, timeout=300)  # 5 minutes

    try:
        send_html_email(
            subject="Your ABCD password reset OTP",
            to_email=user.email,
            template="emails/otp_security.html",
            context={
                "username": user.username,
                "otp": otp,
                "subject": "Your ABCD password reset OTP",
                "preheader": "Use this OTP to reset your ABCD password",
                "login_url": f"{settings.SITE_URL}{reverse('users:login')}",
            },
            fail_silently=False
        )
    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": f"Error sending mail: {e}"},
            status=500
        )

    # Increment resend count, daily counts and set 60s cooldown on success
    attempts = cache.get(counter_key, 0)
    cache.set(counter_key, attempts + 1, timeout=18000)  # 5 hours
    cache.set(cooldown_key, time.time() + 60, timeout=60)  # 60s
    cache.set(daily_ip_key, daily_ip_count + 1, timeout=86400)
    cache.set(daily_email_key, daily_email_count + 1, timeout=86400)

    return JsonResponse({
        "status": "ok",
        "message": "An email has been sent with your OTP.",
        "attempts": attempts + 1,
        "cooldown_seconds": 60
    })


def otp_status_view(request):
    """
    API endpoint returning current OTP resend status/attempts/cooldown.
    """
    if request.user.is_authenticated:
        user_id = str(request.user.id)
    else:
        user_id = request.META.get('REMOTE_ADDR') or 'anonymous'

    counter_key = f"otp_resend_count_{user_id}"
    cooldown_key = f"otp_cooldown_{user_id}"

    attempts = cache.get(counter_key, 0)
    
    import time
    cooldown_expiry = cache.get(cooldown_key)
    cooldown_seconds = 0
    if cooldown_expiry:
        cooldown_seconds = int(max(0, cooldown_expiry - time.time()))

    return JsonResponse({
        'status': 'ok',
        'attempts': attempts,
        'cooldown_seconds': cooldown_seconds
    })

# -----------------------------
# VERIFY OTP VIEW
def verify_otp_view(request):
    """
    POST expects {'email': '...', 'otp': '...'}
    Verifies OTP and stores the user ID in session for reset.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    email = (request.POST.get('email') or "").strip()
    otp = (request.POST.get('otp') or "").strip()

    if not email or not otp:
        return JsonResponse({'status': 'error', 'message': 'Email and OTP are required'}, status=400)

    try:
        user = User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'No account found with this email.'}, status=404)

    cache_key = f"pwreset_otp_{user.pk}"
    stored = cache.get(cache_key)
    if stored and stored == otp:
        cache.delete(cache_key)
        # store user id in session for reset step
        request.session['pwreset_user_id'] = user.pk
        request.session.set_expiry(600)  # 10 minutes to complete reset
        return JsonResponse({'status': 'ok', 'message': 'OTP verified'})
    else:
        return JsonResponse({'status': 'error', 'message': 'Invalid or expired OTP'}, status=400)


def reset_password_view(request):
    """
    POST expects {'new_password': '...', 'confirm_password': '...'}
    Uses request.session['pwreset_user_id'] to allow resetting.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=405)

    user_id = request.session.get('pwreset_user_id')
    if not user_id:
        return JsonResponse({'status': 'error', 'message': 'OTP session expired or not verified'}, status=403)

    new_password = request.POST.get('new_password')
    confirm_password = request.POST.get('confirm_password')

    if not new_password or not confirm_password:
        return JsonResponse({'status': 'error', 'message': 'Password fields required'}, status=400)
    if new_password != confirm_password:
        return JsonResponse({'status': 'error', 'message': 'Passwords do not match'}, status=400)

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)

    # Check if the new password is the same as the current one
    if user.check_password(new_password):
        return JsonResponse({'status': 'error', 'message': 'New password cannot be the same as your current password.'}, status=400)

    # Validate password strength using Django validators
    from django.contrib.auth.password_validation import validate_password
    try:
        validate_password(new_password, user)
    except ValidationError as e:
        return JsonResponse({'status': 'error', 'message': ' '.join(e.messages)}, status=400)

    user.set_password(new_password)
    user.save()

    # Update password_last_updated
    from django.utils import timezone
    if hasattr(user, 'profile'):
        profile = user.profile
        profile.password_last_updated = timezone.now()
        profile.save()
    request.session['password_last_updated'] = timezone.now().isoformat()

    # Set 1-hour cooldown
    cache.set(f"pwreset_cooldown_{user.id}", True, timeout=3600)

    # If there is a pending google association for this email, link it and log them in!
    assoc_data = request.session.get('google_assoc_data')
    linked = False
    if assoc_data and assoc_data.get('email', '').lower() == user.email.lower():
        from social_django.models import UserSocialAuth
        UserSocialAuth.objects.get_or_create(
            user=user,
            provider=assoc_data['provider'],
            uid=assoc_data['uid']
        )
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        linked = True
        try:
            del request.session['google_assoc_data']
        except KeyError:
            pass

    # clear session flag
    try:
        del request.session['pwreset_user_id']
    except KeyError:
        pass

    if linked:
        return JsonResponse({
            'status': 'ok',
            'message': 'Password reset and Google account linked successfully! Redirecting...',
            'redirect': reverse('users:post_login_router')
        })
    return JsonResponse({'status': 'ok', 'message': 'Password reset successful'})


def link_existing_account_by_email(backend, strategy, details, response, user=None, *args, **kwargs):
    if user:
        return {'user': user, 'is_new': False}

    email = details.get('email')
    if not email:
        return

    existing_user = User.objects.filter(email__iexact=email).first()
    if existing_user:
        return {'user': existing_user, 'is_new': False}


def set_new_user_flag(backend, strategy, details, response, user=None, is_new=False, *args, **kwargs):
    request = kwargs.get('request') or (strategy.request if strategy and hasattr(strategy, 'request') else None)
    if is_new and request:
        request.session['show_registration_animation'] = True
    return



@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('users:home_page')


@login_required
def profile_view(request):
    """
    Unified Profile Router:
    Redirects authenticated users to their correct profile/dashboard details page.
    """
    active_dash = request.session.get('active_dashboard')
    if active_dash == 'student':
        return redirect('users:student_details_S')
    elif active_dash == 'alumni':
        from .models import StudentAchievement
        ach = StudentAchievement.objects.filter(user=request.user).first()
        if ach:
            return redirect('users:achievement_detail', pk=ach.pk)

    # Fallback to default user dashboard type
    from .utils import get_user_dashboard_type
    dtype = get_user_dashboard_type(request.user)
    if dtype == 'student':
        return redirect('users:student_details_S')
    elif dtype == 'alumni':
        from .models import StudentAchievement
        ach = StudentAchievement.objects.filter(user=request.user).first()
        if ach:
            return redirect('users:achievement_detail', pk=ach.pk)
        return redirect('users:guest_profile_details')
    elif dtype == 'teacher':
        return redirect('users:teacher_dashboard')
    else:
        return redirect('users:guest_profile_details')

def _get_password_date_display(request):
    user = request.user
    password_date_display = None
    if hasattr(user, 'profile') and user.profile.password_last_updated:
        dt = user.profile.password_last_updated
        password_date_display = f"Updated at {dt.strftime('%d %b %Y, %I:%M %p')}"
    elif 'password_last_updated' in request.session:
        from django.utils.dateparse import parse_datetime
        dt_str = request.session['password_last_updated']
        dt = parse_datetime(dt_str)
        if dt:
            password_date_display = f"Updated at {dt.strftime('%d %b %Y, %I:%M %p')}"
            
    if not password_date_display:
        dt = user.date_joined
        password_date_display = f"Created at {dt.strftime('%d %b %Y, %I:%M %p')}"
        
    return password_date_display


@login_required
def guest_profile_details_view(request):
    """
    Renders the Guest Profile details page for logged-in users with no profile.
    """
    from .utils import get_user_dashboard_type
    dtype = get_user_dashboard_type(request.user)
    if dtype in ('student', 'alumni', 'teacher'):
        return redirect('users:profile')
        
    # Dynamic base template
    base_template = _get_base_template(request.user)
    
    return render(request, 'users/guest_profile_details.html', {
        'base_template': base_template,
        'password_date_display': _get_password_date_display(request),
    })


@login_required
@require_POST
def change_password_view(request):
    """
    Verifies current password (if set) and changes user's password.
    Updates the session to prevent logout.
    """
    current_password = request.POST.get('current_password')
    new_password = request.POST.get('new_password')
    confirm_password = request.POST.get('confirm_password')

    if not current_password or not new_password or not confirm_password:
        return JsonResponse({'status': 'error', 'message': 'All fields are required.'}, status=400)

    # Strictly verify current password
    if not request.user.check_password(current_password):
        return JsonResponse({'status': 'error', 'message': 'Incorrect current password.'}, status=400)

    # Check if new password is the same as the current password
    if new_password == current_password or request.user.check_password(new_password):
        return JsonResponse({'status': 'error', 'message': 'New password cannot be the same as your current password.'}, status=400)

    if new_password != confirm_password:
        return JsonResponse({'status': 'error', 'message': 'New passwords do not match.'}, status=400)

    # Django password validation
    from django.contrib.auth.password_validation import validate_password
    try:
        validate_password(new_password, request.user)
    except ValidationError as e:
        return JsonResponse({'status': 'error', 'message': ' '.join(e.messages)}, status=400)

    request.user.set_password(new_password)
    request.user.save()

    # Update password_last_updated
    from django.utils import timezone
    if hasattr(request.user, 'profile'):
        profile = request.user.profile
        profile.password_last_updated = timezone.now()
        profile.save()
    request.session['password_last_updated'] = timezone.now().isoformat()

    # Update session auth hash to maintain session
    from django.contrib.auth import update_session_auth_hash
    update_session_auth_hash(request, request.user)

    return JsonResponse({'status': 'success', 'message': 'Password changed successfully!'})



@login_required
def guest_page_view(request):
    try:
        track_visitor_intent(request.user, "guest_browsed")
    except Exception:
        pass

    try:
        youtube_videos = get_latest_youtube_videos()
    except Exception:
        youtube_videos = []

    try:
        preview_courses = list(get_accessible_courses(request.user)[:3])
    except Exception:
        preview_courses = []

    try:
        _ach_pool = list(
            StudentAchievement.objects.filter(status='approved')
            .order_by('-id')[:50]
        )
        achievements = random.sample(_ach_pool, min(len(_ach_pool), 8))
    except Exception:
        achievements = []

    try:
        resolved_complaints_count = Complaint.objects.filter(status='resolved').count()
    except Exception:
        resolved_complaints_count = 0

    try:
        avail_seats = get_available_seats_count()
    except Exception:
        avail_seats = 0

    try:
        courses_count = get_accessible_courses(request.user).count()
    except Exception:
        courses_count = len(preview_courses)

    show_reg_animation = request.session.pop('show_registration_animation', False)

    return render(request, 'users/guest_page.html', {
        "youtube_videos": youtube_videos,
        "preview_courses": preview_courses,
        "achievements": achievements,
        "res_count": resolved_complaints_count,
        "avail_seats_count": avail_seats,
        "courses_count": courses_count,
        "profile": None,
        "show_registration_animation": show_reg_animation,
    })

@login_required
def post_login_router(request):
    """Runs after ANY login (normal or Google). Decides where to send the user."""
    user = request.user

    # 3) Teacher / admin
    if request.user.is_staff or request.user.is_superuser:
        return redirect('users:teacher_dashboard')

    profile = StudentProfile.objects.filter(user=request.user).first()
    achievement = StudentAchievement.objects.filter(user=request.user).first()
    has_valid_profile = profile and (profile.is_admitted or profile.dob or profile.father_name)

    # Priority 1: Dual Identity users (Admitted Student + Alumni)
    if has_valid_profile and achievement:
        if profile.is_admitted or profile.dob:
            request.session['active_dashboard'] = 'student'
            return redirect('users:student_dashboard')
        request.session['active_dashboard'] = 'alumni'
        return redirect('users:alumni_dashboard')

    # Priority 2: Alumni only
    if achievement:
        request.session['active_dashboard'] = 'alumni'
        return redirect('users:alumni_dashboard')

    # Priority 3: Student only (Pending or Admitted)
    if has_valid_profile:
        request.session['active_dashboard'] = 'student'
        return redirect('users:student_dashboard')

    # Default: New user / Guest
    return redirect('users:guest_page')

# set_password_after_google was deleted during OAuth refactor
# -------------------------------------------------------------------

@never_cache
def smart_back_router(request):
    """Dynamically routes users to their correct home base on browser back."""
    if not request.user.is_authenticated:
        return redirect('users:home_page')

    if request.user.is_staff or request.user.is_superuser:
        return redirect('users:teacher_dashboard')

    active_dash = request.session.get('active_dashboard')
    if active_dash == 'student':
        return redirect('users:student_dashboard')
    elif active_dash == 'alumni':
        return redirect('users:alumni_dashboard')

    profile = StudentProfile.objects.filter(user=request.user).first()
    achievement = StudentAchievement.objects.filter(user=request.user).first()
    has_valid_profile = profile and (profile.is_admitted or profile.dob or profile.father_name)

    # Dual Identity users
    if has_valid_profile and achievement:
        if profile.is_admitted or profile.dob:
            return redirect('users:student_dashboard')
        return redirect('users:alumni_dashboard')

    if achievement:
        return redirect('users:alumni_dashboard')

    if has_valid_profile:
        return redirect('users:student_dashboard')

    return redirect('users:guest_page')


@login_required
@deduplicate_request(timeout=2)
def admission_form_view(request):
    """
    Handles both NEW and ALREADY ADMITTED students.
    Includes a retry mechanism for 'database is locked' OperationalError (SQLite).
    """
    # --- Is this user already admitted in DB? ---
    try:
        profile = StudentProfile.objects.select_related('seat').get(user=request.user)
        has_profile = True
    except StudentProfile.DoesNotExist:
        profile = None
        has_profile = False

    # Block access if already registered/pending for both services
    coaching_registered = profile and (profile.service_type in ['Coaching', 'Both'] or profile.coaching_pending)
    library_registered = profile and (profile.service_type in ['Library', 'Both'] or profile.library_pending)
    if coaching_registered and library_registered:
        messages.info(request, "You have already registered for all available services.")
        if StudentAchievement.objects.filter(user=request.user, status='approved').exists():
            return redirect('users:alumni_dashboard')
        return redirect('users:student_dashboard')

    disabled_services = []
    if coaching_registered:
        disabled_services.append('Coaching')
    if library_registered:
        disabled_services.append('Library')

    # ======================= GET ==========================
    if request.method == "GET":
        # Track visitor intent safely for SQLite
        try:
            track_visitor_intent(request.user, "opened_admission")
        except OperationalError:
            pass # Ignore lock during GET tracking
        if has_profile:
            first_name, *rest = (profile.full_name or '').split(' ', 1)
            last_name = rest[0] if rest else ''
            initial = {
                'first_name': first_name,
                'last_name': last_name,
                'email': profile.email or profile.user.email,
                'is_new_registration': 'False',
            }
            form = StudentProfileForm(instance=profile, initial=initial, user=request.user, disabled_services=disabled_services)
        else:
            initial = {'is_new_registration': 'True', 'email': request.user.email or ''}
            form = StudentProfileForm(initial=initial, user=request.user, disabled_services=disabled_services)
        return render(request, 'users/admission_form.html', {'form': form})

    # ======================= POST ==========================
    if request.method == 'POST':
        form = StudentProfileForm(request.POST, request.FILES, instance=profile, user=request.user, disabled_services=disabled_services)

        if not form.is_valid():
            messages.error(request, "Please correct the errors below.")
            return render(request, 'users/admission_form.html', {'form': form})

        cleaned = form.cleaned_data
        service_type = cleaned['service_type']
        is_new_choice = cleaned.get('is_new_registration') == 'True'

        # Force existing if already in DB
        if has_profile and is_new_choice:
            messages.info(request, "We found your existing record. Your request will be treated as an already admitted student.")
            is_new_choice = False

        # Duplicate check (read-only)
        if has_profile:
            is_duplicate = True
            if service_type != profile.service_type:
                is_duplicate = False
            elif service_type == 'Coaching':
                if cleaned.get('batch') != profile.batch:
                    is_duplicate = False
            elif service_type == 'Library':
                floor_val = (cleaned.get('floor') or request.POST.get('floor') or '').strip()
                seat_val = (cleaned.get('selected_seat') or request.POST.get('selected_seat') or '').strip()
                if floor_val != (profile.seat.floor if profile.seat else None) or \
                   seat_val != (profile.seat.seat_number if profile.seat else None):
                    is_duplicate = False
            
            if is_duplicate:
                messages.warning(request, "You already have an active admission with these exact details.")
                return render(request, 'users/admission_form.html', {'form': form, 'show_duplicate_popup': True})

        # --- RETRY LOOP FOR DATABASE LOCKS ---
        for attempt in range(3):
            try:
                # Success actions to be performed OUTSIDE the transaction
                deferred_actions = []
                final_redirect = None
                submission_success_message = "Admission form submitted successfully! Log in again to access your dashboard once approved."
                
                with transaction.atomic():
                    # Preparation
                    student_profile = form.save(commit=False)
                    if not cleaned.get('first_name') or not cleaned.get('last_name'):
                        if profile:
                            student_profile.full_name = profile.full_name
                            student_profile.sex = profile.sex
                            student_profile.dob = profile.dob
                        else:
                            ach = StudentAchievement.objects.filter(user=request.user).first()
                            if ach:
                                student_profile.full_name = ach.full_name
                                student_profile.sex = ach.gender.capitalize() if ach.gender else 'Male'
                                student_profile.dob = ach.dob
                    else:
                        student_profile.full_name = f"{cleaned['first_name']} {cleaned['last_name']}"

                    student_profile.admission_type = 'new' if is_new_choice else 'existing'
                    student_profile.is_manual_pending = False
                    
                    if not has_profile:
                        student_profile.user = request.user
                        student_profile.status = 'pending'
                    else:
                        # Existing student registering for a second service
                        if service_type == 'Coaching':
                            student_profile.coaching_pending = True
                        elif service_type == 'Library':
                            student_profile.library_pending = True

                    # 1. Visitor Intents
                    VisitorIntent.objects.filter(user=request.user, resolved=False).update(
                        resolved=True, resolved_at=timezone.now()
                    )

                    # 2. Email sync
                    email_value = (cleaned.get('email') or '').strip()
                    if email_value:
                        student_profile.email = email_value
                    elif not student_profile.email and request.user.email:
                        student_profile.email = request.user.email

                    # 3. Library Logic
                    if service_type == 'Library':
                        selected_floor = (cleaned.get('floor') or request.POST.get('floor') or request.POST.get('floor_radio') or '').strip()
                        selected_seat_num = (cleaned.get('selected_seat') or request.POST.get('selected_seat') or '').strip()
                        selected_shift = cleaned.get('shift_preference') or request.POST.get('shift_preference') or 'full'
                        is_temporary_request = request.POST.get('is_temporary_request') == 'true'

                        if not selected_floor or not selected_seat_num:
                            raise ValidationError("Please select a library floor and seat.")

                        # Already-admitted students CANNOT request temporary allotment
                        if student_profile.admission_type == 'existing':
                            is_temporary_request = False

                        # Save profile to get ID
                        student_profile.save()
                        
                        old_seat = student_profile.seat
                        try:
                            seat = Seat.objects.select_for_update().get(floor=selected_floor, seat_number=selected_seat_num)
                        except Seat.DoesNotExist:
                            seat, _ = Seat.objects.get_or_create(
                                floor=selected_floor,
                                seat_number=selected_seat_num,
                                defaults={'status': 'available'}
                            )
                        
                        # Shift enforcement
                        is_strict_shift_seat = (selected_floor == 'Ground Floor' and 40 <= int(selected_seat_num) <= 53)
                        if seat.is_shift_enabled != is_strict_shift_seat:
                            seat.is_shift_enabled = is_strict_shift_seat
                            seat.save(update_fields=['is_shift_enabled'])
                        
                        if not is_strict_shift_seat:
                            selected_shift = 'full'

                        # Hold Check
                        active_assignments = SeatAssignment.objects.filter(seat=seat, is_active=True)
                        requested_shift_on_hold = False
                        if is_strict_shift_seat:
                            full_hold = active_assignments.filter(shift_type='full', hold_status='active').exists()
                            specific_hold = active_assignments.filter(shift_type=selected_shift, hold_status='active').exists()
                            if selected_shift == 'full':
                                m_hold = active_assignments.filter(shift_type='morning', hold_status='active').exists()
                                e_hold = active_assignments.filter(shift_type='evening', hold_status='active').exists()
                                requested_shift_on_hold = full_hold or m_hold or e_hold
                            else:
                                requested_shift_on_hold = full_hold or specific_hold
                        else:
                            requested_shift_on_hold = seat.status == 'on_hold' or active_assignments.filter(hold_status='active').exists()

                        if requested_shift_on_hold:
                            if is_temporary_request:
                                student_profile.seat = seat
                                student_profile.shift = selected_shift
                                student_profile.status = 'pending'
                                student_profile.save(update_fields=['seat', 'shift', 'status'])

                                if not SeatSpecialRequest.objects.filter(seat=seat, requested_shift=selected_shift, status='pending').exists():
                                    SeatSpecialRequest.objects.create(
                                        student=student_profile, seat=seat, requested_shift=selected_shift, status='pending'
                                    )
                                    create_notification(
                                        user=student_profile.user, title="Temporary Seat Request Submitted",
                                        message=f"Your temporary request for Seat {seat.seat_number} ({selected_shift}) has been submitted.",
                                        link="/dashboard/", category="seat"
                                    )
                                    deferred_actions.append(lambda: send_html_email(
                                        subject="Temporary Seat Request Submitted", to_email=settings.ADMIN_EMAIL,
                                        template="emails/admin_temp_seat_request.html",
                                        context={
                                            "student": student_profile, 
                                            "seat_number": seat.seat_number, 
                                            "floor": selected_floor, 
                                            "shift": selected_shift,
                                            "dashboard_url": f"{settings.SITE_URL}{reverse('users:teacher_dashboard')}"
                                        },
                                        run_async=True
                                    ))
                                    submission_success_message = 'Temporary seat request submitted! Teacher will review it. Please log in again to check status.'
                                    final_redirect = 'users:login'
                                else:
                                    raise ValidationError(f"A temporary request for Seat {seat.seat_number} ({selected_shift}) is already pending.")
                            else:
                                raise ValidationError("This seat is currently on hold. Use temporary seat request options.")
                        else:
                            # Save profile first to get ID and persist all fields (including photo)
                            student_profile.save()
                            
                            # Regular assignment
                            # Validation check via temp assignment
                            SeatAssignment(seat=seat, student=student_profile, shift_type=selected_shift, is_active=False).full_clean()
                            
                            student_profile.shift = selected_shift
                            student_profile.status = 'pending'
                            student_profile.seat = seat 
                            student_profile.save()

                            # Manage assignments
                            SeatAssignment.objects.filter(student=student_profile, is_active=False).delete()
                            SeatAssignment.objects.create(seat=seat, student=student_profile, shift_type=selected_shift, is_active=False)
                            
                            # Deactivate old assignments
                            for a in SeatAssignment.objects.filter(student=student_profile).exclude(seat=seat):
                                a.deactivate()

                            # Mark old seat available if empty
                            if old_seat and old_seat != seat:
                                if not SeatAssignment.objects.filter(seat=old_seat, is_active=True).exists():
                                    old_seat.mark_available()

                            create_notification(
                                user=student_profile.user, title="Seat Reserved",
                                message=f"Seat {seat.seat_number} ({selected_shift} shift) reserved pending teacher approval.",
                                link="/dashboard/", category="seat"
                            )
                            deferred_actions.append(lambda: send_html_email(
                                subject="Library Admission / Seat Request", to_email=settings.ADMIN_EMAIL,
                                template="emails/admin_library_request.html",
                                context={
                                    "student": student_profile, 
                                    "seat": seat, 
                                    "is_new": not has_profile, 
                                    "shift": selected_shift,
                                    "dashboard_url": f"{settings.SITE_URL}{reverse('users:teacher_dashboard')}"
                                },
                                run_async=True
                            ))
                            submission_success_message = 'Admission form submitted successfully! Your library seat request is pending approval. Log in again to access your dashboard once approved.'
                            final_redirect = 'users:login'

                    # 4. Coaching Logic
                    else:
                        student_profile.save()
                        if student_profile.seat_id is not None or student_profile.shift != 'full':
                            student_profile.seat = None
                            student_profile.shift = 'full'
                            student_profile.save(update_fields=['seat', 'shift'])
                        
                        deferred_actions.append(lambda: send_html_email(
                            subject="Coaching Admission Submission", to_email=settings.ADMIN_EMAIL,
                            template="emails/admin_coaching_request.html", 
                            context={
                                "student": student_profile,
                                "batch": student_profile.get_batch_display() if hasattr(student_profile, 'get_batch_display') else student_profile.batch,
                                "dashboard_url": f"{settings.SITE_URL}{reverse('users:teacher_dashboard')}"
                            },
                            run_async=True
                        ))
                        submission_success_message = 'Admission form submitted successfully! Please wait for teacher approval. Log in again to access your dashboard once approved.'
                        final_redirect = 'users:login'

                    # Link any user-level special seat requests to the new student profile
                    SeatSpecialRequest.objects.filter(user=request.user, student__isnull=True).update(student=student_profile)

                # --- OUTSIDE ATOMIC BLOCK: Perform deferred actions ---
                for action in deferred_actions:
                    try:
                        action()
                    except Exception as e:
                        print(f"DEBUG Admission Form Post-Action Error: {e}")

                if final_redirect == 'users:login':
                    from django.contrib.auth import logout
                    logout(request)
                    messages.success(request, submission_success_message)
                
                return redirect(final_redirect or 'users:login')

            except ValidationError as e:
                # Validation errors are user-facing, no retry needed
                messages.error(request, e.message if hasattr(e, 'message') else str(e))
                return render(request, 'users/admission_form.html', {'form': form})
            except OperationalError as e:
                if "database is locked" in str(e) and attempt < 2:
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise
            except Exception as e:
                print(f"DEBUG Admission Form Error: {e}")
                messages.error(request, "There was an error processing your admission. Please try again.")
                return render(request, 'users/admission_form.html', {'form': form})

    return render(request, 'users/admission_form.html', {'form': form})
    
# -------------------------------------------------------------------
# API VIEW: Records interest in an occupied seat
@login_required
@require_POST
def seat_interest_api(request):
    """
    Called ONLY when user clicks:
    'Notify me when this seat becomes available'
    on an OCCUPIED seat.
    """
    try:
        data = json.loads(request.body)
        seat_number = data.get("seat_number")
        floor = data.get("floor")

        if not seat_number or not floor:
            return JsonResponse({"error": "Invalid data"}, status=400)

        track_visitor_intent(
            request.user,
            "selected_library_seat",
            metadata={
                "seat_number": str(seat_number),
                "floor": floor,
                "intent_scope": "specific"
            }
        )

        return JsonResponse({"status": "ok"})

    except Exception as e:
        return JsonResponse({"error": "Failed"}, status=500)

# -------------------------------------------------------------------
# This function is called by the JavaScript to get seat statuses
# -------------------------------------------------------------------
@login_required
def get_seat_status_api(request):
    floor = request.GET.get('floor')
    if not floor:
        return JsonResponse({'error': 'Floor parameter is required'}, status=400)

    seats = (
        Seat.objects
        .filter(floor=floor)
        .prefetch_related('assignments', 'assignments__student', 'special_requests')
    )

    today = timezone.now().date()
    seat_data = []

    for seat in seats:
        # --- ENFORCE STRICT SHIFT DEFINITION ---
        try:
            num = int(str(seat.seat_number).replace('G-', '').replace('F-', '').strip())
            seat.is_shift_enabled = (seat.floor == 'Ground Floor' and 40 <= num <= 53)
        except (ValueError, TypeError):
            seat.is_shift_enabled = False
        # ---------------------------------------

        active_assignments = [
            a for a in seat.assignments.all()
            if a.is_active
        ]
        
        is_my_seat = False
        student_name = None
        user_shift = None  

        for a in active_assignments:
            if a.student.user_id == request.user.id:
                is_my_seat = True
                student_name = a.student.full_name
                user_shift = a.shift_type  # 'morning', 'evening', or 'full'
                break

        # Check for pending temporary requests
        pending_special_requests = [
            r for r in seat.special_requests.all()
            if r.status == 'pending'
        ]
        has_pending_temp_request = len(pending_special_requests) > 0
        morning_has_pending = any(r.requested_shift == 'morning' for r in pending_special_requests)
        evening_has_pending = any(r.requested_shift == 'evening' for r in pending_special_requests)
        full_day_has_pending = any(r.requested_shift == 'full' for r in pending_special_requests)

        # Get hold information per shift
        morning_hold = False
        evening_hold = False
        full_day_hold = False
        morning_hold_remaining_days = 0
        evening_hold_remaining_days = 0
        full_day_hold_remaining_days = 0
        morning_temp_allotted = False
        evening_temp_allotted = False

        for assignment in active_assignments:
            if assignment.hold_status == 'active':
                hold_end = assignment.hold_end_date
                hold_days = max((hold_end - today).days, 0) if hold_end else 0
                
                if assignment.shift_type == 'morning':
                    morning_hold = True
                    morning_hold_remaining_days = hold_days
                elif assignment.shift_type == 'evening':
                    evening_hold = True
                    evening_hold_remaining_days = hold_days
                elif assignment.shift_type == 'full':
                    full_day_hold = True
                    full_day_hold_remaining_days = hold_days

            if assignment.is_partial:
                if assignment.shift_type == 'morning':
                    morning_temp_allotted = True
                elif assignment.shift_type == 'evening':
                    evening_temp_allotted = True
                elif assignment.shift_type == 'full':
                    morning_temp_allotted = True
                    evening_temp_allotted = True

        # Normalized status for legacy JS support
        status = seat.status
        if status == 'pending': status = 'occupied'
        
        shifts = {a.shift_type for a in active_assignments}

        seat_info = {
            'seat_number': seat.seat_number,
            'floor': seat.floor,
            'status': status,
            'is_shift_enabled': seat.is_shift_enabled,
            'morning_taken': 'morning' in shifts,
            'evening_taken': 'evening' in shifts,
            'full_day_taken': 'full' in shifts,
            'is_on_hold': seat.status == 'on_hold' or full_day_hold or morning_hold or evening_hold,
            'morning_hold': morning_hold,
            'evening_hold': evening_hold,
            'full_day_hold': full_day_hold,
            'morning_hold_remaining_days': morning_hold_remaining_days,
            'evening_hold_remaining_days': evening_hold_remaining_days,
            'full_day_hold_remaining_days': full_day_hold_remaining_days,
            'morning_temp_allotted': morning_temp_allotted,
            'evening_temp_allotted': evening_temp_allotted,
            'has_pending_temp_request': has_pending_temp_request,
            'morning_has_pending': morning_has_pending,
            'evening_has_pending': evening_has_pending,
            'full_day_has_pending': full_day_has_pending,
            # Lock information (needed for switch seat selection)
            'is_locked': seat.is_locked,
            'locked_shifts': seat.locked_shifts or '',
        }

        if is_my_seat:
            seat_info['student_name'] = student_name
            seat_info['student_first_name'] = request.user.first_name
            seat_info['user_shift'] = user_shift

        seat_data.append(seat_info)

    return JsonResponse({'seats': seat_data})


# -------------------------------------------------------------------
# VIEW: Renders the public "Library Availability" page
def library_availability_view(request):
    """
    Renders the public, read-only seat availability page.
    This view doesn't need @login_required.
    """
    track_visitor_intent(request.user, "viewed_library")
    return render(request, 'users/library_availability.html')


# -------------------------------------------------------------------
# API VIEW: Public seat status for admission form & library availability
# -------------------------------------------------------------------
def get_public_seat_status_api(request):
    floor = request.GET.get('floor')
    if not floor:
        return JsonResponse({'error': 'Floor parameter is required'}, status=400)

    seats = Seat.objects.filter(floor=floor).prefetch_related(
        'assignments',
        'assignments__student',
        'special_requests'
    )
    today = timezone.now().date()
    seat_data = []

    for seat in seats:
        # --- ENFORCE STRICT SHIFT DEFINITION ---
        if seat.floor == 'Ground Floor' and 40 <= int(seat.seat_number) <= 53:
            seat.is_shift_enabled = True
        else:
            seat.is_shift_enabled = False
        # ---------------------------------------
        
        active_assignments = [
            a for a in seat.assignments.all()
            if a.is_active
        ]

        # Check for pending temporary requests
        pending_special_requests = [
            r for r in seat.special_requests.all()
            if r.status == 'pending'
        ]
        has_pending_temp_request = len(pending_special_requests) > 0
        morning_has_pending = any(r.requested_shift == 'morning' for r in pending_special_requests)
        evening_has_pending = any(r.requested_shift == 'evening' for r in pending_special_requests)
        full_day_has_pending = any(r.requested_shift == 'full' for r in pending_special_requests)

        hold_shifts = {
            a.shift_type
            for a in active_assignments
            if a.hold_status == 'active'
        }

        shifts = {a.shift_type for a in active_assignments}

        morning_taken = 'morning' in shifts
        evening_taken = 'evening' in shifts
        full_day_taken = 'full' in shifts

        # Get hold information per shift
        morning_hold = False
        evening_hold = False
        full_day_hold = False
        morning_hold_remaining_days = 0
        evening_hold_remaining_days = 0
        full_day_hold_remaining_days = 0
        morning_hold_student_id = None
        evening_hold_student_id = None
        morning_temp_allotted = False
        evening_temp_allotted = False

        for assignment in active_assignments:
            if assignment.hold_status == 'active':
                hold_end = assignment.hold_end_date
                if hold_end:
                    hold_days = max((hold_end - today).days, 0)
                else:
                    hold_days = 0
                
                if assignment.shift_type == 'morning':
                    morning_hold = True
                    morning_hold_remaining_days = hold_days
                    morning_hold_student_id = assignment.student.user.id
                elif assignment.shift_type == 'evening':
                    evening_hold = True
                    evening_hold_remaining_days = hold_days
                    evening_hold_student_id = assignment.student.user.id
                elif assignment.shift_type == 'full':
                    full_day_hold = True
                    full_day_hold_remaining_days = hold_days

            if full_day_hold:
                morning_hold = True
                evening_hold = True
                if morning_hold_remaining_days == 0 or full_day_hold_remaining_days < morning_hold_remaining_days:
                    morning_hold_remaining_days = full_day_hold_remaining_days
                if evening_hold_remaining_days == 0 or full_day_hold_remaining_days < evening_hold_remaining_days:
                    evening_hold_remaining_days = full_day_hold_remaining_days

            # Check for temporary allotments
            if assignment.is_partial:
                if assignment.shift_type == 'morning':
                    morning_temp_allotted = True
                elif assignment.shift_type == 'evening':
                    evening_temp_allotted = True
                elif assignment.shift_type == 'full':
                    morning_temp_allotted = True
                    evening_temp_allotted = True

        visual_status = seat.status
        if visual_status == 'pending':
            visual_status = 'occupied'

        # Check for temporary/partial occupancy (Tenant present)
        is_temporarily_occupied = (
            (not seat.is_shift_enabled and (seat.status == 'on_hold' or full_day_hold) and morning_temp_allotted) or
            (seat.is_shift_enabled and (morning_temp_allotted or evening_temp_allotted))
        )

        if is_temporarily_occupied:
            visual_status = 'partial'
        elif seat.status == 'on_hold' or full_day_hold or morning_hold or evening_hold:
            visual_status = 'on_hold'
        elif full_day_taken or (morning_taken and evening_taken):
            visual_status = 'occupied'
        elif seat.is_shift_enabled and (morning_taken or evening_taken):
            visual_status = 'partial'
        else:
            visual_status = 'available'

        free_shifts = []
        if seat.is_shift_enabled and visual_status not in ['occupied', 'on_hold']:
            if not morning_taken:
                free_shifts.append('morning')
            if not evening_taken:
                free_shifts.append('evening')

        hold_conflict = (seat.status == 'on_hold' or morning_hold or evening_hold or full_day_hold) and seat.is_shift_enabled

        remaining_days = None
        if seat.status == 'on_hold' and seat.hold_end_date:
            remaining_days = max((seat.hold_end_date - today).days, 0)
        elif full_day_hold:
            remaining_days = full_day_hold_remaining_days
        elif morning_hold and not evening_hold:
            remaining_days = morning_hold_remaining_days
        elif evening_hold and not morning_hold:
            remaining_days = evening_hold_remaining_days


        allow_full_day = False

        if seat.is_shift_enabled:
            # exactly one shift on HOLD and the other completely free
            if len(hold_shifts) == 1:
                held_shift = next(iter(hold_shifts))
                other_shift = 'evening' if held_shift == 'morning' else 'morning'

                if other_shift not in shifts:
                    allow_full_day = True


        seat_data.append({
            'seat_number': seat.seat_number,
            'status': visual_status,
            'is_shift_enabled': seat.is_shift_enabled,
            'morning_taken': morning_taken,
            'evening_taken': evening_taken,
            'full_day_taken': full_day_taken,
            'free_shifts': free_shifts,
            'hold_conflict': hold_conflict,
            'remaining_days': remaining_days,
            'allow_full_day': allow_full_day,
            'is_on_hold': seat.status == 'on_hold',
            
            # NEW: Shift-wise hold information
            'morning_hold': morning_hold,
            'evening_hold': evening_hold,
            'full_day_hold': full_day_hold,
            'morning_hold_remaining_days': morning_hold_remaining_days,
            'evening_hold_remaining_days': evening_hold_remaining_days,
            'full_day_hold_remaining_days': full_day_hold_remaining_days,
            'morning_hold_student_id': morning_hold_student_id,
            'evening_hold_student_id': evening_hold_student_id,
            'morning_temp_allotted': morning_temp_allotted,
            'evening_temp_allotted': evening_temp_allotted,
            'has_pending_temp_request': has_pending_temp_request,
            'morning_has_pending': morning_has_pending,
            'evening_has_pending': evening_has_pending,
            'full_day_has_pending': full_day_has_pending,
            
            # Lock information
            'is_locked': seat.is_locked,
            'locked_shifts': seat.locked_shifts or '',
        })

    return JsonResponse({'seats': seat_data})

# -------------------------------------------------------------------
# VIEW: Renders the "Student Dashboard" page
@login_required
def student_dashboard_view(request):
    if not cache.get('holds_synced'):
        sync_active_holds()
        cache.set('holds_synced', True, 60 * 5)
    try:
        profile = StudentProfile.objects.select_related('seat').get(user=request.user)
        # If student profile is just an empty skeleton (no DOB and not admitted), send to guest page or alumni
        if not profile.is_admitted and not profile.dob and not profile.father_name:
            achievement = StudentAchievement.objects.filter(user=request.user).first()
            if achievement:
                return redirect('users:alumni_dashboard')
            return redirect('users:guest_page')

        # If Alumni and the student profile is just a skeleton (no DOB), send back to alumni dashboard
        achievement = StudentAchievement.objects.filter(user=request.user).first()
        if achievement and not profile.is_admitted and not profile.dob:
            return redirect('users:alumni_dashboard')
    except StudentProfile.DoesNotExist:
        # Shifting Logic: If admission deleted, check if Alumni remains
        achievement = StudentAchievement.objects.filter(user=request.user).first()
        if achievement:
            return redirect('users:alumni_dashboard')
        return redirect('users:guest_page')

    # -------------------------------
    # AUTO-EXPIRE OLD NOTIFICATIONS
    # -------------------------------
    
    all_notifications = Notification.objects.filter(
        user=request.user
    ).order_by('-created_at')

    # Count unread FIRST (before slicing)
    unread_count = all_notifications.filter(is_read=False).count()
    # Then slice for display (show up to 15)
    notifications = all_notifications[:15]

    achievement = StudentAchievement.objects.filter(user=request.user).first()

    # Track that we are in "Student Space"
    request.session['active_dashboard'] = 'student'

    context = {
        'profile': profile,
        'nav_achievement': achievement,
        "notifications": notifications,
        "unread_count": unread_count,
    }

    if profile.status == 'admitted':
        # Get all payments for this student
        payments_qs = Payment.objects.filter(student=profile)

        # Order by payment date (latest first), then by year
        fee_records = payments_qs.order_by('-date_paid', '-year')

        # Send to template
        context['fee_records'] = fee_records

        # --- LEADERBOARD LOGIC ---
        if profile.service_type == 'Coaching' and profile.batch:
            from .models import PerformanceRecord
            records = PerformanceRecord.objects.filter(batch=profile.batch).order_by('-created_at')[:5]
            
            records_list = []
            for r in records:
                scores = []
                for s in r.scores.all().order_by('-marks_obtained'):
                    s_photo_url = None
                    if s.student and s.student.photo:
                        try:
                            s_photo_url = s.student.photo.url
                        except (ValueError, AttributeError):
                            s_photo_url = None

                    scores.append({
                        'id': str(s.student.id) if s.student else '',
                        'name': s.student.full_name if s.student else 'Unknown',
                        'marks': s.marks_obtained,
                        'photo_url': s_photo_url
                    })
                records_list.append({
                    'id': str(r.id),
                    'topic': r.topic,
                    'total': r.total_marks,
                    'percent': r.show_in_percentage,
                    'marks': r.show_in_marks,
                    'scores': scores
                })
            context['performance_records_json'] = json.dumps(records_list)
            context['has_performance'] = len(records_list) > 0
            
            # --- Notification Logic ---
            now = timezone.now()
            context['today'] = now.date()
            context['expiry_threshold'] = now.date() + timedelta(days=10)
            context['notifications'] = Notification.objects.filter(user=request.user).order_by("-created_at")[:10]



    return render(request, 'users/student_dashboard.html', context)


@login_required
def alumni_dashboard_view(request):
    profile = StudentProfile.objects.filter(user=request.user).first()
    achievement = StudentAchievement.objects.filter(user=request.user).first()
    if not achievement:
        # Shifting Logic: If Alumni deleted, check if Student profile remains
        if profile and (profile.is_admitted or profile.dob):
            return redirect('users:student_dashboard')
        return redirect('users:guest_page')

    # Track that we are in "Alumni Space"
    request.session['active_dashboard'] = 'alumni'

    # Notifications — Alumni see general, course, and guidy-related; NOT seat/fee
    all_notifications = Notification.objects.filter(
        user=request.user
    ).exclude(
        category__in=['payment', 'hold']  # Exclude fee and seat hold for alumni
    ).order_by('-created_at')
    unread_count = all_notifications.filter(is_read=False).count()
    notifications = all_notifications[:15]

    # Content from guest page
    youtube_videos = get_latest_youtube_videos()
    preview_courses = get_accessible_courses(request.user)[:3]
    _ach_pool = list(
        StudentAchievement.objects.filter(status='approved')
        .order_by('-id')[:50]
    )
    
    other_achievers = [a for a in _ach_pool if a.user != request.user]
    show_marquee = len(other_achievers) >= 1
    marquee_achievements = []
    if show_marquee:
        marquee_achievements = _ach_pool
        if achievement and achievement not in marquee_achievements:
            marquee_achievements.insert(0, achievement)

    # Counts for cards
    resolved_complaints_count = Complaint.objects.filter(status='resolved').count()
    avail_seats_count = get_available_seats_count()
    courses_count = get_accessible_courses(request.user).count()

    context = {
        'profile': profile,
        'achievement': achievement, # For the page content
        'nav_achievement': achievement, # For the navbar
        'notifications': notifications,
        'unread_count': unread_count,
        'youtube_videos': youtube_videos,
        'preview_courses': preview_courses,
        'achievements': marquee_achievements,
        'show_marquee': show_marquee,
        'avail_seats_count': avail_seats_count,
        'courses_count': courses_count,
        'res_count': resolved_complaints_count,
        'is_alumni': True,  # Used in notification panel for alumni-specific UI
    }

    # --- ACHIEVEMENT ANALYTICS ---
    alumni_achievements = StudentAchievement.objects.filter(user=request.user, status='approved').order_by('selection_year')
    has_achievements = alumni_achievements.exists()
    
    if has_achievements:
        from django.db.models import Count
        yearly_data = alumni_achievements.values('selection_year').annotate(count=Count('id')).order_by('selection_year')
        
        achievement_years = []
        achievement_counts = []
        achievement_titles = []
        
        for item in yearly_data:
            year = item['selection_year']
            achievement_years.append(str(year))
            achievement_counts.append(item['count'])
            titles = list(alumni_achievements.filter(selection_year=year).values_list('current_post', flat=True))
            achievement_titles.append(titles)
            
        context.update({
            'has_alumni_achievements': True,
            'ach_years_json': json.dumps(achievement_years),
            'ach_counts_json': json.dumps(achievement_counts),
            'ach_titles_json': json.dumps(achievement_titles),
        })
    else:
        context['has_alumni_achievements'] = False

    return render(request, 'users/alumni_dashboard.html', context)



# notifications mark as viewed
@login_required
def mark_notifications_read(request):
    if request.method == "POST":
        now = timezone.now()
        Notification.objects.filter(
            user=request.user,
            is_read=False
        ).update(is_read=True, read_at=now)

        return JsonResponse({"status": "ok"})

    return HttpResponseForbidden("POST only")

# -------------------------------------------------------------------
# VIEW: Renders the "Your Seat Status" page
# -------------------------------------------------------------------   
@login_required
def your_seat_status_view(request):
    if not cache.get('holds_synced'):
        sync_active_holds()
        cache.set('holds_synced', True, 60 * 5)
    try:
        # Get the student's profile (seat is now a field on profile)
        profile = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        messages.error(request, "You must have an admission profile to view this page.")
        return redirect('users:guest_page')
    
    # Access the seat via ForeignKey
    seat = profile.seat

    if profile.service_type != 'Library' or not seat:
        messages.error(request, "This page is only for admitted library students with an assigned seat.")
        return redirect('users:student_dashboard')

    # Get today's date plus 3 days
    min_hold_date = (timezone.now() + timedelta(days=3)).strftime('%Y-%m-%d')
    
    # Find the current hold request (either pending, or approved future hold)
    hold_req = SeatHoldRequest.objects.filter(
        student=profile,
        seat=seat
    ).filter(
        models.Q(status='pending') | models.Q(status='approved')
    ).first()

    pending_switch = SeatSwitchRequest.objects.filter(
        student=profile,
        status='pending'
    ).select_related('target_seat').first()

    remaining_days = None
    days_of_hold = None
    end_date_calculated = None
    today = timezone.now().date()

    if hold_req:
        remaining_days = (hold_req.start_date - today).days
        if remaining_days < 0:
            remaining_days = 0

        # Calculate end date
        duration_str = hold_req.duration_text.lower()
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
                
        end_date_calculated = hold_req.start_date + relativedelta(months=months, days=days)
        days_of_hold = (end_date_calculated - hold_req.start_date).days

    # Detect teacher-scheduled future holds (hold_start_date set in the future, hold_status='none')
    # These don't have a SeatHoldRequest record — teacher did it directly from management pages.
    scheduled_hold = None
    if not hold_req:
        scheduled_hold = SeatAssignment.objects.filter(
            student=profile,
            is_active=True,
            hold_status='none',
            hold_start_date__isnull=False,
            hold_start_date__gt=today,
        ).first()

    context = {
        'profile': profile,
        'seat': seat,
        'min_hold_date': min_hold_date,
        'shift': profile.shift,
        'hold_req': hold_req,
        'pending_switch': pending_switch,
        'remaining_days': remaining_days,
        'days_of_hold': days_of_hold,
        'end_date_calculated': end_date_calculated,
        'scheduled_hold': scheduled_hold,
        'today': today,
    }
    return render(request, 'users/your_seat_status.html', context)

# -------------------------------------------------------------------
# VIEW: Renders the "Student Complaints" page
# -------------------------------------------------------------------
@login_required
def student_complaints_view(request):
    # each user has one StudentProfile linked as user.profile
    try:
        student = request.user.profile  # StudentProfile instance
    except Exception:
        # If no profile, check if they are an Alumni (have an achievement)
        if hasattr(request.user, 'achievements') and request.user.achievements.exists():
            ach = request.user.achievements.first()
            # Create a student profile for the alumni so they can use the complaints system
            student = StudentProfile.objects.create(
                user=request.user,
                full_name=abcd_format_name(f"{ach.first_name} {ach.last_name}"),
                mobile_number=ach.mobile_number or "N/A",
                whatsapp_number=ach.whatsapp_number or "N/A",
                sex=ach.gender,
                service_type=ach.services_used.capitalize() if ach.services_used in ['library', 'coaching'] else 'Coaching',
                status='pending', 
                is_admitted=False
            )
        else:
            return HttpResponseForbidden("You are not linked to a student profile.")

    # Get current role from session (default to student)
    current_role = request.session.get('active_dashboard', 'student')

    if request.method == "POST":
        form = ComplaintForm(request.POST, request.FILES)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.student = student
            complaint.role = current_role
            complaint.save()

            # Send Email to Admin/Teacher
            send_html_email(
                subject=f"New Complaint: {complaint.display_subject}",
                to_email=settings.ADMIN_EMAIL,
                template="emails/admin_complaint_raised.html",
                context={
                    "sender_name": student.full_name,
                    "complaint_subject": complaint.display_subject,
                    "role": current_role,
                    "complaint_code": complaint.code,
                    "raised_at": complaint.created_at,
                    "message": complaint.message,
                    "action_url": f"{settings.SITE_URL}{reverse('users:teacher_dashboard')}",
                },
                fail_silently=True,
                run_async=True,
            )

            # notify student at dashboard
            create_notification(
                user=request.user,
                title=f"Complaint Submitted ({current_role.capitalize()})",
                message="Your complaint has been submitted successfully. We will update you once it is reviewed.",
                link="/student/complaints/",
                category="complaint"
            )

            return redirect(
                "users:student_complaints_success",
                complaint_id=complaint.id,
            )
    else:
        form = ComplaintForm()

    complaints = student.complaints.filter(role=current_role).order_by("-created_at")

    context = {
        "student": student,
        "form": form,
        "complaints": complaints,
        "current_role": current_role,
    }

    return render(request, "users/student_complaints.html", context)

# -------------------------------------------------------------------
# VIEW: Renders the "Complaint Submitted Successfully" page
# -------------------------------------------------------------------
@login_required
def student_complaints_success_view(request, complaint_id):
    try:
        student = request.user.profile
    except Exception:
        # Check if they are an alumni with a freshly created profile
        if hasattr(request.user, 'achievements') and request.user.achievements.exists():
            from .models import StudentProfile
            student = StudentProfile.objects.filter(user=request.user).first()
            if not student:
                return HttpResponseForbidden("You are not linked to a student profile.")
        else:
            return HttpResponseForbidden("You are not linked to a student profile.")

    complaint = get_object_or_404(Complaint, id=complaint_id, student=student)

    images = []
    for img_field in (complaint.image1, complaint.image2, complaint.image3):
        if img_field:
            try:
                images.append(img_field.url)
            except (ValueError, AttributeError):
                pass

    return render(request, "users/student_complaint_success.html", {
        "student": student,
        "complaint": complaint,
        "images": images,
    })

# -------------------------------------------------------------------
# VIEW: Handles "Submit Complaint Rating" (modal POST from listing)
# -------------------------------------------------------------------
@login_required
def submit_complaint_rating(request, complaint_id):
    try:
        student = request.user.profile  # StudentProfile
    except Exception:
        # Check if they are an alumni with a freshly created profile
        if hasattr(request.user, 'achievements') and request.user.achievements.exists():
            from .models import StudentProfile
            student = StudentProfile.objects.filter(user=request.user).first()
            if not student:
                return HttpResponseForbidden("You are not linked to a student profile.")
        else:
            return HttpResponseForbidden("You are not linked to a student profile.")

    complaint = get_object_or_404(
        Complaint, id=complaint_id, student=student
    )

    if complaint.status != Complaint.STATUS_RESOLVED:
        return HttpResponseForbidden("You can rate only resolved complaints.")

    if request.method == "POST":
        form = ComplaintRatingForm(request.POST, instance=complaint)
        if form.is_valid():
            form.save()
            messages.success(request, "Thank you for rating your resolved complaint!")
            return redirect("users:student_complaints")
    else:
        form = ComplaintRatingForm(instance=complaint)

    current_role = request.session.get('active_dashboard', 'student')
    base_template = 'users/alumni_dashboard.html' if current_role == 'alumni' else 'users/student_dashboard.html'

    return render(request, "users/student_complaint_rate.html", {
        "complaint": complaint,
        "form": form,
        "base_template": base_template,
    })

# --------------------------------------------------------------------------------------------------------------
# API VIEW: Handles the "Update Complaint Status" request / {Teacher – change complaint status (AJAX-friendly)}
# --------------------------------------------------------------------------------------------------------------
@login_required
def update_complaint_status_view(request, complaint_id):
    # wrap with your teacher-only decorator if needed
    if request.method != "POST":
        return HttpResponseForbidden("POST only")

    complaint = get_object_or_404(Complaint, id=complaint_id)

    new_status = request.POST.get("status")
    if new_status not in {
        Complaint.STATUS_NEW,
        Complaint.STATUS_IN_PROGRESS,
        Complaint.STATUS_RESOLVED,
    }:
        return JsonResponse({"ok": False, "error": "Invalid status"}, status=400)

    complaint.status = new_status
    if new_status == Complaint.STATUS_RESOLVED:
        complaint.resolved_at = timezone.now()
    else:
        complaint.resolved_at = None
    complaint.save(update_fields=["status", "updated_at", "resolved_at"])

    # Send Email to Student for any status update
    send_html_email(
        subject=f"Complaint Status Updated: {complaint.display_subject}",
        to_email=get_user_notification_email(complaint.student.user),
        template="emails/complaint_status_update.html",
        context={
            "student_name": complaint.student.full_name,
            "complaint_code": complaint.code,
            "complaint_subject": complaint.display_subject,
            "status_text": complaint.get_status_display(),
            "action_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
        },
        fail_silently=True,
        run_async=True,
    )

    create_notification(
        user=complaint.student.user,
        title="Complaint Status Updated",
        message=f"Your complaint '{complaint.subject}' is now {complaint.get_status_display()}. Would you like to rate it ?",
        category="complaint",
        link="/student/complaints/"
    )
        
    return JsonResponse(
        {"ok": True, "status": complaint.get_status_display(), "id": complaint.id}
    )


# Ensure Complaint is imported (you already used it elsewhere)

def complaint_ratings_api(request):
    """
    Returns JSON:
    {
      "avg": 4.5,
      "count": 123,
      "recent": [
         {"id": 12, "code":"C00012","subject":"Wi-Fi", "rating":5, "image":"/media/..", "date":"2025-12-10"},
         ...
      ]
    }
    """
    # Only resolved complaints with a numeric rating
    # Try common rating field names (rating, rating_value). If none exist returns empty.
    rating_field = None
    sample = Complaint()
    # detect available field names
    for f in ('rating', 'rating_value', 'stars'):
        if hasattr(Complaint, f) or f in [f.name for f in Complaint._meta.get_fields()]:
            rating_field = f
            break

    # base queryset for resolved complaints (3 stars or higher only)
    qs = Complaint.objects.filter(
        status__in=['resolved', 'Resolved', 'RESOLVED'],
        rating__gte=3
    )

    # build aggregation safely
    avg = 0
    count = qs.count()
    try:
        if rating_field:
            agg = qs.aggregate(avg=Avg(rating_field))
            avg = agg['avg'] or 0
        else:
            # No rating field found -> return zeros
            avg = 0
    except Exception:
        avg = 0

    # recent resolved items (most-recent first)
    recent_qs = qs.order_by('-id')[:8]  # adjust limit
    recent = []
    for c in recent_qs:
        # try to get an image url (first available)
        image_url = None
        for img_field in ('image1', 'image2', 'image3'):
            if hasattr(c, img_field):
                img = getattr(c, img_field)
                if img:
                    try:
                        image_url = img.url
                        break
                    except Exception:
                        image_url = None
        # rating value try
        rating_val = None
        if rating_field:
            rating_val = getattr(c, rating_field, None)

        recent.append({
            'id': c.id,
            'code': getattr(c, 'code', getattr(c, 'get_code_display', '')),
            'subject': getattr(c, 'display_subject', getattr(c, 'subject', '')),
            'rating': rating_val,
            'image': image_url,
            'date': getattr(c, 'resolved_at', getattr(c, 'updated_at', None)) and (getattr(c, 'resolved_at', getattr(c, 'updated_at', None)).isoformat())
        })

    return JsonResponse({'avg': float(round(avg or 0, 2)), 'count': count, 'recent': recent})
# --------------------------------------------------------------------------------------------------------------
# Helper function to humanize duration
def humanize_duration(td):
    total_seconds = int(td.total_seconds())

    if total_seconds < 60:
        return "less than a minute"

    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes != 1 else ''}"

    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour{'s' if hours != 1 else ''}"

    days = hours // 24
    rem_hours = hours % 24

    if rem_hours:
        return f"{days} day{'s' if days != 1 else ''} {rem_hours} hour{'s' if rem_hours != 1 else ''}"
    return f"{days} day{'s' if days != 1 else ''}"

# -------------------------------------------------------------------
# VIEW: Renders the public "Resolved Complaints" page
def public_resolved_complaints(request):
    # Filter for resolved AND rating >= 3
    complaints = Complaint.objects.filter(status='resolved', rating__gte=3).order_by('-updated_at')
  
    for c in complaints:
        if c.updated_at and c.created_at:
            c.resolution_time = humanize_duration(c.updated_at - c.created_at)
        else:
            c.resolution_time = None

    paginator = Paginator(complaints, 5)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'users/resolved_complaints_public.html', {
        'page_obj': page_obj
    })
# -------------------------------------------------------------------
# VIEW: Handles "Delete Complaint" (teacher only)
@login_required
@user_passes_test(lambda u: u.is_staff)
def delete_complaint(request, complaint_id):
    complaint = get_object_or_404(Complaint, id=complaint_id)
    # Clean up physical storage files for attached images
    for img_field in (complaint.image1, complaint.image2, complaint.image3):
        if img_field:
            try:
                img_field.delete(save=False)
            except Exception:
                pass
    complaint.delete()
    messages.success(request, "Complaint deleted permanently.")
    return redirect('users:teacher_dashboard')
# -------------------------------------------------------------------


# API VIEW: Handles the "Put on Hold" request
@login_required
@transaction.atomic
def request_seat_hold_api(request):
    """
    STUDENT API: Request to put seat on hold
    RESTRICTIONS: 
    - Can only request after 3 days from today
    - Duration must be 15-90 days
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        profile = StudentProfile.objects.select_related('seat').get(user=request.user)
        seat = profile.seat

        if not seat:
            return JsonResponse({'status': 'error', 'message': 'You do not have an assigned seat.'}, status=400)

        # Lock seat row
        seat = Seat.objects.select_for_update().get(id=seat.id)

        data = json.loads(request.body or '{}')
        action = data.get('action')

        if action == 'cancel_pending':
            # Delete pending hold request
            deleted_count, _ = SeatHoldRequest.objects.filter(
                seat=seat, 
                student=profile, 
                status='pending'
            ).delete()
            
            if deleted_count > 0:
                if seat.hold_status == 'pending':
                    seat.hold_status = 'none'
                    seat.hold_request_date = None
                    seat.hold_request_duration = None
                    seat.save()
                return JsonResponse({'status': 'success', 'message': 'Hold request cancelled.'})
            return JsonResponse({'status': 'error', 'message': 'No pending request found.'}, status=404)

        if action == 'cancel_approved':
            hold_req = SeatHoldRequest.objects.filter(
                seat=seat,
                student=profile,
                status='approved'
            ).first()
            
            if not hold_req:
                return JsonResponse({'status': 'error', 'message': 'No approved hold request found.'}, status=404)
                
            hold_req.cancel_requested = True
            hold_req.save(update_fields=['cancel_requested'])
            
            from django.contrib.auth.models import User
            teachers = User.objects.filter(is_staff=True)
            for teacher in teachers:
                create_notification(
                    user=teacher,
                    title="Hold Cancellation Request",
                    message=f"{profile.full_name} requested to cancel their hold on Seat {seat.seat_number}.",
                    link="/teacher/dashboard/",
                    category="seat"
                )
                
            return JsonResponse({'status': 'success', 'message': 'Hold cancellation request sent to teacher.'})

        if action == 'request_end':
            if seat.hold_status != 'active':
                return JsonResponse({'status': 'error', 'message': 'No active hold.'}, status=400)
            
            # Create/Update SeatHoldRequest to make it visible in teacher dashboard
            hold_req, created = SeatHoldRequest.objects.get_or_create(
                seat=seat,
                status='approved',
                defaults={
                    'student': profile,
                    'start_date': seat.hold_start_date or timezone.now().date(),
                    'duration_text': 'Active Hold'
                }
            )
            hold_req.cancel_requested = True
            hold_req.save(update_fields=['cancel_requested'])
            
            # Notify teachers
            from django.contrib.auth.models import User
            teachers = User.objects.filter(is_staff=True)
            for teacher in teachers:
                create_notification(
                    user=teacher,
                    title="End Hold Request",
                    message=f"{profile.full_name} wants to end hold for Seat {seat.seat_number}.",
                    link=f"/teacher/dashboard/#holds",
                    category="seat"
                )
            return JsonResponse({'status': 'success', 'message': 'Request sent to teachers. They will review it on the dashboard.'})

        if action == 'cancel_scheduled_hold':
            # Student wants to cancel a teacher-scheduled future hold
            scheduled = SeatAssignment.objects.filter(
                student=profile,
                is_active=True,
                hold_status='none',
                hold_start_date__isnull=False,
                hold_start_date__gt=timezone.now().date(),
            ).first()

            if not scheduled:
                return JsonResponse({'status': 'error', 'message': 'No scheduled future hold found.'}, status=404)

            # Create/Update SeatHoldRequest to make it visible in teacher dashboard
            hold_req, created = SeatHoldRequest.objects.get_or_create(
                seat=seat,
                status='approved',
                defaults={
                    'student': profile,
                    'start_date': scheduled.hold_start_date,
                    'duration_text': f"Scheduled: {scheduled.hold_start_date.strftime('%d %b')} to {scheduled.hold_end_date.strftime('%d %b') if scheduled.hold_end_date else '?'}"
                }
            )
            hold_req.cancel_requested = True
            hold_req.save(update_fields=['cancel_requested'])

            # Notify teachers to review
            from django.contrib.auth.models import User
            teachers = User.objects.filter(is_staff=True)
            for teacher in teachers:
                create_notification(
                    user=teacher,
                    title="Scheduled Hold Cancellation Request",
                    message=(
                        f"{profile.full_name} has requested to cancel their scheduled hold "
                        f"on Seat {seat.seat_number} (scheduled from "
                        f"{scheduled.hold_start_date.strftime('%d %b %Y')} to "
                        f"{scheduled.hold_end_date.strftime('%d %b %Y') if scheduled.hold_end_date else '?'})."
                    ),
                    link=f"/teacher/dashboard/#holds",
                    category="seat"
                )

            # Also notify the student that their request was sent
            create_notification(
                user=profile.user,
                title="Cancellation Request Sent",
                message=(
                    f"Your request to cancel the scheduled hold on Seat {seat.seat_number} "
                    f"has been sent to the teacher for review."
                ),
                category="seat"
            )

            return JsonResponse({
                'status': 'success',
                'message': 'Cancellation request sent to teacher. It will appear on their dashboard for approval.'
            })

        # --- Default: New Hold Request ---

        # Must be occupied
        if seat.status != 'occupied':
            return JsonResponse({'status': 'error', 'message': 'Seat is not currently occupied.'}, status=400)

        # Student must be seat owner
        owner_assignment = SeatAssignment.objects.filter(
            seat=seat,
            student=profile,
            is_active=True
        ).first()

        if not owner_assignment:
            return JsonResponse({'status': 'error', 'message': 'You are not the owner of this seat.'}, status=403)

        # No existing pending request
        if SeatHoldRequest.objects.filter(seat=seat, status='pending').exists():
            return JsonResponse(
                {'status': 'error', 'message': 'A hold request is already pending for this seat.'},
                status=400
            )

        start_date_str = data.get('start_date')
        duration = (data.get('duration') or '').strip()

        if not start_date_str or not duration:
            return JsonResponse({'status': 'error', 'message': 'Missing data.'}, status=400)

        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except Exception:
            return JsonResponse({'status': 'error', 'message': 'Invalid date format.'}, status=400)

        # ===== STUDENT RESTRICTIONS =====
        today = timezone.now().date()
        if start_date < today + timedelta(days=3):
            return JsonResponse({'status': 'error', 'message': 'Must start at least 3 days from today.'}, status=400)

        # Validate duration (15–90 days)
        text = duration.lower()
        days = 0
        m = re.search(r'(\d+)\s*month', text)
        d = re.search(r'(\d+)\s*day', text)
        if m: days += int(m.group(1)) * 30
        if d: days += int(d.group(1))

        if days < 15 or days > 90:
            return JsonResponse({'status': 'error', 'message': 'Duration 15-90 days only.'}, status=400)

        # Create hold request
        SeatHoldRequest.objects.create(
            seat=seat, student=profile, start_date=start_date, duration_text=duration
        )

        # Update seat fields
        seat.hold_status = 'pending'
        seat.hold_request_date = timezone.now()
        seat.hold_request_duration = duration
        seat.save()

        # Notifications
        create_notification(
            user=profile.user, title="Hold Requested",
            message="Request sent for approval.", category="seat"
        )
        from django.contrib.auth.models import User
        for teacher in User.objects.filter(is_staff=True):
            create_notification(
                user=teacher, title="New Hold Request",
                message=f"{profile.full_name} - Seat {seat.seat_number}",
                link=f"/teacher/seat-manager/?floor={seat.floor}",
                category="seat"
            )

        return JsonResponse({'status': 'success', 'message': 'Submitted successfully.'})

    except StudentProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Profile not found.'}, status=404)

    except Exception as e:
        print("request_seat_hold_api error:", str(e))
        return JsonResponse({'status': 'error', 'message': f'Error: {str(e)}'}, status=500)
# -------------------------------------------------------------------

# VIEW: Renders the "Student Details S" page    
@login_required
def student_details_S_view(request):
    request.session['active_dashboard'] = 'student'
    student = get_object_or_404(StudentProfile.objects.select_related('seat'), user=request.user)
    return render(request, 'users/student_details_S.html', {
        'student': student,
        'password_date_display': _get_password_date_display(request),
    })


@login_required
@user_passes_test(lambda u: u.is_staff)
def teacher_dashboard_view(request):
    if not cache.get('holds_synced'):
        sync_active_holds()
        cache.set('holds_synced', True, 60 * 5)
    search_query = request.GET.get('q', '')
    service_filter = request.GET.get('service_filter', '')
    section_filter = request.GET.get('section_filter', '')
    
    admitted_students = StudentProfile.objects.filter(status='admitted').select_related('user')

    # Get achievement status for all users in one go
    admitted_user_ids = list(admitted_students.values_list('user_id', flat=True))
    achievement_user_ids = set(
        StudentAchievement.objects
        .filter(user_id__in=admitted_user_ids)
        .values_list('user_id', flat=True)
    )

    for s in admitted_students:
        s.has_achievement = s.user.id in achievement_user_ids

    # ---------------- Notifications ----------------
    from django.utils import timezone
    today = timezone.now().date()
    
    # Fetch notifications for current user
    all_notifs = Notification.objects.filter(user=request.user).order_by("-created_at")
    
    # Filter: Hide 'fee_teacher' notifications where expiry_date < today
    active_notifications = []
    unread_count = 0
    for n in all_notifs:
        if n.category == "fee_teacher" and n.meta and 'expiry_date' in n.meta:
            try:
                # meta['expiry_date'] is stored as ISO string (e.g., '2026-05-15')
                notif_expiry = datetime.date.fromisoformat(n.meta['expiry_date'])
                if notif_expiry < today:
                    continue # Skip expired fee alert
            except (ValueError, TypeError):
                pass
        
        active_notifications.append(n)
        if not n.is_read:
            unread_count += 1

    notifications = active_notifications[:15]


    # --- Notification Enrichment ---
    student_ids = []
    for n in notifications:
        if n.meta and 'student_id' in n.meta:
            student_ids.append(n.meta['student_id'])
    
    if student_ids:
        # Pre-fetch students to avoid N+1 queries
        students_map = {s.id: s for s in StudentProfile.objects.filter(id__in=student_ids).select_related('seat')}
        for n in notifications:
            if n.meta and 'student_id' in n.meta:
                st_obj = students_map.get(n.meta['student_id'])
                if st_obj:
                    st_photo_url = None
                    if st_obj.photo:
                        try:
                            st_photo_url = st_obj.photo.url
                        except (ValueError, AttributeError):
                            st_photo_url = None
                    st_obj.safe_photo_url = st_photo_url
                n.student_obj = st_obj



    # ---------------- Fee Expiry Tracking ----------------
    overdue_count = cache.get('overdue_students_count')
    if overdue_count is None:
        overdue_count = admitted_students.filter(
            fee_expiry_date__isnull=False,
            fee_expiry_date__lte=today
        ).count()
        cache.set('overdue_students_count', overdue_count, 30)

    overdue_students = admitted_students.filter(
        fee_expiry_date__isnull=False,
        fee_expiry_date__lte=today
    ).select_related('user', 'seat').order_by('fee_expiry_date')


    if search_query:
        admitted_students = admitted_students.filter(full_name__icontains=search_query)
    
    if service_filter:
        admitted_students = admitted_students.filter(service_type=service_filter)

    # Get pending admission requests (Only those NOT yet admitted OR having pending services, AND NOT manual pending)
    pending_students = StudentProfile.objects.filter(
        Q(status='pending') | Q(coaching_pending=True) | Q(library_pending=True)
    ).filter(
        is_manual_pending=False
    ).order_by('-id').select_related('seat', 'user').distinct()

    # Get achievement status for all pending users
    pending_user_ids = list(pending_students.values_list('user_id', flat=True))
    achievements_by_user = {
        ach.user_id: ach 
        for ach in StudentAchievement.objects.filter(user_id__in=pending_user_ids)
    }

    for s in pending_students:
        s.other_achievement = achievements_by_user.get(s.user.id)
        s.has_achievement = s.other_achievement is not None

    # Sync missing seat data for pending library requests (safety net)
    pending_no_seat = pending_students.filter(
        Q(service_type='Library') | Q(library_pending=True)
    ).filter(seat__isnull=True)
    if pending_no_seat.exists():
        assignments_by_student = {
            a.student_id: a
            for a in SeatAssignment.objects.filter(
                student__in=pending_no_seat,
                is_active=False
            ).select_related('seat')
        }
        special_by_student = {
            r.student_id: r
            for r in SeatSpecialRequest.objects.filter(
                student__in=pending_no_seat,
                status='pending'
            ).select_related('seat')
        }

        for student in pending_no_seat:
            assignment = assignments_by_student.get(student.id)
            special_request = special_by_student.get(student.id)
            seat_source = assignment.seat if assignment else (special_request.seat if special_request else None)
            shift_source = assignment.shift_type if assignment else (special_request.requested_shift if special_request else None)

            if seat_source:
                student.seat = seat_source
                if shift_source:
                    student.shift = shift_source
                student.save(update_fields=['seat', 'shift'])

        # Refresh pending_students queryset after sync
        pending_students = StudentProfile.objects.filter(
            Q(status='pending') | Q(coaching_pending=True) | Q(library_pending=True)
        ).filter(
            is_manual_pending=False
        ).order_by('-id').select_related('seat').distinct()

    # Split by service + admission_type
    pending_new_coaching_students = pending_students.filter(
        Q(service_type='Coaching', status='pending') | Q(coaching_pending=True)
    ).filter(
        admission_type='new',
    )
    pending_existing_coaching_students = pending_students.filter(
        Q(service_type='Coaching', status='pending') | Q(coaching_pending=True)
    ).filter(
        admission_type='existing',
    )
    # Exclude students who have a pending SeatSpecialRequest (Partial Allotment)
    # We want them to appear ONLY in the "Partial Seat Allotment Requests" section.
    partial_request_student_ids = SeatSpecialRequest.objects.filter(
        status='pending',
        student__isnull=False
    ).values_list('student_id', flat=True)

    pending_new_library_students = pending_students.filter(
        Q(service_type='Library', status='pending') | Q(library_pending=True)
    ).filter(
        admission_type='new',
    ).exclude(id__in=partial_request_student_ids)

    pending_existing_library_students = pending_students.filter(
        Q(service_type='Library', status='pending') | Q(library_pending=True)
    ).filter(
        admission_type='existing',
    ).exclude(id__in=partial_request_student_ids)

    # -------------------------------------------------
    # Pending HOLD requests (NEW SYSTEM)
    # -------------------------------------------------
    pending_hold_requests = SeatHoldRequest.objects.filter(
        status='pending'
    ).select_related(
        'seat',
        'student'
    ).order_by('created_at')

    # Cancel/End Hold requests (approved holds where student requested cancellation)
    cancel_hold_requests = SeatHoldRequest.objects.filter(
        status='approved',
        cancel_requested=True
    ).select_related(
        'seat',
        'student'
    ).order_by('created_at')

    # -------------------------------------------------
    # Pending Partial / Special Seat Requests
    # -------------------------------------------------
    pending_partial_requests = SeatSpecialRequest.objects.filter(
        status='pending'
    ).select_related(
        'student',
        'seat',
        'user'
    ).order_by('-created_at')

    pending_achievements = StudentAchievement.objects.filter(
        status='pending'
    ).select_related('user').order_by('-created_at')

    # Fetch pending seat switch requests
    seat_switch_requests = SeatSwitchRequest.objects.filter(
        status='pending'
    ).select_related('student', 'student__user', 'target_seat').order_by('-created_at')

    # Enrich achievements with student profile
    profiles_by_user = {
        p.user_id: p 
        for p in StudentProfile.objects.filter(
            user__in=[a.user for a in pending_achievements]
        ).select_related('seat')
    }

    for a in pending_achievements:
        a.other_profile = profiles_by_user.get(a.user_id)
        a.has_profile = a.other_profile is not None

    # Enrich partial requests with hold metadata for frontend alerts
    today = timezone.now().date()
    for req in pending_partial_requests:
        seat = req.seat
        
        # Determine strict shift mode
        is_shift_seat = (seat.floor == 'Ground Floor' and 40 <= int(seat.seat_number) <= 53)
        seat.is_shift_enabled = is_shift_seat

        req.hold_remaining_days = 0
        req.hold_end_date = None
        req.holder_name = "Unknown"
        req.morning_holder_name = ""
        req.evening_holder_name = ""
        req.full_day_hold_remaining_days = 0
        req.morning_hold_remaining_days = 0
        req.evening_hold_remaining_days = 0

        # Fetch active hold assignments (owners)
        hold_assignments = seat.assignments.filter(
            is_active=True, 
            hold_status='active', 
            is_partial=False
        ).select_related('student')

        if not is_shift_seat:
            # Case 1: Non-shift seat
            assignment = hold_assignments.first()
            if assignment and assignment.hold_end_date:
                req.hold_end_date = assignment.hold_end_date
                req.hold_remaining_days = max((assignment.hold_end_date - today).days, 0)
                req.holder_name = assignment.student.full_name
        else:
            # Shift seat logic
            # We need to look at what shift is requested vs what is on hold
            req_shift = req.requested_shift # morning, evening, full

            # Get specific owners
            morning_owner = hold_assignments.filter(shift_type='morning').first()
            evening_owner = hold_assignments.filter(shift_type='evening').first()
            full_owner = hold_assignments.filter(shift_type='full').first()

            # Helper to calculate days
            def get_days(d): return max((d - today).days, 0) if d else 0

            if full_owner:
                req.full_day_hold_remaining_days = get_days(full_owner.hold_end_date)
                req.hold_end_date = full_owner.hold_end_date
                req.holder_name = full_owner.student.full_name
                req.hold_remaining_days = req.full_day_hold_remaining_days
            
            else:
                if morning_owner:
                    req.morning_hold_remaining_days = get_days(morning_owner.hold_end_date)
                    req.morning_holder_name = morning_owner.student.full_name
                
                if evening_owner:
                    req.evening_hold_remaining_days = get_days(evening_owner.hold_end_date)
                    req.evening_holder_name = evening_owner.student.full_name

                # Determine relevant hold based on request
                if req_shift == 'morning' and morning_owner:
                    req.hold_remaining_days = req.morning_hold_remaining_days
                    req.hold_end_date = morning_owner.hold_end_date
                    req.holder_name = morning_owner.student.full_name
                
                elif req_shift == 'evening' and evening_owner:
                    req.hold_remaining_days = req.evening_hold_remaining_days
                    req.hold_end_date = evening_owner.hold_end_date
                    req.holder_name = evening_owner.student.full_name
                
                elif req_shift == 'full':
                    # Hybrid case: both might be on hold
                    dates = []
                    
                    if morning_owner: 
                        dates.append(morning_owner.hold_end_date)
                        req.holder_name = morning_owner.student.full_name # fallback if needed
                    if evening_owner: 
                        dates.append(evening_owner.hold_end_date)
                        # evening_holder_name is already set
                    
                    if dates:
                        earliest = min(dates)
                        req.hold_end_date = earliest
                        req.hold_remaining_days = get_days(earliest)
                        # We don't join names here anymore, frontend handles it via data attrs

    # ---- Notification counts ----
    total_admission_requests = pending_students.count()
    total_hold_requests = pending_hold_requests.count() + cancel_hold_requests.count()
    total_pending_achievements = pending_achievements.count()

    # ---- Calculate New Requests for Auto-dismissing Banner ----
    current_admission_ids = list(pending_students.values_list('id', flat=True))
    current_achievement_ids = list(pending_achievements.values_list('id', flat=True))
    current_hold_ids = list(pending_hold_requests.values_list('id', flat=True)) + list(cancel_hold_requests.values_list('id', flat=True))

    seen_admission_ids = request.session.get('seen_admission_ids', [])
    seen_achievement_ids = request.session.get('seen_achievement_ids', [])
    seen_hold_ids = request.session.get('seen_hold_ids', [])

    new_admissions = [i for i in current_admission_ids if i not in seen_admission_ids]
    new_achievements = [i for i in current_achievement_ids if i not in seen_achievement_ids]
    new_holds = [i for i in current_hold_ids if i not in seen_hold_ids]

    new_requests_alert = ""
    if new_admissions or new_achievements or new_holds:
        parts = []
        if new_admissions:
            parts.append(f"<strong>{len(new_admissions)}</strong> new Admission request{'s' if len(new_admissions) > 1 else ''}")
        if new_achievements:
            parts.append(f"<strong>{len(new_achievements)}</strong> new Achievement request{'s' if len(new_achievements) > 1 else ''}")
        if new_holds:
            parts.append(f"<strong>{len(new_holds)}</strong> new Hold request{'s' if len(new_holds) > 1 else ''}")
        new_requests_alert = ", ".join(parts) + "."

    # Update session seen lists
    request.session['seen_admission_ids'] = current_admission_ids
    request.session['seen_achievement_ids'] = current_achievement_ids
    request.session['seen_hold_ids'] = current_hold_ids

    # --- Complaints ---
    active_complaints = Complaint.objects.exclude(
        status=Complaint.STATUS_RESOLVED
    ).select_related("student", "student__user").order_by('-created_at')

    resolved_complaints = Complaint.objects.filter(
        status=Complaint.STATUS_RESOLVED
    ).select_related("student", "student__user").order_by('-updated_at')
    
    for c in resolved_complaints:
        c.resolved_in = timesince(c.created_at, c.updated_at)

    pending_complaints_count = active_complaints.count()

    total_notification_count = (
        total_admission_requests
        + total_hold_requests
        + pending_partial_requests.count()
        + pending_complaints_count
        + total_pending_achievements
        + overdue_count
    )


    # Group admitted students by service type
    coaching_batches = defaultdict(list)
    library_floors = defaultdict(list)

    # All admitted library students (with their seat & user)
    library_students_all = admitted_students.filter(
        service_type__in=['Library', 'Both']
    ).select_related('seat', 'user')

    # HOLD students = Any library student with status 'on_hold' OR admitted students whose seat is on hold
    hold_assignment_students = SeatAssignment.objects.filter(
        is_active=True,
        hold_status='active',
        is_partial=False
    ).values('student_id')

    hold_library_students = StudentProfile.objects.filter(
        service_type__in=['Library', 'Both']
    ).filter(
        models.Q(status='on_hold') |
        models.Q(status='admitted', seat__isnull=False, seat__status='on_hold') |
        models.Q(status='admitted', id__in=hold_assignment_students)
    ).select_related('seat', 'user').distinct()

    # NORMAL library students = all library students EXCEPT the hold ones
    normal_library_students = library_students_all.exclude(
        id__in=hold_library_students.values('id')
    )

    # Pending library students (Exclusively those manually set to pending by teacher)
    pending_library_students = StudentProfile.objects.filter(
        service_type__in=['Library', 'Both'],
        status='pending',
        is_manual_pending=True
    ).select_related('seat', 'user')
    
    # Students on hold (library)
    on_hold_library_students = StudentProfile.objects.filter(
        status='on_hold',
        service_type__in=['Library', 'Both']
    ).select_related('seat', 'user')

    # NO-SEAT library students (approved without seat)
    # These are admitted Library students who do not currently have a seat assigned.
    no_seat_library_students = admitted_students.filter(
        service_type__in=['Library', 'Both'],
        seat__isnull=True,
    ).select_related('user')

    # Coaching batches
    for student in admitted_students.filter(service_type__in=['Coaching', 'Both']):
        coaching_batches[student.batch].append(student)

    # Sort batches alphabetically (handling None safely)
    sorted_coaching_batches = dict(sorted(coaching_batches.items(), key=lambda item: (item[0] is None, str(item[0] or ''))))
    coaching_batches = defaultdict(list, sorted_coaching_batches)

    # PARTIAL / TEMPORARY students = admitted Library students
    # whose active SeatAssignment has is_partial=True (they are tenants, not owners)
    partial_assignments = SeatAssignment.objects.filter(
        is_active=True,
        is_partial=True,
        student__service_type__in=['Library', 'Both'],
        student__status='admitted'
    ).select_related('student', 'student__user', 'student__seat', 'seat')

    partial_student_ids = partial_assignments.values_list('student_id', flat=True)

    # Build partial student list with temp seat/shift annotated
    partial_library_students = []
    for assignment in partial_assignments:
        student = assignment.student
        student.temp_seat = assignment.seat          # The seat they TEMP-occupy
        student.temp_shift = assignment.shift_type   # The shift they TEMP-occupy
        student.temp_hold_end = assignment.hold_end_date
        partial_library_students.append(student)

    # NORMAL library students = all library students EXCEPT hold AND partial ones
    normal_library_students = normal_library_students.exclude(
        id__in=partial_student_ids
    )

    # Group NORMAL library students by floor
    # Skip students with no seat — they appear in no_seat_library_students section
    # Auto-healing: Ensure stale seat pointers are cleared if another student holds the active assignment
    for student in normal_library_students:
        seat = getattr(student, 'seat', None)
        if not seat:
            continue

        if not seat.is_shift_enabled:
            has_active_assignment = SeatAssignment.objects.filter(
                seat=seat, student=student, is_active=True
            ).exists()
            if not has_active_assignment:
                other_active_exists = SeatAssignment.objects.filter(
                    seat=seat, is_active=True
                ).exclude(student=student).exists()
                if other_active_exists:
                    student.seat = None
                    student.save(update_fields=['seat'])
                    continue

        floor_name = seat.floor
        library_floors[floor_name].append(student)

    context = {
        'pending_students': pending_students,
        'pending_new_coaching_students': pending_new_coaching_students,
        'pending_existing_coaching_students': pending_existing_coaching_students,
        'pending_new_library_students': pending_new_library_students,
        'pending_existing_library_students': pending_existing_library_students,

        'pending_hold_requests': pending_hold_requests,
        'cancel_hold_requests': cancel_hold_requests,
        'pending_partial_requests': pending_partial_requests,
        'seat_switch_requests': seat_switch_requests,

        'admitted_students': admitted_students,
        'coaching_students_by_batch': dict(coaching_batches),
        'library_students_by_floor': dict(library_floors),
        'hold_library_students': hold_library_students,
        'pending_library_students': pending_library_students,
        'on_hold_library_students': on_hold_library_students,
        'no_seat_library_students': no_seat_library_students,
        'partial_library_students': partial_library_students,

        'search_query': search_query,
        'service_filter': service_filter,
        'section_filter': section_filter,

        'total_coaching_students': StudentProfile.objects.filter(
            status='admitted', service_type__in=['Coaching', 'Both']
        ).count(),

        'total_library_students': StudentProfile.objects.filter(
            status='admitted', service_type__in=['Library', 'Both']
        ).count(),

        'total_admission_requests': total_admission_requests,
        'total_hold_requests': total_hold_requests,
        'pending_achievements': pending_achievements,
        'total_pending_achievements': total_pending_achievements,

        "active_complaints": active_complaints,
        "resolved_complaints": resolved_complaints,
        "pending_complaints_count": pending_complaints_count,

        'total_notification_count': total_notification_count,
        "notifications": notifications,
        'show_teacher_filter_dropdown': True,
        "unread_count": unread_count,
        "overdue_students": overdue_students,
        "today": today,
        'total_courses': Course.objects.count(),
        'total_admitted_students_count': StudentProfile.objects.filter(status__in=['admitted', 'on_hold']).count(),
        'new_requests_alert': new_requests_alert,
    }


    return render(request, 'users/teacher_dashboard.html', context)

# -------------------------------------------------------------------
# VIEW: teacher- "Visitor Insights" page
@login_required
@user_passes_test(lambda u: u.is_staff)
def visitor_insights_view(request):
    intents = VisitorIntent.objects.select_related("user").order_by("-created_at")
    return render(
        request,
        "users/visitor_insights.html",
        {"intents": intents}
    )

# -------------------------------------------------------------------
# VIEW: teacher- "Clear Old Visitor Records" action
@login_required
@user_passes_test(lambda u: u.is_staff)
@require_POST
def clear_visitor_intents(request):
    VisitorIntent.objects.filter(
        Q(reminder_sent=True) | Q(resolved=True)
    ).delete()

    messages.success(request, "Old visitor records cleared successfully.")
    return redirect("users:visitor_insights")

# -------------------------------------------------------------------
# VIEW: Teacher - Delete Selected Visitor Intents
@login_required
@user_passes_test(lambda u: u.is_staff)
@require_POST
def delete_selected_visitor_intents(request):
    intent_ids = request.POST.getlist('intent_ids[]')
    if not intent_ids:
        messages.warning(request, "No visitor records selected for deletion.")
        return redirect("users:visitor_insights")
        
    try:
        with transaction.atomic():
            count = VisitorIntent.objects.filter(id__in=intent_ids).delete()[0]
            messages.success(request, f"Successfully deleted {count} visitor record(s).")
    except Exception as e:
        messages.error(request, f"Error deleting records: {str(e)}")
        
    return redirect("users:visitor_insights")

# -------------------------------------------------------------------
# VIEW: Teacher - "Fees Record" accounting history
@login_required
@user_passes_test(lambda u: u.is_staff)
def fees_record_view(request):
    search_query = request.GET.get('search', '').strip()
    
    # Optimized queryset
    transactions = FeeTransaction.objects.select_related('student').order_by('-created_at')
    
    if search_query:
        query_filter = (
            Q(receipt_number__icontains=search_query) |
            Q(student__full_name__icontains=search_query) |
            Q(student__mobile_number__icontains=search_query)
        )
        try:
            from datetime import datetime
            parsed_date = datetime.strptime(search_query, '%Y-%m-%d').date()
            query_filter |= Q(payment_date=parsed_date)
        except (ValueError, TypeError):
            pass
        transactions = transactions.filter(query_filter)
    
    # Pagination: 20 per page
    paginator = Paginator(transactions, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    return render(request, 'users/fees_record.html', {
        'page_obj': page_obj,
        'search_query': search_query,
    })

# -------------------------------------------------------------------
# VIEW: Teacher - Bulk Delete Fee Transactions
@login_required
@user_passes_test(lambda u: u.is_staff)
@require_POST
def bulk_delete_fees_action(request):
    transaction_ids = request.POST.getlist('transaction_ids[]')
    
    if not transaction_ids:
        messages.warning(request, "No records selected for deletion.")
        return redirect("users:fees_record")
        
    try:
        with transaction.atomic():
            count = FeeTransaction.objects.filter(id__in=transaction_ids).delete()[0]
            messages.success(request, f"Successfully deleted {count} fee record(s).")
    except Exception as e:
        messages.error(request, f"Error deleting records: {str(e)}")
        
    return redirect("users:fees_record")

# -------------------------------------------------------------------
# VIEW: Teacher - Download Fee Receipt PDF
@login_required
@user_passes_test(lambda u: u.is_staff)
def download_fee_receipt_view(request, transaction_id):
    import logging
    from django.http import HttpResponse, JsonResponse
    logger = logging.getLogger(__name__)
    try:
        from users.models import FeeTransaction
        from users.utils.receipt_generator import generate_fee_receipt_pdf
        
        transaction_obj = get_object_or_404(FeeTransaction.objects.select_related('student'), id=transaction_id)
        pdf_buffer = generate_fee_receipt_pdf(transaction_obj)
        
        response = HttpResponse(pdf_buffer.getvalue(), content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Fee_Receipt_{transaction_obj.receipt_number}.pdf"'
        return response
    except Exception as e:
        logger.exception(f"Error in download_fee_receipt_view for transaction {transaction_id}: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)





# -------------------------------------------------------------------
# VIEW: Renders the Teacher's "Seat Status" page
@login_required
@user_passes_test(lambda u: u.is_staff)
def teacher_seat_status_view(request):
    """
    Renders the main seat management page for teachers.
    The page will be loaded empty, and JavaScript will
    fetch the seat data from the API.
    """
    return render(request, 'users/teacher_seat_status.html')

# -------------------------------------------------------------------
# API VIEW: Teacher API for seat status (includes student names)
@login_required
@user_passes_test(lambda u: u.is_staff)
def get_teacher_seat_status_api(request):
    floor = request.GET.get('floor')
    if not floor:
        return JsonResponse({'error': 'Floor parameter is required'}, status=400)

    # Prefetch relevant data to avoid N+1 queries
    seats = Seat.objects.filter(floor=floor).prefetch_related(
        'assignments',
        'assignments__student',
        'special_requests',
        'special_requests__student',
        'special_requests__user',
    )

    today = timezone.now().date()
    seat_data = []

    for seat in seats:
        # --- ENFORCE STRICT SHIFT DEFINITION ---
        if seat.floor == 'Ground Floor' and 40 <= int(seat.seat_number) <= 53:
            seat.is_shift_enabled = True
        else:
            seat.is_shift_enabled = False
        # ---------------------------------------
        # Get ALL assignments (active + pending)
        assignments_qs = list(seat.assignments.all())
        active_assignments = [a for a in assignments_qs if a.is_active]
        # Only consider it a pending request if the student is actually still seeking admission for THIS exact seat
        pending_assignments = [
            a for a in assignments_qs 
            if not a.is_active and a.student.status == 'pending' and a.student.seat_id == seat.id
        ]

        # --- 1. GROUP BY SHIFT (ACTIVE ONLY) ---
        # We might have 2 people on Morning (Owner-on-Hold + Tenant)
        assignments_map = {
            'morning': [],
            'evening': [],
            'full': []
        }

        for a in active_assignments:
            shift_key = a.shift_type if a.shift_type in ['morning', 'evening', 'full'] else 'full'
            assignments_map[shift_key].append(a)

        # --- 2. CALCULATE STATUS & LABELS ---
        names = []
        student_ids = []
        visual_data = []  # Detailed list for the frontend to render rows

        # Helper to process a specific assignment
        def process_assignment(a, is_pending=False):
            s = a.student

            # Label Construction
            # e.g., "Vikas (M - Hold)" or "Syam (M - PT)"
            badges = []

            # Shift Badge
            if a.shift_type == 'morning':
                badges.append("M")
            elif a.shift_type == 'evening':
                badges.append("E")
            elif a.shift_type == 'full':
                badges.append("Full")

            # Status Badge
            if is_pending:
                badges.append("Pending")
            elif a.is_partial:
                badges.append("PT")  # Partial Tenant
            elif a.hold_status == 'active':
                # Calculate days remaining for this specific shift hold
                days = 0
                if a.hold_end_date:
                    days = max((a.hold_end_date - today).days, 0)
                badges.append(f"Hold({days})")
            elif s.status == 'pending':
                badges.append("Pending")

            label = " • ".join(badges)
            full_label = f"{s.full_name} ({label})" if label else s.full_name
            if not is_pending:
                names.append(full_label)
                student_ids.append(s.id)

            photo_url = None
            if s.photo:
                try:
                    photo_url = s.photo.url
                except (ValueError, AttributeError):
                    photo_url = None

            return {
                "student_id": s.id,
                "student_name": s.full_name,
                "student_status": s.status,
                "shift": a.shift_type or 'full',
                "is_partial": a.is_partial,
                "hold_status": a.hold_status,
                "hold_days": max((a.hold_end_date - today).days + 1, 0) if a.hold_end_date else 0,
                "hold_start_date": a.hold_start_date.isoformat() if a.hold_start_date else None,
                "hold_end_date": a.hold_end_date.isoformat() if a.hold_end_date else None,
                "is_pending": is_pending,
                "is_active": not is_pending,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "photo_url": photo_url
            }

        # Process assignments to build the name list and modal data
        for a in active_assignments:
            visual_data.append(process_assignment(a, is_pending=False))
        for a in pending_assignments:
            visual_data.append(process_assignment(a, is_pending=True))

        # --- PROCESS PENDING SPECIAL REQUESTS (Temporary/Partial) ---
        pending_specials = seat.special_requests.filter(status='pending')
        special_req_pending = False
        
        for req in pending_specials:
            special_req_pending = True
            s = req.student
            user = req.user
            
            s_name = s.full_name if s else (user.username if user else "Unknown")
            s_id = s.id if s else None
            s_status = s.status if s else 'pending'
            
            # Construct a visual object compatible with the frontend
            visual_data.append({
                "student_id": s_id,
                "student_name": s_name,
                "student_status": s_status,
                "shift": req.requested_shift,
                "is_partial": True,           # Triggers pink visual logic
                "hold_status": 'none',
                "hold_days": 0,
                "is_pending": True,
                "is_active": False,
                "created_at": req.created_at.isoformat(),
                "request_id": req.id,
                "is_special_request": True
            })

        # --- 3. DERIVE SEAT STATUS (For coloring) ---
        derived_status = seat.status  # Start with DB status

        has_full = bool(assignments_map['full']) or (not seat.is_shift_enabled and bool(active_assignments))
        has_morning = bool(assignments_map['morning'])
        has_evening = bool(assignments_map['evening'])
        has_active = bool(active_assignments)
        has_pending = bool(pending_assignments) or special_req_pending

        has_assignment_hold = any(a.hold_status == 'active' for a in active_assignments)

        # Refine status based on actual content and strict hierarchy:
        # 1. On Hold
        # 2. Occupied (Any active approved student)
        # 3. Pending (No active approved student, but has pending admission request)
        # 4. Available (No active student and no pending requests)
        if seat.status == 'on_hold' or has_assignment_hold:
            derived_status = 'on_hold'
        elif has_active or has_full or (has_morning and has_evening):
            derived_status = 'occupied'
        elif has_pending:
            derived_status = 'pending'
        else:
            derived_status = 'available'

        # Seat-level / assignment-level Hold Remaining Days
        seat_remaining_days = None
        hold_days = []
        if seat.status == 'on_hold' and seat.hold_end_date:
            hold_days.append(max((seat.hold_end_date - today).days + 1, 0))

        for assignment in active_assignments:
            if assignment.hold_status == 'active' and assignment.hold_end_date:
                hold_days.append(max((assignment.hold_end_date - today).days + 1, 0))

        if hold_days:
            seat_remaining_days = min(hold_days)

        # --- 4. CONSTRUCT RESPONSE ---
        seat_data.append({
            'id': seat.id,
            'seat_number': seat.seat_number,
            'floor': seat.floor,
            'status': derived_status, # visual color class
            'student_name': ", ".join(names) if names else None,
            'student_first_names': ", ".join([name.split()[0] for name in names]) if names else None,
            'student_ids': student_ids,
            'is_shift_enabled': seat.is_shift_enabled,
            
            # Occupancy Flags
            'morning_taken': has_morning,
            'evening_taken': has_evening,
            'full_day_taken': has_full,
            
            # Days remaining (Seat Level)
            'remaining_days': seat_remaining_days,
            
            # Detailed Assignments for Modal/Tooltip
            'assignments': visual_data,
            
            # Lock Flags
            'is_locked': seat.is_locked,
            'locked_shifts': seat.locked_shifts or '',
            
            # Permission Flags for Context Menu
            'can_request_partial': (
                seat.status == 'on_hold' or 
                any(a.hold_status == 'active' for a in active_assignments)
            ),
            'available_shifts': {
                'morning': not has_morning and not has_full and 'morning' not in (seat.locked_shifts or '').split(','),
                'evening': not has_evening and not has_full and 'evening' not in (seat.locked_shifts or '').split(','),
            }
        })

    return JsonResponse({'seats': seat_data})


# -------------------------------------------------------------------
# API VIEW: Toggle Lock Seat / Lock Shift (Staff Only)
# -------------------------------------------------------------------
@login_required
@user_passes_test(lambda u: u.is_staff)
def toggle_seat_lock_api(request):
    """
    API endpoint for locking or unlocking a seat or shift.
    Only available/free seats or shifts can be locked.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        data = json.loads(request.body or '{}')
        seat_id = data.get('seat_id')
        floor = data.get('floor')
        seat_number = str(data.get('seat_number') or '').strip()
        action = data.get('action') # 'lock' or 'unlock'
        shift = data.get('shift', 'full') # 'morning', 'evening', 'full'

        seat = None
        if seat_id and str(seat_id).isdigit():
            seat = Seat.objects.filter(id=int(seat_id)).first()

        if not seat and floor and seat_number:
            seat = Seat.objects.filter(floor=floor, seat_number=seat_number).first()


        if not seat:
            return JsonResponse({'status': 'error', 'message': 'Seat not found.'}, status=404)

        if action == 'lock':
            # Validation: ONLY FREE/AVAILABLE SEATS OR SHIFTS CAN BE LOCKED!
            active_assigns = seat.assignments.filter(is_active=True)
            if shift == 'full':
                if active_assigns.exists() or seat.status == 'occupied':
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Only available/free seats can be locked. This seat is currently occupied or on hold.'
                    }, status=400)
                seat.is_locked = True
                seat.locked_shifts = 'full'
            else:
                shift_taken = active_assigns.filter(shift_type__in=[shift, 'full']).exists()
                if shift_taken:
                    return JsonResponse({
                        'status': 'error',
                        'message': f'Only available/free shifts can be locked. The {shift.capitalize()} shift is currently occupied.'
                    }, status=400)
                current_locked = [s for s in (seat.locked_shifts or '').split(',') if s and s != 'full']
                if shift not in current_locked:
                    current_locked.append(shift)
                seat.locked_shifts = ','.join(current_locked)
                if 'morning' in current_locked and 'evening' in current_locked:
                    seat.is_locked = True

            seat.save()
            return JsonResponse({
                'status': 'success',
                'message': f'Seat {seat.seat_number} ({shift.capitalize()}) has been locked successfully.',
                'is_locked': seat.is_locked,
                'locked_shifts': seat.locked_shifts
            })

        elif action == 'unlock':
            if shift == 'full':
                seat.is_locked = False
                seat.locked_shifts = ''
            else:
                current_locked = [s for s in (seat.locked_shifts or '').split(',') if s and s != shift and s != 'full']
                seat.locked_shifts = ','.join(current_locked)
                seat.is_locked = False

            seat.save()
            return JsonResponse({
                'status': 'success',
                'message': f'Seat {seat.seat_number} ({shift.capitalize()}) has been unlocked.',
                'is_locked': seat.is_locked,
                'locked_shifts': seat.locked_shifts
            })

        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid action specified.'}, status=400)

    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# -------------------------------------------------------------------
# API VIEW: Gets list of students to assign to seats
# paste/replace in /mnt/data/views.py (update existing get_student_list_api)
@login_required
@user_passes_test(lambda u: u.is_staff)
def get_student_list_api(request):
    """
    Returns a list of admitted students filtered by type.
    Accepts GET param 'type' which can be:
      - 'library' (default) : admitted library/both students
      - 'coaching'          : admitted coaching/both students
      - 'alumni'            : approved alumni (mapped to profiles or users)
      - 'all'               : all admitted students
    """
    stype = request.GET.get('type', 'library').lower()
    try:
        from users.models import StudentProfile, StudentAchievement
        from django.contrib.auth.models import User as DjangoUser

        student_data = []

        if stype == 'alumni':
            alumni_list = StudentAchievement.objects.filter(status='approved').select_related('user')
            for al in alumni_list:
                # Find if they have a student profile
                profile = StudentProfile.objects.filter(user=al.user).first()
                
                # Check for active assignment specific status (Hold Owner vs Tenant)
                is_tenant = False
                is_hold_owner = False
                if profile:
                    active_assign = profile.seat_assignments.filter(is_active=True).first()
                    if active_assign:
                        is_tenant = active_assign.is_partial
                        is_hold_owner = (active_assign.hold_status == 'active')

                student_data.append({
                    'id': profile.id if profile else f"user_{al.user.id}",
                    'user_id': al.user.id,
                    'full_name': al.full_name,
                    'service_type': profile.service_type if profile else 'Alumni',
                    'seat_id': profile.seat.id if (profile and profile.seat) else None,
                    'seat_number': profile.seat.seat_number if (profile and profile.seat) else None,
                    'floor': profile.seat.floor if (profile and profile.seat) else None,
                    'is_hold_owner': is_hold_owner,
                    'is_tenant': is_tenant,
                    'has_alumni': True,
                    'has_coaching': profile.service_type in ['Coaching', 'Both'] if profile else False
                })
        else:
            qs = StudentProfile.objects.filter(status='admitted')
            if stype == 'library':
                qs = qs.filter(service_type__in=['Library', 'Both'])
            elif stype == 'coaching':
                qs = qs.filter(service_type__in=['Coaching', 'Both'])
            elif stype != 'all':
                return JsonResponse({'students': []})

            students = qs.select_related('seat', 'user').order_by('full_name')
            for student in students:
                seat_obj = getattr(student, 'seat', None)
                has_alumni = StudentAchievement.objects.filter(user=student.user, status='approved').exists()
                
                is_tenant = False
                is_hold_owner = False
                active_assign = student.seat_assignments.filter(is_active=True).first()
                if active_assign:
                    is_tenant = active_assign.is_partial
                    is_hold_owner = (active_assign.hold_status == 'active')

                student_data.append({
                    'id': student.id,
                    'user_id': student.user.id,
                    'full_name': student.full_name,
                    'service_type': student.service_type,
                    'seat_id': seat_obj.id if seat_obj else None,
                    'seat_number': seat_obj.seat_number if seat_obj else None,
                    'floor': seat_obj.floor if seat_obj else None,
                    'is_hold_owner': is_hold_owner,
                    'is_tenant': is_tenant,
                    'has_alumni': has_alumni,
                    'has_coaching': student.service_type in ['Coaching', 'Both']
                })

        return JsonResponse({'students': student_data})
    except Exception as e:
        print("get_student_list_api error:", str(e))
        return JsonResponse({'students': []})


# -------------------------------------------------------------------
# API VIEW: Handles ALL Teacher seat modifications
# -------------------------------------------------------------------

@login_required
@user_passes_test(lambda u: u.is_staff)
def seat_action_api(request):
    """
    API endpoint for seat actions (allot, free, approve, etc.)
    
    Protected against database lock errors with automatic retry.
    Uses safe_db_operation decorator pattern internally.
    """
    from users.db_utils import retry_on_db_lock
    from django.db import transaction
    from django.core.cache import cache
    
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    # Deduplication: Prevent rapid duplicate requests
    try:
        body_preview = request.body.decode('utf-8', errors='ignore')[:200]
    except:
        body_preview = ''
    
    import hashlib
    request_hash = hashlib.sha256(f'{request.user.id}:{body_preview}'.encode()).hexdigest()[:16]
    cache_key = f'seat_action_{request_hash}'
    
    if cache.get(cache_key):
        return JsonResponse({
            'status': 'duplicate',
            'message': 'This action is already being processed. Please wait.',
            'code': 'DUPLICATE_REQUEST'
        }, status=429)
    
    # Lock for 5 seconds to prevent duplicates
    cache.set(cache_key, True, 5)

    try:
        data = json.loads(request.body or '{}')
        floor = data.get('floor')
        seat_number = str(data.get('seat_number') or '').strip()
        action = data.get('action')
        student_id = data.get('student_id')
        reassign = data.get('confirm_reassign', False)
        payload = data.get('payload', {})
        # Force flag allows teacher to bypass ALL conflict checks
        force = payload.get('force', False) or data.get('force', False)

        # Basic validation
        if not floor or not seat_number or not action:
            return JsonResponse(
                {'status': 'error',
                'message': 'floor, seat_number and action are required.'},
                status=400
            )

        # Execute within atomic transaction - with retry on database lock
        @retry_on_db_lock(max_retries=5, initial_delay=0.1)
        def execute_seat_action():
            with transaction.atomic():
                # Lock the row to prevent race conditions
                seat, created = Seat.objects.select_for_update().get_or_create(
                    floor=floor, 
                    seat_number=seat_number,
                    defaults={'status': 'available'}
                )
                return seat, created

        try:
            seat, created = execute_seat_action()
        except OperationalError as e:
            if 'database is locked' in str(e).lower():
                return JsonResponse({
                    'status': 'error',
                    'message': 'Server is busy. Please try again in a moment.',
                    'code': 'DATABASE_BUSY'
                }, status=503)
            raise
        
        def success_response(message):
            return JsonResponse({'status': 'success', 'message': message})
        
        # STRICT LOCK GUARD: Cannot assign/allot a locked seat or locked shift!
        if action != 'free':
            target_shift = payload.get('shift', 'full') if isinstance(payload, dict) else 'full'
            locked_list = [s for s in (seat.locked_shifts or '').split(',') if s]
            if seat.is_locked or 'full' in locked_list or target_shift in locked_list:
                return JsonResponse({
                    'status': 'error',
                    'message': '🔒 This seat/shift is locked by the Librarian. You cannot assign it until it is unlocked by the Librarian.'
                }, status=400)

        # ------------------------------------
        # 1. ACTION: FREE THIS SEAT
        # ------------------------------------

        if action == 'free':
            if student_id:
                # SPECIFIC FREEDOM: Only deactivate the selected student.
                # If they are owner, temporary tenant stays.
                assignments = SeatAssignment.objects.filter(seat=seat, is_active=True, student_id=student_id)
                if not assignments.exists():
                     return JsonResponse({'status': 'error', 'message': 'Student assignment not found on this seat.'}, status=404)
                
                count = assignments.count()
                for a in assignments:
                     a.deactivate()
                     try:
                         notifications.send_seat_rejection_email(a.student, seat, a.shift_type)
                     except Exception:
                         pass
                     
                seat.recalc_status(save=True)

                # NEW SAFEGUARD: If we just removed a partial tenant, ensure ANY remaining active owners who are on hold STAY on hold
                # This fixes an edge case where recalc_status or sync_student_pointer might unintentionally set status to occupied.
                active_owners = SeatAssignment.objects.filter(seat=seat, is_active=True, is_partial=False)
                for owner in active_owners:
                    if owner.hold_status == 'active':
                        # Force update the student and seat status back to hold, just to be absolutely sure
                        owner.student.status = 'on_hold'
                        owner.student.save(update_fields=['status'])
                        seat.status = 'on_hold'
                        seat.save(update_fields=['status'])

                return success_response(f"Removed student from seat. {count} assignment(s) deactivated.")
            else:
                # If no student_id provided, free the entire seat (Fallback to original logic)
                # SAFETY CHECK: If there are PARTIAL tenants (e.g. temporary), we only remove THEM.
                # We do NOT remove the Owner-On-Hold.
                # UNLESS 'force' is True (Nuclear Option).
                
                if not force:
                    partial_assignments = SeatAssignment.objects.filter(seat=seat, is_active=True, is_partial=True)
                    
                    # The student_id check here is redundant if we're in the 'else' block for student_id
                    # if student_id:
                    #     partial_assignments = partial_assignments.filter(student_id=student_id)

                    if partial_assignments.exists():
                        count = partial_assignments.count()
                        for p in partial_assignments:
                            p.deactivate()
                            create_notification(
                                user=p.student.user,
                                title="Temporary Seat Ended",
                                message=f"Your temporary allotment for Seat {seat.seat_number} has ended.",
                                category="seat"
                            )
                        
                        seat.recalc_status(save=True)
                        return success_response(f"Temporary allotment ended. {count} tenant(s) removed. Owner status preserved.")

                # Standard Behavior: Deactivate EVERYONE (Owners)
                assignments = SeatAssignment.objects.filter(seat=seat, is_active=True)
                names = []

                for a in assignments:
                    names.append(a.student.full_name)
                    a.deactivate()

                # Clear seat-level hold data
                seat.hold_status = 'none'
                seat.hold_student = None
                seat.hold_start_date = None
                seat.hold_end_date = None
                seat.status = 'available'
                seat.available_since = timezone.now()
                seat.save(update_fields=[
                    'status','hold_status','hold_student','hold_start_date','hold_end_date','available_since'
                ])

                student_name = ", ".join(names) if names else "Student"

                return success_response(
                    f'Seat {seat_number} is now available. {student_name} has been unassigned.'
                )

        # ------------------------------------
        # 2. ACTION: APPROVE PENDING REQUEST
        # ------------------------------------
        elif action == 'approve_pending':
            with transaction.atomic():
                request_shift = payload.get('shift', 'full')
                request_student_id = payload.get('request_id')
                
                # Build query to find the specific genuine pending assignment
                pending_filter = {'seat': seat, 'is_active': False, 'student__status': 'pending'}
                if request_student_id:
                    pending_filter['student_id'] = request_student_id
                if request_shift:
                    pending_filter['shift_type'] = request_shift
                
                assignment = SeatAssignment.objects.select_for_update().filter(
                    **pending_filter
                ).select_related('student').first()

                if not assignment:
                    return JsonResponse({'status':'error','message':'No pending assignment found for this shift.'},status=400)

                student = assignment.student
                shift_type = assignment.shift_type

                if conflict_assignment := SeatAssignment.objects.filter(
                    seat=seat,
                    is_active=True,
                    shift_type__in=[shift_type, 'full'] if shift_type != 'full' else ['morning', 'evening', 'full']
                ).exclude(pk=assignment.pk).select_related('student').first():
                    # CHANGE: If the conflict is an OWNER ON HOLD, and this is a PARTIAL request, we allow it!
                    # But wait, logic:
                    # If I am approving a Partial Request, I am a Tenant.
                    # My assignment.is_partial SHOULD be True.
                    
                    is_taking_partial = assignment.is_partial
                    conflict_is_hold = (conflict_assignment.hold_status == 'active')
                    conflict_is_owner = (not conflict_assignment.is_partial)
                    
                    if is_taking_partial and conflict_is_hold and conflict_is_owner:
                        # Allow! We are tenant taking over a held seat.
                        pass
                    else:
                        occupier = conflict_assignment.student
                        return JsonResponse({
                            'status': 'conflict',
                            'message': f'{shift_type.capitalize()} shift is already occupied by {occupier.full_name}.',
                            'occupier': {
                                'name': occupier.full_name,
                                'id': occupier.id,
                                'shift': conflict_assignment.shift_type
                            },
                            'requested_student': {
                                'name': student.full_name,
                                'id': student.id,
                                'request_id': assignment.id
                            },
                            'seat_number': seat.seat_number,
                            'floor': seat.floor
                        }, status=409)

                # No conflict - ACTIVATE the assignment
                assignment.is_active = True
                assignment.save(update_fields=['is_active'])

                if student.status == 'pending':
                    student.status = 'admitted'
                    student.save(update_fields=['status'])

                create_notification(
                    user=student.user,
                    title="Seat Approved",
                    message=f"Your seat {seat.seat_number} ({shift_type}) on {seat.floor} has been approved.",
                    link="/dashboard/",
                    category="seat"
                )

                try:
                    threading.Thread(
                        target=notifications.send_admission_approval_notifications,
                        args=(student, seat)
                    ).start()
                except Exception:
                    pass

                return success_response(
                    f'Admission for {student.full_name} approved ({shift_type}). Seat {seat_number} is now occupied.'
                )
        
        # ------------------------------------
        # 3. ACTION: DELETE PENDING REQUEST
        # ------------------------------------
        elif action == 'delete_request':
            request_shift = payload.get('shift')
            request_student_id = payload.get('request_id')
            
            # Build query to find the specific genuine pending assignment
            pending_filter = {'seat': seat, 'is_active': False, 'student__status': 'pending'}
            if request_student_id:
                pending_filter['student_id'] = request_student_id
            if request_shift:
                pending_filter['shift_type'] = request_shift
                
            assignment = SeatAssignment.objects.filter(
                **pending_filter
            ).select_related('student').first()

            if not assignment:
                return JsonResponse({'status':'error','message':'No pending request found for this shift.'},status=400)

            student = assignment.student
            shift_label = assignment.shift_type
            is_special_request_deletion = assignment.is_partial # Check if this was a temp request
            
            assignment.delete()

            if not student:
                return JsonResponse({'status': 'error', 'message': 'No student found to reject.'}, status=400)

            name = student.full_name

            # Free up the seat pointer on profile ONLY if no other assignments exist
            other_assignments = SeatAssignment.objects.filter(student=student, is_active=True).exists()
            # Also check if they are an Owner of *another* seat (unlikely but possible)?
            # Primarily check if they have any *active* seat.
            
            if not other_assignments:
                # If they were a Partial Tenant candidate, they shouldn't lose their seat pointer 
                # if they actually hold a seat elsewhere... 
                # But here we are deleting a *pending* assignment.
                # If they have no active assignments, clear the pointer.
                student.seat = None
                student.save(update_fields=['seat'])
            
            create_notification(
                user=student.user,
                title="Seat Request Rejected",
                message=f"Your request for {shift_label} shift was rejected by the teacher. Please select another seat.",
                link="/dashboard/",
                category="seat"
            )

            try:
                notifications.send_seat_rejection_email(student, seat, shift_label)
            except Exception:
                pass

            return success_response(f'Pending request for {name} ({shift_label}) deleted.')
            
        # ------------------------------------
        # 4. ACTION: END HOLD
        # ------------------------------------
        elif action == 'end_hold':
            # Use specific student_id if provided (for shift-wise selective release)
            target_assignments = SeatAssignment.objects.filter(
                seat=seat,
                is_active=True,
                hold_status='active'
            )
            
            if student_id:
                target_assignments = target_assignments.filter(student_id=student_id)
            
            if not target_assignments.exists():
                return JsonResponse({'status': 'error', 'message': 'No active hold found.'}, status=400)

            # Process removal
            for owner in target_assignments:
                # 1. Restore owner status — keep dates for fee extension history
                actual_end = timezone.now().date()
                owner.hold_status = 'none'
                owner.hold_end_date = actual_end  # Actual end, not original X days
                # hold_start_date preserved for fee extension calc
                owner.save(update_fields=['hold_status', 'hold_end_date'])

                # 2. Evict any partial tenants occupying THIS owner's shift
                partials_to_evict = SeatAssignment.objects.filter(
                    seat=seat,
                    is_active=True,
                    is_partial=True
                )
                if owner.shift_type != 'full':
                    # Only evict partials that conflict with this owner's shift
                    partials_to_evict = partials_to_evict.filter(
                        shift_type__in=[owner.shift_type, 'full']
                    )
                
                for p in partials_to_evict:
                    p.deactivate()
                    create_notification(
                        user=p.student.user,
                        title="Temporary Seat Ended",
                        message=f"The hold on Seat {seat.seat_number} has ended. Your temporary allotment is finished.",
                        category="seat"
                    )

                # Recalculate fee expiry with hold extension
                _recalc_fee_expiry_with_hold(owner.student)

                create_notification(
                    user=owner.student.user,
                    title="Seat Restored",
                    message=f"Your seat {seat.seat_number} is active again.",
                    category="seat"
                )

            # Cleanup legacy seat fields if ALL holds are gone
            if not SeatAssignment.objects.filter(seat=seat, is_active=True, hold_status='active').exists():
                seat.hold_status = 'none'
                seat.hold_student = None
                seat.save(update_fields=['hold_status', 'hold_student'])

            # Dynamic Status Recalculation
            seat.recalc_status(save=True)

            return success_response(f"Hold ended for Seat {seat_number}. Selective restoration complete.")

        # ------------------------------------
        # 5. ACTION: FREE A SHIFT
        # ------------------------------------
        elif action == 'free_shift':
            shift = payload.get('shift')

            if shift not in ['morning', 'evening']:
                return JsonResponse(
                    {'status': 'error', 'message': 'Invalid or missing shift.'},
                    status=400
                )

            # SAFETY CHECK: If this shift has a PARTIAL tenant, we only remove THE TENANT.
            # We preserve the Owner-On-Hold.
            partial_assignments = SeatAssignment.objects.filter(
                seat=seat,
                shift_type=shift,
                is_active=True,
                is_partial=True
            )

            if partial_assignments.exists():
                for p in partial_assignments:
                    p.deactivate()
                    create_notification(
                        user=p.student.user,
                        title="Temporary Seat Ended",
                        message=f"Your temporary allotment for {shift} shift on Seat {seat.seat_number} has ended.",
                        category="seat"
                    )
                # count = count_freed # This variable is not defined in the provided context. Assuming it's a placeholder or needs to be defined elsewhere.
                seat.recalc_status(save=True)

                # --- START NEW SAFEGUARD ---
                active_owners = SeatAssignment.objects.filter(seat=seat, is_active=True, is_partial=False)
                for owner in active_owners:
                    if owner.hold_status == 'active':
                        # Refreshing their status guarantees the frontend receives "active" metadata
                        owner.student.status = 'on_hold'
                        owner.student.save(update_fields=['status'])
                        seat.status = 'on_hold'
                        seat.save(update_fields=['status'])
                # --- END NEW SAFEGUARD ---

                return success_response(f"{shift.capitalize()} shift - Temporary allotment ended. Owner status preserved.")

            # Standard Behavior: Deactivate active assignments for this shift (Owner)
            assignments = SeatAssignment.objects.filter(
                seat=seat,
                shift_type=shift,
                is_active=True
            )

            if not assignments.exists():
                return JsonResponse(
                    {'status': 'error', 'message': f'No active {shift} assignment to free.'},
                    status=400
                )

            for a in assignments:
                a.deactivate()

            # Trigger recalc to update seat color
            seat.recalc_status(save=True)

            return success_response(
                f"{shift.capitalize()} shift freed for Seat {seat_number}."
            )

        # ------------------------------------
        # 6. ACTION: PUT SHIFT ON HOLD
        # ------------------------------------
        elif action == 'put_shift_on_hold':
            shift = payload.get('shift')

            if shift not in ['morning', 'evening']:
                return JsonResponse(
                    {'status': 'error', 'message': 'Invalid or missing shift.'},
                    status=400
                )

            assignment = SeatAssignment.objects.filter(
                seat=seat,
                shift_type=shift,
                is_active=True
            ).first()

            if not assignment:
                return JsonResponse(
                    {'status': 'error', 'message': f'No active {shift} assignment to hold.'},
                    status=400
                )

            assignment.hold_status = 'active'
            assignment.hold_start_date = timezone.now().date()
            assignment.hold_end_date = seat.hold_end_date # fallback if seat has date
            assignment.save(
                update_fields=['hold_status', 'hold_start_date', 'hold_end_date']
            )

            # Visual update
            seat.status = 'on_hold' 
            seat.save(update_fields=['status'])

            return success_response(
                f"{shift.capitalize()} shift placed on hold for Seat {seat_number}."
            )

        # ------------------------------------
        # 7. ACTION: ASSIGN FULL DAY TEMP (Explicit Partial)
        # ------------------------------------
        elif action == 'assign_full_day_temp':
            if seat.status != 'on_hold':
                # Double check shift-level holds if seat-level check fails
                has_shift_hold = SeatAssignment.objects.filter(seat=seat, is_active=True, hold_status='active').exists()
                if not has_shift_hold:
                    return JsonResponse(
                        {'status': 'error', 'message': 'Temporary full-day allowed only during hold.'},
                        status=400
                    )

            if not student_id:
                return JsonResponse(
                    {'status': 'error', 'message': 'Student ID required.'},
                    status=400
                )

            student = StudentProfile.objects.select_for_update().get(id=student_id)

            try:
                SeatAssignment.objects.create(
                    seat=seat,
                    student=student,
                    shift_type='full',
                    is_active=True,
                    is_partial=True,           # Explicitly marking as Partial Tenant
                    allow_hold_override=True
                )
            except ValidationError as e:
                return JsonResponse(
                    {'status': 'error', 'message': e.messages[0]},
                    status=400
                )

            student.seat = seat
            student.shift = 'full'
            student.status = 'admitted'
            student.save(update_fields=['seat', 'shift', 'status'])

            return success_response(
                f"Temporary full-day seat assigned to {student.full_name}."
            )

        # ------------------------------------
        # 8. ACTION: PUT SEAT ON HOLD (Standard)
        # ------------------------------------
        elif action == 'put_on_hold':
            # Basic validation
            start_date_str = payload.get('start_date')
            duration_str = (payload.get('duration') or '').strip().lower()
            
            if not start_date_str or not duration_str:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Hold start date and duration are required.'
                }, status=400)
                
            try:
                start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            except ValueError:
                return JsonResponse({'status': 'error', 'message': 'Invalid date format.'}, status=400)

            # Duration Parsing
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
                    return JsonResponse({
                        'status': 'error',
                        'message': 'Invalid hold duration format.'
                    }, status=400)

            end_date = start_date + relativedelta(months=months, days=days) - timedelta(days=1)
            total_days = (end_date - start_date).days + 1

            if total_days < 1:
                return JsonResponse({'status': 'error','message': 'Hold duration must be at least 1 day.'}, status=400)

            # --- Target Assignments Selection ---
            # If student_id is provided, we only put THAT specific assignment on hold.
            # This is crucial for shift seats!
            active_owners = SeatAssignment.objects.filter(
                seat=seat,
                is_active=True
            )
            
            if student_id:
                active_owners = active_owners.filter(student_id=student_id)
            
            if not active_owners.exists():
                return JsonResponse({
                    'status': 'error',
                    'message': 'No active assignment found to place on hold.'
                }, status=400)

            today = timezone.now().date()

            # Apply hold dates to selected assignments
            for owner in active_owners:
                owner.hold_start_date = start_date
                owner.hold_end_date = end_date

                if start_date <= today:
                    # Hold starts today or in the past — activate immediately
                    owner.hold_status = 'active'
                    owner.student.status = 'on_hold'
                    owner.student.save(update_fields=['status'])
                else:
                    # Future hold — keep hold_status='none' until start date
                    owner.hold_status = 'none'
                    # student.status stays 'admitted'

                owner.save(update_fields=['hold_status', 'hold_start_date', 'hold_end_date'])

                # Legacy tracking on seat model
                seat.hold_student = owner.student
                seat.hold_start_date = start_date
                seat.hold_end_date = end_date

                if start_date <= today:
                    seat.hold_status = 'active'
                else:
                    seat.hold_status = 'none'

                seat.save(update_fields=['hold_status', 'hold_student', 'hold_start_date', 'hold_end_date'])

                # Recalculate fee expiry with hold extension
                _recalc_fee_expiry_with_hold(owner.student)

            # Dynamic Status Recalculation (Determines color)
            seat.recalc_status(save=True)

            if start_date <= today:
                msg = f'Seat {seat_number} is now on hold until {end_date.strftime("%d-%b-%Y")}.'
            else:
                msg = (f'Hold scheduled: Seat {seat_number} will be put on hold '
                       f'from {start_date.strftime("%d-%b-%Y")} to {end_date.strftime("%d-%b-%Y")}. '
                       f'Status remains unchanged until then.')

            return success_response(msg)

        # ------------------------------------
        # 8b. ACTION: DELETE SCHEDULED (FUTURE) HOLD
        # ------------------------------------
        elif action == 'delete_scheduled_hold':
            today = timezone.now().date()

            # Find the scheduled future hold for the given student on this seat
            target_assigns = SeatAssignment.objects.filter(
                seat=seat,
                is_active=True,
                hold_status='none',
                hold_start_date__isnull=False,
                hold_start_date__gt=today,
            )
            if student_id:
                target_assigns = target_assigns.filter(student_id=student_id)

            if not target_assigns.exists():
                return JsonResponse({
                    'status': 'error',
                    'message': 'No scheduled future hold found for this student.'
                }, status=404)

            with transaction.atomic():
                for assign in target_assigns:
                    assign.hold_start_date = None
                    assign.hold_end_date = None
                    assign.hold_status = 'none'
                    assign.save(update_fields=['hold_start_date', 'hold_end_date', 'hold_status'])

                # Clear seat-level hold fields if they match
                if seat.hold_start_date and seat.hold_start_date > today:
                    seat.hold_start_date = None
                    seat.hold_end_date = None
                    seat.hold_status = 'none'
                    seat.save(update_fields=['hold_start_date', 'hold_end_date', 'hold_status'])

                seat.recalc_status(save=True)

            # Notify the student
            for assign in target_assigns:
                create_notification(
                    user=assign.student.user,
                    title="Scheduled Hold Cancelled",
                    message=f"The teacher has cancelled the scheduled hold on your seat ({seat_number}). Your seat remains active.",
                    category="seat"
                )

            return success_response(f'Scheduled hold for Seat {seat_number} has been deleted. The seat remains occupied.')

        # ------------------------------------
        # 9. ACTION: APPROVE PARTIAL REQUEST
        # ------------------------------------
        elif action == 'approve_partial_request':

            request_id = payload.get('request_id')

            if not request_id:
                return JsonResponse(
                    {'status': 'error', 'message': 'Request ID required'},
                    status=400
                )

            with transaction.atomic():
                try:
                    special_request = SeatSpecialRequest.objects.select_for_update().get(
                        id=request_id,
                        status='pending'
                    )
                except SeatSpecialRequest.DoesNotExist:
                    return JsonResponse({'status': 'error', 'message': 'Request not found.'}, status=404)

                seat = special_request.seat
                student = special_request.student
                requested_shift = special_request.requested_shift

                try:
                    SeatAssignment.objects.create(
                        seat=seat,
                        student=student,
                        shift_type=requested_shift,
                        is_active=True,
                        is_partial=True,           # Explicitly Partial
                        allow_hold_override=True
                    )
                except ValidationError as e:
                    return JsonResponse(
                        {'status': 'error', 'message': e.messages[0]},
                        status=400
                    )

                student.seat = seat
                student.shift = requested_shift
                student.status = 'admitted'
                student.save(update_fields=['seat', 'shift', 'status'])

                special_request.status = 'approved'
                special_request.save(update_fields=['status'])

                create_notification(
                    user=student.user,
                    title="Seat Partially Allotted",
                    message=(
                        f"You have been temporarily allotted "
                        f"Seat {seat.seat_number} ({requested_shift.capitalize()}) "
                        f"until hold ends."
                    ),
                    category="seat"
                )

                return success_response(
                    f"Partial allotment approved for {student.full_name}."
                )

        # ------------------------------------
        # 10. ACTION: ALLOT / ASSIGN MANUAL
        # ------------------------------------
        elif action in ['allot', 'assign_manual']:
            
            # A. Resolve Student Object
            if action == 'allot':
                if not student_id:
                    return JsonResponse({'status': 'error', 'message': 'Student ID required.'}, status=400)
                
                student_id_str = str(student_id)
                student_user = None
                
                if student_id_str.startswith('user_'):
                    user_id = int(student_id_str.split('_')[1])
                    student_user = get_object_or_404(DjangoUser, id=user_id)
                    achievement = StudentAchievement.objects.filter(user=student_user).first()
                    
                    full_name = f"{student_user.first_name} {student_user.last_name}".strip() or student_user.username
                    sex = 'Other'
                    dob = None
                    mobile = ''
                    whatsapp = ''
                    email = student_user.email
                    
                    if achievement:
                        full_name = achievement.full_name
                        sex = achievement.gender
                        dob = achievement.dob
                        mobile = achievement.mobile_number or ''
                        whatsapp = achievement.whatsapp_number or ''
                        email = achievement.email or student_user.email

                    # Get or create the StudentProfile
                    from django.utils import timezone
                    student, created = StudentProfile.objects.select_for_update().get_or_create(
                        user=student_user,
                        defaults={
                            'full_name': full_name,
                            'sex': sex,
                            'dob': dob,
                            'mobile_number': mobile,
                            'whatsapp_number': whatsapp,
                            'status': 'admitted',
                            'is_admitted': True,
                            'service_type': 'Library',
                            'email': email,
                            'approved_at': timezone.now()
                        }
                    )
                else:
                    try:
                        student = StudentProfile.objects.select_for_update().get(id=student_id)
                        student_user = student.user
                    except StudentProfile.DoesNotExist:
                        return JsonResponse({'status': 'error', 'message': 'Selected student not found.'}, status=400)
                
                # Check for Action Scope from Payload
                action_scope = payload.get('action_scope')
                
                if action_scope == 'switch':
                    # Switch to Library only: delete alumni profile and set service to library only
                    achievement = StudentAchievement.objects.filter(user=student_user).first()
                    if achievement:
                        decouple_chats_for_achievement(achievement)
                        achievement.delete()
                    
                    student.service_type = 'Library'
                    student.save(update_fields=['service_type'])
                    
                elif action_scope == 'add':
                    # Add to Library: update service type accordingly
                    if student.service_type == 'Coaching':
                        student.service_type = 'Both'
                    else:
                        if student.service_type not in ['Library', 'Both']:
                            student.service_type = 'Library'
                    student.save(update_fields=['service_type'])

                existing_seat = student.seat
                if existing_seat and (existing_seat.id != seat.id):
                    if not reassign and not force:
                        return JsonResponse({
                            'status': 'conflict',
                            'conflict_type': 'student_has_seat',
                            'message': f"Student already has seat {existing_seat.seat_number}. Confirm reassign.",
                            'existing_seat': existing_seat.seat_number,
                            'student_name': student.full_name,
                            'student_id': student.id
                        }, status=409)

                    # Teacher confirmed reassign: deactivate current active assignments
                    active_assignments = SeatAssignment.objects.filter(
                        student=student,
                        is_active=True
                    ).select_related('seat')
                    for assignment in active_assignments:
                        assignment.deactivate()
                    
                    # Also delete any pending special requests for the old seat
                    SeatSpecialRequest.objects.filter(
                        student=student,
                        status='pending'
                    ).delete()
                    
                    # Clear old seat reference
                    student.seat = None
                    student.save(update_fields=['seat'])

            elif action == 'assign_manual':
                # Manual User Creation Logic
                username = (payload.get('username') or '').strip()
                password = payload.get('password') or ''
                first_name = (payload.get('first_name') or '').strip()
                last_name = (payload.get('last_name') or '').strip()
                full_name = (payload.get('full_name') or '').strip()
                mobile_number = (payload.get('mobile_number') or '').strip()
                whatsapp_number = (payload.get('whatsapp_number') or '').strip()
                email = (payload.get('email') or '').strip()
                profile_photo_base64 = payload.get('profile_photo')
                service_type = payload.get('service_type') or 'Library'

                if not full_name:
                    full_name = f"{first_name} {last_name}".strip()

                if not username or not password or not first_name or not last_name:
                    return JsonResponse({'status': 'error', 'message': 'Missing required fields for manual assignment.'}, status=400)

                if not whatsapp_number and not mobile_number:
                    return JsonResponse({'status': 'error', 'message': 'Provide at least one contact number.'}, status=400)

                if not whatsapp_number:
                    whatsapp_number = mobile_number
                if not mobile_number:
                    mobile_number = whatsapp_number

                # Duplicate contact checks
                existing = StudentProfile.objects.filter(
                    models.Q(whatsapp_number=whatsapp_number) | models.Q(mobile_number=mobile_number)
                ).first()
                if existing:
                    return JsonResponse({'status': 'error', 'message': f'Student with this contact exists: {existing.full_name}'}, status=400)

                # Email format & uniqueness checks
                if email:
                    email = email.strip().lower()
                    import re
                    if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                        return JsonResponse({'status': 'error', 'message': 'Please enter a valid email address.'}, status=400)
                    if User.objects.filter(email__iexact=email).exists() or \
                       StudentProfile.objects.filter(email__iexact=email).exists() or \
                       StudentAchievement.objects.filter(email__iexact=email).exists():
                        return JsonResponse({'status': 'error', 'message': 'This email address is already registered in the system.'}, status=400)

                # Username uniqueness
                base_username = username.lower()
                unique_username = base_username
                i = 1
                while User.objects.filter(username=unique_username).exists():
                    unique_username = f"{base_username}{i}"
                    i += 1

                # Create User & Profile
                user = User.objects.create_user(
                    username=unique_username,
                    password=password,
                    email=email or '',
                    first_name=first_name,
                    last_name=last_name
                )
                student = StudentProfile.objects.create(
                    user=user,
                    full_name=full_name,
                    sex=payload.get('sex', 'Other'),
                    sex_other=payload.get('sex_other', None),
                    dob=payload.get('dob', None) or None,
                    service_type=service_type,
                    email=email or '',
                    mobile_number=mobile_number or whatsapp_number,
                    whatsapp_number=whatsapp_number,
                    batch=payload.get('batch', None),
                    status='admitted',
                    is_admitted=True,           # <--- Parity: Marked as admitted
                    is_manual_pending=False,    # <--- Parity: No pending state
                    seat=seat,
                    approved_at=timezone.now()
                )

                # --- In-app Notification for Parity ---
                create_notification(
                    user=student.user,
                    title="Admission Confirmed",
                    message="Your admission has been manually confirmed by the teacher. You now have full access.",
                    category="admission"
                )

                # --- Handle Profile Photo ---
                if profile_photo_base64 and profile_photo_base64.startswith('data:image'):
                    try:
                        import base64
                        from django.core.files.base import ContentFile
                        format, imgstr = profile_photo_base64.split(';base64,')
                        ext = format.split('/')[-1]
                        # Use a unique name for the photo
                        photo_name = f"manual_profile_{student.id}_{int(timezone.now().timestamp())}.{ext}"
                        student.photo = ContentFile(base64.b64decode(imgstr), name=photo_name)
                        student.save(update_fields=['photo'])
                    except Exception as e:
                        print(f"DEBUG: Error saving manual profile photo: {str(e)}")
                # --- End Photo Handling ---

            # --- B. INTELLIGENT LOGIC: UPGRADE VS PARTIAL ---
            requested_shift = payload.get('shift', 'full')
            is_partial_mode = False
            
            # 1. CHECK UPGRADE (Is this student ALREADY on this seat?)
            # We look for an active assignment for THIS student on THIS seat.
            existing_on_seat = SeatAssignment.objects.filter(
                seat=seat, student=student, is_active=True
            ).first()
            
            if existing_on_seat:
                # SCENARIO: Existing student upgrading to Full Day OR making their current shift Permanent
                if existing_on_seat.hold_status == 'active':
                    return JsonResponse({'status':'error', 'message':'Cannot upgrade a seat while it is on hold.'}, status=400)
                
                # We are merging/upgrading. Deactivate the old partial shift (e.g. Morning).
                # The new assignment created below will be Permanent (is_partial=False).
                existing_on_seat.is_active = False 
                existing_on_seat.save()
                
            else:
                # SCENARIO: New Student / Stranger (Subject to Partial Logic)
                # Check if seat is on hold
                if seat.status == 'on_hold':
                    is_partial_mode = True
                elif seat.is_shift_enabled:
                    # Check if any existing occupants are on hold
                    existing_holders = SeatAssignment.objects.filter(
                        seat=seat, is_active=True, hold_status='active'
                    )
                    
                    if requested_shift == 'full':
                        # If ANY part of the seat is held, the Stranger takes it Partially
                        if existing_holders.exists():
                            is_partial_mode = True
                    else:
                        # If the specific shift I want is held
                        if existing_holders.filter(shift_type=requested_shift).exists():
                            is_partial_mode = True

            # --- TEACHER FORCE: Check for existing occupants on target seat ---
            # If force=True, remove any existing occupants on the target shift
            if force:
                conflicting_assignments = SeatAssignment.objects.filter(
                    seat=seat,
                    is_active=True
                )
                # Filter by shift: if full requested, remove all; if specific shift, remove that shift or full
                if requested_shift == 'full':
                    # Remove all active assignments on this seat
                    pass  # Keep all for removal
                else:
                    # Remove only matching shift or full-day assignments
                    conflicting_assignments = conflicting_assignments.filter(
                        models.Q(shift_type=requested_shift) | models.Q(shift_type='full')
                    )
                
                for ca in conflicting_assignments:
                    if ca.student_id != student.id:  # Don't deactivate our own student
                        ca.deactivate()
                        
                        create_notification(
                            user=ca.student.user,
                            title="Seat Reassigned",
                            message=f"Your seat {seat.seat_number} has been reassigned by teacher. Please contact administration.",
                            category="seat"
                        )

                        # Send Email to Student
                        send_html_email(
                            subject="Important: Seat Reassignment Notification",
                            to_email=get_user_notification_email(ca.student.user),
                            template="emails/course_update.html", # Reusing consistent layout
                            context={
                                "title": "Seat Reassigned",
                                "message": f"Your seat {seat.seat_number} has been reassigned by a teacher. This usually happens during floor management or batch changes.",
                                "course_name": f"Seat {seat.seat_number}",
                                "action_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                            },
                            fail_silently=True,
                        )

            # C. Create Assignment
            try:
                SeatAssignment.objects.create(
                    seat=seat,
                    student=student,
                    shift_type=requested_shift,
                    is_active=True,
                    is_partial=is_partial_mode,   # <--- The auto-detected flag
                    allow_hold_override=is_partial_mode or force
                )
            except ValidationError as e:
                if action == 'assign_manual': student.delete() # Rollback
                return JsonResponse({'status': 'error', 'message': e.messages[0]}, status=400)

            # Update Student Link
            student.seat = seat
            student.shift = requested_shift
            
            # Parity: Ensure student is fully admitted when assigned/allotted a seat by teacher
            student.status = 'admitted'
            student.is_admitted = True
            student.is_manual_pending = False
            
            student.save()

            # Notifications
            if action == 'assign_manual':
                try:
                    threading.Thread(target=notifications.send_admission_approval_notifications, args=(student, seat)).start()
                except: pass
                msg = f'Manually created {full_name} and assigned Seat {seat_number}.'
            else:
                msg = f"Seat {seat_number} assigned to {student.full_name}."

            return success_response(msg)

        # ------------------------------------
        # 11. ACTION: REJECT PARTIAL REQUEST
        # ------------------------------------
        elif action == 'reject_partial_request':
            request_id = payload.get('request_id')

            if not request_id:
                return JsonResponse({'status': 'error', 'message': 'Request ID required.'}, status=400)

            try:
                special_req = SeatSpecialRequest.objects.select_for_update().get(
                    id=request_id,
                    status='pending'
                )
            except SeatSpecialRequest.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Pending request not found.'}, status=404)

            special_req.status = 'rejected'
            special_req.save(update_fields=['status'])

            create_notification(
                user=special_req.student.user,
                title="Partial Seat Request Rejected",
                message=f"Your request for Seat {special_req.seat.seat_number} was rejected.",
                link="/dashboard/",
                category="seat"
            )

            return JsonResponse({'status': 'success', 'message': 'Partial allotment request rejected.'})

        else:
            return JsonResponse({'status': 'error', 'message': f'Invalid action: {action}'}, status=400)

    except Seat.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Seat not found.'}, status=404)
    except StudentProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Student not found during operation.'}, status=404)
    except Exception as e:
        print("seat_action_api critical error:", str(e))
        return JsonResponse({'status': 'error', 'message': f'A critical error occurred: {str(e)}'}, status=500)

#now retreive the code from here of seat_action_api .... 
# -------------------------------------------------------------------
# API: Student Special Seat Request (Partial Allotment / Shift Request)
# -------------------------------------------------------------------

@login_required
@transaction.atomic
def send_special_seat_request_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Invalid request method'}, status=405)

    try:
        data = json.loads(request.body or {})
        seat_number = str(data.get('seat_number') or '').strip()
        floor = (data.get('floor') or '').strip()
        requested_shift = (data.get('requested_shift') or 'full').strip().lower()

        if not seat_number or not floor:
            return JsonResponse({'error': 'Seat number and floor are required'}, status=400)

        # Get or create student profile for new students
        try:
            student = StudentProfile.objects.select_for_update().get(user=request.user)
            # Prevent if student already has an ACTIVE seat (admitted status)
            if student.seat_id and student.status == 'admitted':
                return JsonResponse({'error': 'You already have an active seat.'}, status=400)
        except StudentProfile.DoesNotExist:
            # New student - they don't have a profile yet, that's OK
            # We'll create the SeatSpecialRequest with student=None and store user reference
            student = None

        seat = Seat.objects.select_for_update().get(
            seat_number=seat_number,
            floor=floor
        )

        # --- ENFORCE STRICT SHIFT DEFINITION ---
        is_strict_shift_seat = (seat.floor == 'Ground Floor' and 40 <= int(seat.seat_number) <= 53)
        seat.is_shift_enabled = is_strict_shift_seat  # update in memory
        # ---------------------------------------

        if seat.status != 'on_hold':
            return JsonResponse({'error': 'Seat is not currently on hold'}, status=400)

        # Ensure hold owner exists (owner = hold_status='active' AND is_partial=False)
        hold_owner_assignment = SeatAssignment.objects.filter(
            seat=seat,
            is_active=True,
            hold_status='active',
            is_partial=False
        ).select_related('student').first()

        if not hold_owner_assignment:
            return JsonResponse(
                {'error': 'Seat hold owner not found. Partial requests are not allowed.'},
                status=400
            )

        # Check if the requester already owns this seat (only for existing students)
        if student and hold_owner_assignment.student_id == student.id:
            return JsonResponse({'error': 'You already own this seat.'}, status=400)

        # -------------------------------
        # SHIFT + HOLD VALIDATION (CORE LOGIC)
        # -------------------------------

        active_assignments = SeatAssignment.objects.filter(seat=seat, is_active=True)

        hold_assignments = active_assignments.filter(hold_status='active', is_partial=False)
        partial_assignments = active_assignments.filter(is_partial=True)

        # Prevent more than one partial tenant per shift
        if requested_shift in ('morning', 'evening', 'full'):
            if partial_assignments.filter(shift_type=requested_shift).exists():
                return JsonResponse({'error': 'This shift already has a temporary student.'}, status=400)

        if not seat.is_shift_enabled:
            # Normal seat
            if requested_shift != 'full':
                return JsonResponse({'error': 'Shift selection not allowed for this seat'}, status=400)

            if not hold_assignments.exists():
                return JsonResponse({'error': 'Seat is not under active hold'}, status=400)

        else:
            # Shift seat (40–53 ground floor)

            if requested_shift not in ('morning', 'evening', 'full'):
                return JsonResponse({'error': 'Invalid shift selection'}, status=400)

            morning_owner = active_assignments.filter(shift_type='morning', is_partial=False).first()
            evening_owner = active_assignments.filter(shift_type='evening', is_partial=False).first()
            full_owner = active_assignments.filter(shift_type='full', is_partial=False).first()

            morning_on_hold = bool(morning_owner and morning_owner.hold_status == 'active')
            evening_on_hold = bool(evening_owner and evening_owner.hold_status == 'active')
            full_on_hold = bool(full_owner and full_owner.hold_status == 'active')

            morning_taken = active_assignments.filter(shift_type='morning').exists()
            evening_taken = active_assignments.filter(shift_type='evening').exists()

            if requested_shift == 'morning':
                if not (morning_on_hold or full_on_hold):
                    return JsonResponse({'error': 'Morning shift is not on hold'}, status=400)

            elif requested_shift == 'evening':
                if not (evening_on_hold or full_on_hold):
                    return JsonResponse({'error': 'Evening shift is not on hold'}, status=400)

            elif requested_shift == 'full':
                # Allow full-day temp when both shifts are on hold OR when full-day is on hold
                valid = (
                    full_on_hold or
                    (morning_on_hold and evening_on_hold) or
                    (morning_on_hold and not evening_taken) or
                    (evening_on_hold and not morning_taken)
                )
                if not valid:
                    return JsonResponse({
                        'error': 'Full day temporary allotment not allowed for this seat'
                    }, status=400)

                # If one shift already has a temporary tenant, block full-day temp
                if partial_assignments.filter(shift_type__in=['morning', 'evening', 'full']).exists():
                    return JsonResponse({
                        'error': 'Full day temporary allotment not allowed while a shift is already temporarily allotted.'
                    }, status=400)

        # Prevent duplicate request (check by user for new students, or by student for existing)
        if student:
            duplicate_exists = SeatSpecialRequest.objects.filter(
                student=student, seat=seat, status='pending'
            ).exists()
        else:
            duplicate_exists = SeatSpecialRequest.objects.filter(
                user=request.user, seat=seat, status='pending'
            ).exists()
        
        if duplicate_exists:
            return JsonResponse({'error': 'You already have a pending request for this seat'}, status=400)

        # Create request (note: expiration_data from frontend is not stored,
        # instead we calculate hold_end_date from the seat's SeatAssignment on-the-fly)
        # Handle both new students (no profile) and existing students (with profile)
        SeatSpecialRequest.objects.create(
            user=request.user,
            student=student,  # Will be None for new students
            seat=seat,
            requested_shift=requested_shift
        )

        # Notify teachers
        from django.contrib.auth.models import User
        teachers = User.objects.filter(is_staff=True)
        
        # Get requester name (student profile name or username for new students)
        requester_name = student.full_name if student else request.user.username

        for teacher in teachers:
            create_notification(
                user=teacher,
                title="[TEMPORARY] Special Seat Request",
                message=(
                    f"{requester_name} requested "
                    f"{requested_shift.upper()} temporary allotment on "
                    f"Seat {seat.seat_number} ({seat.floor})"
                ),
                category="seat"
            )

        return JsonResponse({'status': 'success', 'message': 'Your request has been sent to the teacher.'})

    except StudentProfile.DoesNotExist:
        return JsonResponse({'error': 'Student profile not found'}, status=404)

    except Seat.DoesNotExist:
        return JsonResponse({'error': 'Seat not found'}, status=404)

    except Exception as e:
        print("special_seat_request error:", e)
        return JsonResponse({'error': 'Something went wrong. Please try again.'}, status=500)

# -------------------------------------------------------------------
# API VIEW: Handles approving/denying hold requests
@login_required
@user_passes_test(lambda u: u.is_staff)
@transaction.atomic
def manage_hold_request_api(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    try:
        data = json.loads(request.body or '{}')
        seat_id = data.get('seat_id')
        seat = Seat.objects.select_for_update().get(id=seat_id)

        action = data.get('action')  # approve | deny

        if not seat_id or action not in ['approve', 'deny']:
            return JsonResponse({'status': 'error', 'message': 'seat_id and valid action required.'}, status=400)
        
        # --------------------------------------------------
        # PARTIAL ALLOTMENT: APPROVE SPECIAL SEAT REQUEST
        # --------------------------------------------------
        special_request_id = data.get('special_request_id')

        if special_request_id:
            try:
                special_request = SeatSpecialRequest.objects.select_for_update().get(
                    id=special_request_id,
                    seat=seat,
                    status='pending'
                )
            except SeatSpecialRequest.DoesNotExist:
                return JsonResponse(
                    {'status': 'error', 'message': 'Special seat request not found.'},
                    status=404
                )

            student = special_request.student
            requested_shift = special_request.requested_shift

            # Create temporary assignment (HOLD OVERRIDE)
            try:
                SeatAssignment.objects.create(
                    seat=seat,
                    student=student,
                    shift_type=requested_shift,
                    is_active=True,
                    is_partial=True,
                    allow_hold_override=True
                )
            except ValidationError as e:
                return JsonResponse(
                    {'status': 'error', 'message': e.messages[0]},
                    status=400
                )

            # Update student record
            student.seat = seat
            student.shift = requested_shift
            student.status = 'admitted'
            student.save(update_fields=['seat', 'shift', 'status'])

            # Mark request approved
            special_request.status = 'approved'
            special_request.save(update_fields=['status'])

            create_notification(
                user=student.user,
                title="Partial Seat Approved",
                message=(
                    f"Your request for Seat {seat.seat_number} "
                    f"({requested_shift.capitalize()} shift) has been approved "
                    f"until hold ends."
                ),
                category="seat"
            )

            return JsonResponse({
                'status': 'success',
                'message': f'Partial allotment approved for {student.full_name}.'
            })
        # --------------------------------------------------

        # FULL HOLD REQUEST MANAGEMENT
        hold_request = SeatHoldRequest.objects.select_for_update().filter(
            seat_id=seat_id
        ).filter(
            models.Q(status='pending') | models.Q(status='approved', cancel_requested=True)
        ).first()

        if not hold_request:
            return JsonResponse({'status': 'error', 'message': 'Pending or cancelable hold request not found.'}, status=404)

        student = hold_request.student

        owner_assignment = SeatAssignment.objects.filter(
            seat=seat,
            student=student,
            is_active=True
        ).first()

        if not owner_assignment:
            return JsonResponse({'status': 'error', 'message': 'Seat owner assignment not found.'}, status=400)

        if hold_request.cancel_requested:
            if action == 'approve':
                hold_request.delete()
                
                today = timezone.now().date()
                hold_started = (owner_assignment.hold_start_date and owner_assignment.hold_start_date <= today)
                
                # Revert seat hold state
                seat.hold_status = 'none'
                seat.hold_student = None
                if hold_started:
                    # Active hold being ended early
                    seat.hold_end_date = today
                else:
                    # Future scheduled hold being cancelled before it starts
                    seat.hold_start_date = None
                    seat.hold_end_date = None
                
                seat.status = 'occupied'
                seat.save()
                
                # Revert assignment hold state
                owner_assignment.hold_status = 'none'
                if hold_started:
                    owner_assignment.hold_end_date = today
                else:
                    owner_assignment.hold_start_date = None
                    owner_assignment.hold_end_date = None
                owner_assignment.save()
                
                # Revert student status
                student.status = 'admitted'
                student.save(update_fields=['status'])
                
                # Recalculate fee expiry with hold extension (only counts days already passed)
                _recalc_fee_expiry_with_hold(student)
                
                seat.recalc_status()

                create_notification(
                    user=student.user,
                    title="Hold Cancellation Approved",
                    message=f"Your request to cancel the hold on Seat {seat.seat_number} was approved.",
                    link="/dashboard/",
                    category="seat"
                )

                return JsonResponse({
                    'status': 'success',
                    'message': f'Hold cancellation approved for seat {seat.seat_number}.'
                })
            else:
                hold_request.cancel_requested = False
                hold_request.save(update_fields=['cancel_requested'])

                create_notification(
                    user=student.user,
                    title="Hold Cancellation Denied",
                    message=f"Your request to cancel the hold on Seat {seat.seat_number} was denied. The hold will proceed.",
                    link="/dashboard/",
                    category="seat"
                )

                return JsonResponse({
                    'status': 'success',
                    'message': f'Hold cancellation denied. Hold will proceed for seat {seat.seat_number}.'
                })

        if action == 'approve':

            # --- Calculate end date ---
            start_date = hold_request.start_date
            duration_str = hold_request.duration_text.lower()

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
                    return JsonResponse({'status': 'error', 'message': 'Invalid duration format.'}, status=400)

            end_date = start_date + relativedelta(months=months, days=days) - timedelta(days=1)

            # Store hold details unconditionally
            seat.hold_student = student
            seat.hold_start_date = start_date
            seat.hold_end_date = end_date
            
            owner_assignment.hold_start_date = start_date
            owner_assignment.hold_end_date = end_date

            today = timezone.now().date()
            if start_date <= today:
                seat.status = 'on_hold'
                seat.hold_status = 'active'
                owner_assignment.hold_status = 'active'
                student.status = 'on_hold'
                student.save(update_fields=['status'])
            else:
                # Keep seat available/occupied until start date
                seat.hold_status = 'none'
                owner_assignment.hold_status = 'none'
            
            seat.save()
            owner_assignment.save()

            # Recalculate fee expiry with hold extension
            _recalc_fee_expiry_with_hold(student)

            # Mark request approved
            hold_request.status = 'approved'
            hold_request.save(update_fields=['status'])

            create_notification(
                user=student.user,
                title="Seat Hold Approved",
                message=f"Your request to hold Seat {seat.seat_number} was approved and will begin on {start_date.strftime('%d %b %Y')}.",
                link="/dashboard/",
                category="seat"
            )

            return JsonResponse({
                'status': 'success',
                'message': f'Hold request approved for seat {seat.seat_number}.'
            })

        # ---------- DENY ----------

        hold_request.status = 'rejected'
        hold_request.save(update_fields=['status'])

        create_notification(
            user=student.user,
            title="Seat Hold Denied",
            message="Your seat hold request was denied by the teacher.",
            link="/dashboard/",
            category="seat"
        )

        return JsonResponse({
            'status': 'success',
            'message': f'Hold request denied for seat {seat.seat_number}.'
        })

    except SeatHoldRequest.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Pending hold request not found.'}, status=404)

    except Exception as e:
        print("manage_hold_request_api error:", str(e))
        return JsonResponse({'status': 'error', 'message': 'Internal server error.'}, status=500)
    

@login_required
@user_passes_test(lambda u: u.is_staff)
def teacher_put_seat_on_hold_api(request):
    """
    TEACHER-ONLY API: Directly put a seat on hold without restrictions
    PERMISSIONS: 
    - No date restrictions (can start from today)
    - No duration restrictions (can hold for any number of days)
    
    POST body:
    {
        "seat_id": <int>,
        "start_date": "YYYY-MM-DD",
        "duration": "X days" or "X months Y days",
        "reason": "Optional reason for putting on hold"
    }
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

    if not request.user.is_staff:
        return JsonResponse({'status': 'error', 'message': 'Only teachers can use this API.'}, status=403)

    try:
        data = json.loads(request.body or '{}')
        seat_id = data.get('seat_id')
        start_date_str = data.get('start_date')
        duration = (data.get('duration') or '').strip()
        reason = (data.get('reason') or 'Teacher initiated hold').strip()

        if not seat_id or not start_date_str or not duration:
            return JsonResponse(
                {'status': 'error', 'message': 'Seat ID, start date, and duration are required.'},
                status=400
            )

        # Get seat with lock
        seat = Seat.objects.select_for_update().get(id=seat_id)

        # Seat must be occupied (have active assignment)
        active_assignment = SeatAssignment.objects.filter(
            seat=seat,
            is_active=True
        ).first()

        if not active_assignment:
            return JsonResponse(
                {'status': 'error', 'message': f'Seat {seat.seat_number} is not currently occupied.'},
                status=400
            )

        # Check if already on hold
        if seat.status == 'on_hold':
            return JsonResponse(
                {'status': 'error', 'message': f'Seat {seat.seat_number} is already on hold.'},
                status=400
            )

        # Parse start date
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        except Exception:
            return JsonResponse(
                {'status': 'error', 'message': 'Invalid start date format. Use YYYY-MM-DD.'},
                status=400
            )

        # Parse duration (NO RESTRICTIONS for teachers)
        days = _parse_duration(duration)

        if days < 1:
            return JsonResponse(
                {'status': 'error', 'message': 'Hold duration must be at least 1 day.'},
                status=400
            )

        # Calculate end date (inclusive)
        end_date = start_date + timedelta(days=days - 1)

        today = timezone.now().date()
        student = active_assignment.student

        # Store hold dates on seat
        seat.hold_student = student
        seat.hold_start_date = start_date
        seat.hold_end_date = end_date

        # Store hold dates on assignment
        active_assignment.hold_start_date = start_date
        active_assignment.hold_end_date = end_date

        if start_date <= today:
            # Hold starts today or in the past — activate immediately
            seat.status = 'on_hold'
            seat.hold_status = 'active'
            active_assignment.hold_status = 'active'
            student.status = 'on_hold'
            student.save(update_fields=['status'])
        else:
            # Future hold — keep current status; hold will activate on start_date
            seat.hold_status = 'none'
            active_assignment.hold_status = 'none'
            # student.status remains as-is (admitted / occupied)

        seat.save(update_fields=['status', 'hold_status', 'hold_student', 'hold_start_date', 'hold_end_date'])
        active_assignment.save(update_fields=['hold_status', 'hold_start_date', 'hold_end_date'])

        # Recalculate fee expiry to reflect the upcoming hold
        _recalc_fee_expiry_with_hold(student)

        # Notify the student
        create_notification(
            user=student.user,
            title="Seat Put on Hold",
            message=f"Your seat {seat.seat_number} has been put on hold from {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}. Reason: {reason}",
            link="/dashboard/",
            category="seat"
        )

        return JsonResponse({
            'status': 'success',
            'message': f'Seat {seat.seat_number} has been put on hold successfully.',
            'seat_number': seat.seat_number,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'student_name': student.full_name if student else 'N/A'
        })

    except Seat.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Seat not found.'}, status=404)

    except Exception as e:
        print("teacher_put_seat_on_hold_api error:", str(e))
        return JsonResponse({'status': 'error', 'message': f'Internal error: {str(e)}'}, status=500)


@login_required
@user_passes_test(lambda u: u.is_staff)
def student_details_view(request, student_id):
    # Use select_related('seat') to fetch the seat info in the same query
    student = get_object_or_404(StudentProfile.objects.select_related('seat', 'user'), id=student_id)
    student.has_achievement = StudentAchievement.objects.filter(user=student.user).exists()
    return render(request, 'users/student_details.html', {'student': student})

@login_required
@transaction.atomic
def edit_student_view(request, student_id):
    student = get_object_or_404(StudentProfile, id=student_id)
    
    # Permission Check: Staff can edit anyone, Student can only edit themselves
    if not (request.user.is_staff or (hasattr(request.user, 'profile') and request.user.profile.id == student_id)):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("You do not have permission to edit this profile.")
    
    old_status = student.status
    
    if request.method == 'POST':
        form = EditStudentProfileForm(request.POST, request.FILES, instance=student, user_editing=request.user)
        if form.is_valid():
            updated_student = form.save(commit=False)
            new_status = updated_student.status
            
            # Teachers only: handle status-based logic
            if request.user.is_staff:
                if new_status == 'admitted':
                    updated_student.is_admitted = True
                    updated_student.is_manual_pending = False
                elif new_status == 'pending':
                    updated_student.is_manual_pending = True
                else:
                    updated_student.is_manual_pending = False
            
            updated_student.save()
            
            # Send Email for Profile Update (if edited by staff and not self)
            if request.user.is_staff and request.user != updated_student.user:
                send_html_email(
                    subject="Profile Updated by Administration",
                    to_email=get_user_notification_email(updated_student.user),
                    template="emails/course_update.html",
                    context={
                        "title": "Profile Information Updated",
                        "message": "An administrator has updated your profile information. Please review your details in your dashboard.",
                        "course_name": "User Profile",
                        "action_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                    },
                    fail_silently=True,
                )
            
            # Sync seat and assignment status (Teachers only, or if status changed)
            if request.user.is_staff and student.seat and old_status != new_status:
                if new_status == 'admitted':
                    # Activate pending assignments
                    pending = SeatAssignment.objects.filter(student=student, is_active=False).first()
                    if pending:
                        pending.is_active = True
                        pending.hold_status = 'none'
                        pending.save(update_fields=['is_active', 'hold_status'])
                        pending.sync_student_pointer()
                        pending.recalc_seat_state()
                    
                    # Ensure hold is cleared and fee expiry recalculated
                    _recalc_fee_expiry_with_hold(student)

                    create_notification(
                        user=student.user,
                        title="Admission Approved",
                        message=f"Your admission has been approved! Seat: {student.seat.seat_number}",
                        link="/dashboard/",
                        category="admission"
                    )

                    # Send Admission/Course Enrollment Email
                    send_html_email(
                        subject="Welcome to ABCD! Your Admission is Approved",
                        to_email=get_user_notification_email(student.user),
                        template="emails/course_update.html",
                        context={
                            "title": "Admission & Course Access Granted",
                            "message": f"Welcome to the ABCD family! Your admission is approved and your seat ({student.seat.seat_number}) is ready. You now have full access to our digital courses and library resources.",
                            "course_name": "Full ABCD Curriculum",
                            "action_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                        },
                        fail_silently=True,
                    )
                elif new_status == 'on_hold':
                    # --- HOLD LOGIC ---
                    hold_start_str = request.POST.get('hold_start_date')
                    hold_duration_str = request.POST.get('hold_duration')

                    today_date = timezone.now().date()
                    start_date = today_date
                    end_date = start_date + timedelta(days=29)

                    if hold_start_str and hold_duration_str:
                        try:
                            start_date = datetime.strptime(hold_start_str, "%Y-%m-%d").date()
                            days = _parse_duration(hold_duration_str)
                            if days < 1: days = 1
                            end_date = start_date + timedelta(days=days - 1)
                        except Exception as e:
                            print(f"Error parsing hold details: {e}")

                    # Store hold dates on seat
                    student.seat.hold_student = student
                    student.seat.hold_start_date = start_date
                    student.seat.hold_end_date = end_date

                    active_assignment = SeatAssignment.objects.filter(student=student, is_active=True).first()
                    if active_assignment:
                        active_assignment.hold_start_date = start_date
                        active_assignment.hold_end_date = end_date

                    if start_date <= today_date:
                        # Hold starts today or in the past — activate immediately
                        student.seat.status = 'on_hold'
                        student.seat.hold_status = 'active'
                        student.seat.save(update_fields=['status', 'hold_status', 'hold_student', 'hold_start_date', 'hold_end_date'])
                        if active_assignment:
                            active_assignment.hold_status = 'active'
                            active_assignment.save(update_fields=['hold_status', 'hold_start_date', 'hold_end_date'])
                        # student.status already set to 'on_hold' by form save above
                    else:
                        # Future hold — keep current seat/student status; hold activates on start_date
                        # Revert student status back to previous (don't mark on_hold yet)
                        updated_student.status = old_status
                        student.seat.hold_status = 'none'
                        student.seat.save(update_fields=['hold_status', 'hold_student', 'hold_start_date', 'hold_end_date'])
                        if active_assignment:
                            active_assignment.hold_status = 'none'
                            active_assignment.save(update_fields=['hold_status', 'hold_start_date', 'hold_end_date'])

                    # Recalculate fee expiry to include upcoming hold
                    _recalc_fee_expiry_with_hold(student)

                    create_notification(
                        user=student.user,
                        title="Seat Put on Hold",
                        message=f"Your seat {student.seat.seat_number} has been scheduled on hold from {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}.",
                        link="/dashboard/",
                        category="hold"
                    )
                elif new_status == 'pending':
                    active_assignments = SeatAssignment.objects.filter(student=student, is_active=True)
                    for a in active_assignments:
                        a.is_active = False
                        a.hold_status = 'none'
                        a.save(update_fields=['is_active', 'hold_status'])
                        a.recalc_seat_state()
                    
                    other_active = SeatAssignment.objects.filter(seat=student.seat, is_active=True).exclude(student=student).exists()
                    if not other_active:
                        student.seat.status = 'available'
                        student.seat.hold_status = 'none'
                        student.seat.hold_student = None
                        student.seat.save(update_fields=['status', 'hold_status', 'hold_student'])
                    
                    create_notification(
                        user=student.user,
                        title="Status Changed to Pending",
                        message="Your status has been changed to 'Pending'.",
                        link="/dashboard/",
                        category="admission"
                    )
            
            # If teacher edited profile but status didn't trigger a specific notification → send a general one
            if request.user.is_staff and old_status == new_status:
                create_notification(
                    user=student.user,
                    title="Profile Updated by Teacher",
                    message=f"Your student profile has been updated by a teacher.",
                    link="/dashboard/",
                    category="general"
                )

            messages.success(request, f"Profile for {student.full_name} has been updated.")

            # Redirect back to appropriate details page
            if request.user.is_staff:
                return redirect('users:student_details', student_id=student.id)
            else:
                return redirect('users:student_details_S')
    else:
        form = EditStudentProfileForm(instance=student, user_editing=request.user)

    return render(request, 'users/edit_student.html', {
        'form': form,
        'student': student,
        'is_teacher': request.user.is_staff,
        'base_template': 'users/teacher_dashboard.html' if request.user.is_staff else 'users/student_dashboard.html'
    })


@login_required
def upload_profile_photo(request, student_id):
    student = get_object_or_404(StudentProfile, id=student_id)
    
    # Permission check: Staff or the student themselves
    print(f"DEBUG: upload_profile_photo called for student {student_id}")
    if not request.user.is_staff and student.user != request.user:
        print(f"DEBUG: Permission denied for user {request.user}")
        return HttpResponseForbidden("You are not authorized to perform this action.")
    
    if request.method == 'POST':
        photo_file = request.FILES.get('photo')
        photo_base64 = request.POST.get('photo_base64')
        
        if photo_base64:
            print("DEBUG: Processing base64 photo")
            try:
                import base64
                from django.core.files.base import ContentFile
                format, imgstr = photo_base64.split(';base64,')
                ext = format.split('/')[-1]
                data = ContentFile(base64.b64decode(imgstr), name=f"profile_{student_id}.{ext}")
                student.photo = data
                student.save()
                print("DEBUG: Base64 student saved successfully")
                return JsonResponse({'status': 'success'})
            except Exception as e:
                print(f"DEBUG: Base64 error: {str(e)}")
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
                
        elif photo_file:
            print(f"DEBUG: File received: {photo_file.name}, size: {photo_file.size}")
            try:
                student.photo = photo_file
                student.save()
                print("DEBUG: Student saved successfully")
                return JsonResponse({'status': 'success'})
            except Exception as e:
                print(f"DEBUG: Save error: {str(e)}")
                return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
    print("DEBUG: No file received or not POST")
    return JsonResponse({'status': 'error', 'message': 'No file received'}, status=400)


@login_required
def delete_profile_photo(request, student_id):
    student = get_object_or_404(StudentProfile, id=student_id)
    
    # Permission check: Staff or the student themselves
    if not request.user.is_staff and student.user != request.user:
        return HttpResponseForbidden("You are not authorized to perform this action.")
        
    if request.method == 'POST':
        if student.photo:
            student.photo.delete(save=False)
            student.save()
            messages.success(request, "Profile photo removed.")
        
        # Redirect back to appropriate details page
        if request.user.is_staff:
            return redirect('users:student_details', student_id=student.id)
        else:
            return redirect('users:student_details_S')
            
    return redirect('users:home_page')



@login_required
@user_passes_test(lambda u: u.is_staff)
def approve_student_view(request, student_id):
    """
    Approve a student's admission request.
    
    Protected against:
    - Duplicate rapid requests (5 second deduplication window)
    - Database lock errors (automatic retry with exponential backoff)
    - Race conditions (atomic transactions with retry)
    """
    from users.db_utils import safe_atomic_transaction, deduplicate_request
    
    # Check for duplicate request manually since we need custom handling
    from django.core.cache import cache
    import hashlib
    
    # Create a unique key for this specific approval request
    cache_key = f'approve_student_{student_id}_{request.user.id}'
    
    if cache.get(cache_key):
        # Duplicate request detected
        messages.warning(request, 'This request is already being processed. Please wait.')
        return redirect('users:teacher_dashboard')
    
    # Mark as processing
    cache.set(cache_key, True, 10)  # 10 second lock
    
    try:
        return _do_approve_student(request, student_id)
    finally:
        # Keep lock for 2 more seconds to prevent rapid re-attempts
        cache.set(cache_key, True, 2)


def _do_approve_student(request, student_id):
    """Internal function that performs the actual approval with retry logic."""
    from users.db_utils import safe_atomic_transaction
    from django.db import OperationalError
    
    if request.method == 'POST':
        student = get_object_or_404(StudentProfile, id=student_id)
        is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest' or 'application/json' in request.headers.get('Accept', '')

        # Check for 'skip_seat' flag (passed via query param for "Approve without seat")
        skip_seat = (request.GET.get('skip_seat') == 'true')

        # Use safe_atomic_transaction for retry on database lock
        try:
            with safe_atomic_transaction():
                # --- 🛑 PRE-CHECK CONFLICT DETECTION ---
                # We absolutely must do this BEFORE altering student.status to 'admitted'
                # because changing to admitted silently activates the SeatAssignment during student.save()
                if student.seat is not None and not skip_seat:
                    seat = student.seat
                    shift_type = student.shift or 'full'

                    conflict_assignment = SeatAssignment.objects.filter(
                        seat=seat,
                        is_active=True,
                        shift_type__in=[shift_type, 'full'] if shift_type != 'full' else ['morning', 'evening', 'full']
                    ).exclude(student=student).select_related('student').first()

                    if conflict_assignment:
                        # --- PARTIAL ALLOTMENT EXCEPTION ---
                        # If the conflicting occupant is an OWNER who is ON HOLD and NOT partial,
                        # this student is a temporary tenant — allow the approval as partial.
                        conflict_is_owner_on_hold = (
                            conflict_assignment.hold_status == 'active'
                            and not conflict_assignment.is_partial
                        )
                        if not conflict_is_owner_on_hold:
                            occupier = conflict_assignment.student
                            msg = (
                                f'The {shift_type.capitalize()} shift for this seat is currently occupied '
                                f'by {occupier.full_name}. Please free this seat in the Seat Manager first, '
                                f'or you may approve the student without assigning them a seat.'
                            )
                            if is_ajax:
                                return JsonResponse({
                                    'status': 'conflict',
                                    'message': msg,
                                }, status=409)
                            messages.error(request, f'Seat Conflict: {msg}')
                            return redirect('users:teacher_dashboard')
                        # If we reach here, conflict is owner-on-hold → proceed as partial tenant

                # No conflict! Proceed with standard pipeline.
                if skip_seat and student.seat:
                    seat_to_free = student.seat
                    # Unlink seat from student
                    student.seat = None
                    
                    # If the seat was pending, free it up
                    if seat_to_free.status == 'pending':
                        seat_to_free.status = 'available'
                        seat_to_free.save(update_fields=['status'])

                if student.coaching_pending:
                    student.coaching_pending = False
                    if student.service_type == 'Library':
                        student.service_type = 'Both'
                    else:
                        student.service_type = 'Coaching'
                elif student.library_pending:
                    student.library_pending = False
                    if student.service_type == 'Coaching':
                        student.service_type = 'Both'
                    else:
                        student.service_type = 'Library'

                from django.utils import timezone
                student.status = 'admitted'
                student.is_admitted = True
                student.is_manual_pending = False
                student.approved_at = timezone.now()
                student.save()

                # --- HANDLE SEAT ASSIGNMENT (if exists) ---
                if student.seat is not None:
                    seat = student.seat
                    shift_type = student.shift or 'full'

                    # Detect if this approval is a partial/temporary allotment.
                    # This happens when the seat or the requested shift is currently on hold
                    # by another student (the owner).
                    is_partial_mode = False
                    if seat.status == 'on_hold':
                        is_partial_mode = True
                    else:
                        owner_on_hold = SeatAssignment.objects.filter(
                            seat=seat,
                            is_active=True,
                            hold_status='active',
                            is_partial=False,
                        )
                        if shift_type != 'full':
                            owner_on_hold = owner_on_hold.filter(
                                shift_type__in=[shift_type, 'full']
                            )
                        if owner_on_hold.exists():
                            is_partial_mode = True

                    # Find or create a SeatAssignment record
                    assignment, created = SeatAssignment.objects.get_or_create(
                        seat=seat,
                        student=student,
                        shift_type=shift_type,
                        defaults={
                            'is_active': True,
                            'is_partial': is_partial_mode,
                            'allow_hold_override': is_partial_mode,
                            'hold_status': 'none'
                        }
                    )

                    # If assignment already exists, ensure it is active and partial flag is correct
                    dirty = []
                    if not assignment.is_active:
                        assignment.is_active = True
                        dirty.append('is_active')
                    if created is False and is_partial_mode and not assignment.is_partial:
                        assignment.is_partial = True
                        assignment.allow_hold_override = True
                        dirty.extend(['is_partial', 'allow_hold_override'])
                    if dirty:
                        assignment.save(update_fields=dirty)

                    # Update seat status to occupied only if not on hold
                    if seat.status == 'pending':
                        seat.status = 'occupied'
                        seat.save(update_fields=['status'])

                    # Sync student pointer and recalculate seat state
                    assignment.sync_student_pointer()
                    assignment.recalc_seat_state()
                    
                    # Send the specific seat approval notification
                    notifications.send_admission_approval_notifications(student, seat=seat)
                    messages.success(request, f'Student {student.full_name} approved and seat {seat.seat_number} confirmed.')
                else:
                    # This handles coaching students or library students approved without a seat
                    notifications.send_admission_approval_notifications(student)
                    messages.success(request, f'Student {student.full_name} approved.')
                    
                create_notification(
                    user=student.user,
                    title="Admission Approved",
                    message="Your admission has been approved. You now have full access.",
                    category="admission"
                )

            if is_ajax:
                return JsonResponse({'status': 'success', 'message': 'Student approved successfully.'})
            return redirect('users:teacher_dashboard')
            
        except OperationalError as e:
            # If we still get a database error after retries, show friendly message
            if 'database is locked' in str(e).lower():
                err_msg = 'Server is busy processing requests. Please try again in a moment.'
            else:
                err_msg = f'An error occurred: {str(e)}'
            
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': err_msg}, status=500)
            messages.error(request, err_msg)
            return redirect('users:teacher_dashboard')
    return HttpResponseForbidden('Only POST allowed')


@login_required
@user_passes_test(lambda u: u.is_staff)
@staff_member_required
def delete_student_view(request, student_id):
    """
    Teacher-only view to delete a student's service or completely wipe them.
    Supports granular deletion via 'delete_scope' POST parameter.
    """
    if request.method == 'POST':
        delete_scope = request.POST.get('delete_scope', 'complete')  # alumni, admission, complete
        
        def decouple_chats_for_achievement(ach):
            from .models import GuidanceRequest, ChatSession
            reqs = GuidanceRequest.objects.filter(alumni=ach)
            for r in reqs:
                try:
                    session = getattr(r, 'chat_session', None)
                    if session:
                        session.user_one = r.student
                        session.user_two = ach.user
                        session.request = None
                        session.save()
                except Exception:
                    pass

        with transaction.atomic():
            # Handle user lookup by either student_id (StudentProfile PK) or potentially User PK
            # If student_id is from StudentProfile:
            student = StudentProfile.objects.filter(id=student_id).select_related('user', 'seat').first()
            achievement = None
            user = None

            if student:
                user = student.user
                achievement = StudentAchievement.objects.filter(user=user).first()
            else:
                # Try finding by User ID if student profile not found (might be only alumni)
                user = get_object_or_404(User, id=student_id)
                achievement = StudentAchievement.objects.filter(user=user).first()

            full_name = student.full_name if student else (f"{achievement.first_name} {achievement.last_name}" if achievement else user.username)

            next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('users:teacher_dashboard')
            # Prevent 404 crash: never redirect back to the student details page of a deleted student
            if next_url and (f"/teacher/student/{student_id}" in next_url or f"/student/{student_id}" in next_url):
                next_url = reverse('users:teacher_dashboard')

            if delete_scope == 'alumni' and achievement:
                decouple_chats_for_achievement(achievement)
                if achievement.photo:
                    achievement.photo.delete(save=False)
                achievement.delete()
                messages.success(request, f"Alumni record for {full_name} deleted.")
                return redirect(next_url)

            elif delete_scope == 'admission' and student:
                # 2. Get all seats this student is currently assigned to or interested in
                involved_seat_ids = set()
                if student.seat_id:
                    involved_seat_ids.add(student.seat_id)
                
                assignments = SeatAssignment.objects.filter(student=student)
                for sa in assignments:
                    involved_seat_ids.add(sa.seat_id)
                
                # 3. Explicitly clear Seat holds
                Seat.objects.filter(hold_student=student).update(
                    hold_student=None, 
                    status='available', 
                    hold_status='none',
                    hold_start_date=None,
                    hold_end_date=None
                )
                
                if student.photo:
                    student.photo.delete(save=False)
                student.delete() # Only delete the admission profile
                
                # Recalculate seats
                for seat_id in involved_seat_ids:
                    if seat_id:
                        try:
                            s = Seat.objects.get(id=seat_id)
                            s.recalculate_status()
                        except: pass
                
                messages.success(request, f"Admission record for {full_name} deleted.")
                return redirect(next_url)

            else: # Complete wipe
                if user:
                    # Explicitly clear Seat holds if this student is the hold owner
                    if student:
                        Seat.objects.filter(hold_student=student).update(
                            hold_student=None, 
                            status='available', 
                            hold_status='none',
                            hold_start_date=None,
                            hold_end_date=None
                        )
                    # Delete profiles to push them back to guest page
                    if student:
                        if student.photo:
                            student.photo.delete(save=False)
                        student.delete()
                    if achievement:
                        decouple_chats_for_achievement(achievement)
                        if achievement.photo:
                            achievement.photo.delete(save=False)
                        achievement.delete()
                    messages.success(request, f"Student {full_name} admission and achievements deleted. Account preserved as guest.")
                else:
                    messages.error(request, "Student not found.")
                
                return redirect(next_url)

    return HttpResponseForbidden('Only POST allowed')


@login_required
@user_passes_test(lambda u: u.is_staff)
def fee_calendar_view(request, student_id):
    student = get_object_or_404(StudentProfile, id=student_id)
    
    try:
        selected_year = int(request.GET.get('year', datetime.now().year))
    except ValueError:
        selected_year = datetime.now().year

    payments = Payment.objects.filter(student=student, year=selected_year)
    payment_data = {p.month: p for p in payments}
    all_months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    
    MONTH_NUM = {
        "January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
        "July":7,"August":8,"September":9,"October":10,"November":11,"December":12
    }
    calendar_data = []
    for month_name in all_months:
        calendar_data.append({
            'month_name': month_name,
            'month_num': MONTH_NUM[month_name],
            'payment': payment_data.get(month_name),
        })

    # Build a list of all paid entries (all years) so JS can compute the range highlight
    import json as _json
    _month_num_map = {
        "January":1,"February":2,"March":3,"April":4,"May":5,"June":6,
        "July":7,"August":8,"September":9,"October":10,"November":11,"December":12
    }
    # Sort by year and then month number
    all_payments_qs = Payment.objects.filter(student=student)
    all_payments_list_raw = list(all_payments_qs)
    all_payments_list_raw.sort(key=lambda p: (int(p.year), _month_num_map.get(p.month, 1)))

    all_payments_list = []
    for p in all_payments_list_raw:
        if p.date_paid:
            all_payments_list.append({
                "date": p.date_paid.strftime("%Y-%m-%d"),
                "year": int(p.year) if isinstance(p.year, str) else p.year,
                "month_num": _month_num_map.get(p.month, 1),
                "month_name": p.month,
                "amount": float(p.amount) if p.amount is not None else 0.0,
            })
    all_payments_json = _json.dumps(all_payments_list)
    expiry_date_json = _json.dumps(student.fee_expiry_date.strftime("%Y-%m-%d") if student.fee_expiry_date else None)

    context = {
        'student': student,
        'calendar_data': calendar_data,
        'selected_year': selected_year,
        'year_range': range(datetime.now().year - 5, datetime.now().year + 6),
        'all_payments_json': all_payments_json,
        'expiry_date_json': expiry_date_json,
        'hold_periods_json': _json.dumps(get_student_hold_periods(student)),
    }
    return render(request, 'users/fee_calendar.html', context)


def get_student_hold_periods(student):
    """
    Returns a list of {start, end} date-string dicts representing actual hold
    periods for this student. Only includes periods where the hold has actually
    started (start_date <= today). For currently active holds, end = today.
    """
    from datetime import date
    from django.utils import timezone

    today = timezone.now().date()
    periods = []

    # 1) Check SeatAssignment-level holds (shift-level holds)
    assignments = SeatAssignment.objects.filter(
        student=student,
        hold_start_date__isnull=False,
    ).exclude(hold_status='none')
    for a in assignments:
        start = a.hold_start_date
        if start > today:
            continue  # Future hold — hasn't started yet
        if a.hold_status == 'active':
            # Use planned end date for active holds to extend expiry immediately
            end = a.hold_end_date or today
        else:
            # Hold ended — use stored end date, or start if no end
            end = a.hold_end_date or start
            # If hold ended before it started (edge case), skip
            if end < start:
                continue
        periods.append({
            'start': start.strftime('%Y-%m-%d'),
            'end': end.strftime('%Y-%m-%d'),
        })

    # 2) Check Seat-level holds (legacy/master hold via Seat model)
    if student.seat:
        seat = student.seat
        if seat.hold_student_id == student.id and seat.hold_start_date and seat.hold_status != 'none':
            start = seat.hold_start_date
            if start <= today:
                if seat.status == 'on_hold' and seat.hold_status == 'active':
                    # Use planned end date for active holds
                    end = seat.hold_end_date or today
                else:
                    end = seat.hold_end_date or start
                if end >= start:
                    # Only add if not already covered by assignment-level
                    seat_period = {
                        'start': start.strftime('%Y-%m-%d'),
                        'end': end.strftime('%Y-%m-%d'),
                    }
                    if seat_period not in periods:
                        periods.append(seat_period)

    return periods


def _parse_duration(duration_str):
    """
    Unified helper to parse duration strings like '10', '10 days', '1 month' into total days.
    """
    if not duration_str:
        return 0
    text = duration_str.lower().strip()
    
    # Try plain number first
    if text.isdigit():
        return int(text)
    
    days = 0
    m = re.search(r'(\d+)\s*month', text)
    d = re.search(r'(\d+)\s*day', text)
    if m: days += int(m.group(1)) * 30
    if d: days += int(d.group(1))
    
    # If no keywords found but has number, assume days
    if days == 0:
        num = re.search(r'(\d+)', text)
        if num:
            days = int(num.group(1))
            
    return days


def calculate_hold_extension_days(student):
    """
    Returns the total number of actual hold days for this student.
    Used to extend the fee expiry date.
    """
    periods = get_student_hold_periods(student)
    total = 0
    for p in periods:
        start = datetime.strptime(p['start'], '%Y-%m-%d').date()
        end = datetime.strptime(p['end'], '%Y-%m-%d').date()
        total += (end - start).days + 1
    return total


def _recalc_fee_expiry_with_hold(student):
    """
    Recalculates fee expiry from the chain rule, then adds hold extension.
    Called when a hold starts/ends to keep expiry in sync.
    """
    from dateutil.relativedelta import relativedelta
    import calendar as cal_mod

    base_year, base_month, base_day = sync_student_fee_chain(student)
    if base_year is not None:
        next_month_date = datetime(base_year, base_month, 1) + relativedelta(months=1)
        _, last_day = cal_mod.monthrange(next_month_date.year, next_month_date.month)
        final_day = min(base_day, last_day)
        student.fee_expiry_date = datetime(next_month_date.year, next_month_date.month, final_day).date()
        
        hold_days = calculate_hold_extension_days(student)
        if hold_days > 0:
            student.fee_expiry_date += timedelta(days=hold_days)
        
        student.save(update_fields=['fee_expiry_date'])
    # If no payments exist, don't touch fee_expiry_date


def sync_student_fee_chain(student):
    """
    Recalculates the implicit 'date_paid' for zero-amount payments based on the highest
    preceding explicit payment's day, creating a 'chain' rule.
    Returns the final (base_year, base_month, base_day) of the highest month to be used for expiry.
    """
    from datetime import datetime
    import calendar
    from django.utils import timezone
    from .models import Payment
    
    month_map = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6, "July": 7, "August": 8,
        "September": 9, "October": 10, "November": 11, "December": 12
    }
    
    all_payments = list(Payment.objects.filter(student=student))
    all_payments.sort(key=lambda p: (int(p.year) if str(p.year).isdigit() else 0, month_map.get(p.month, 1)))
    
    current_settlement_day = None
    max_year = 0
    max_month_num = 0
    max_payment = None
    
    for p in all_payments:
        if p.amount > 0:
            current_settlement_day = p.date_paid.day if p.date_paid else timezone.now().day
        elif current_settlement_day is not None:
            # Sync marked month to chain
            y = int(p.year) if str(p.year).isdigit() else 0
            m = month_map.get(p.month, 1)
            _, last_day = calendar.monthrange(y, m)
            day_to_use = min(current_settlement_day, last_day)
            
            if not p.date_paid or p.date_paid.day != day_to_use:
                p.date_paid = datetime(y, m, day_to_use).date()
                p.save(update_fields=['date_paid'])
        else:
            # No preceding explicit payment exists — default settlement day is 1
            current_settlement_day = 1
            y = int(p.year) if str(p.year).isdigit() else 0
            m = month_map.get(p.month, 1)
            default_date = datetime(y, m, 1).date()
            if not p.date_paid or p.date_paid.day != 1:
                p.date_paid = default_date
                p.save(update_fields=['date_paid'])
            
        max_year = int(p.year) if str(p.year).isdigit() else 0
        max_month_num = month_map.get(p.month, 1)
        max_payment = p
        
    if max_payment:
        return max_year, max_month_num, current_settlement_day if current_settlement_day else (max_payment.date_paid.day if max_payment.date_paid else timezone.now().day)
    return None, None, None

def send_receipt_notifications_async(transaction_id, student_id):
    from django.db import connection, close_old_connections
    close_old_connections()
    try:
        from users.models import FeeTransaction, StudentProfile
        from users.utils.receipt_generator import generate_fee_receipt_pdf
        from users.notifications import send_fee_receipt_whatsapp
        from users.email_service import send_html_email
        from django.conf import settings

        trans = FeeTransaction.objects.get(id=transaction_id)
        stud = StudentProfile.objects.get(id=student_id)

        pdf_buffer = generate_fee_receipt_pdf(trans)
        pdf_content = pdf_buffer.getvalue()
        pdf_filename = f"Fee Receipt {trans.receipt_number}.pdf"

        # WhatsApp PDF Receipt Dispatch
        send_fee_receipt_whatsapp(stud, trans, pdf_content)

        # Prepare attachment tuple for Django EmailMessage: (name, content, mimetype)
        attachments = [(pdf_filename, pdf_content, 'application/pdf')]

        # 2. Email to Student
        stud_email = get_user_notification_email(stud)
        if stud_email:
            student_email_success = send_html_email(
                subject=f"Fee_Receipt_{trans.receipt_number}",
                to_email=stud_email,
                template="emails/student_fee_receipt.html",
                context={
                    "student_name": stud.full_name,
                    "service_details": trans.service_snapshot,
                    "receipt_number": trans.receipt_number,
                },
                attachments=attachments
            )
            if student_email_success:
                trans.email_sent = True
                trans.save(update_fields=['email_sent'])

        # 3. Email to Teacher (Sir Ji)
        if settings.ADMIN_EMAIL:
            pdf_buffer.seek(0)
            send_html_email(
                subject=f"Fee_Receipt_{trans.receipt_number}",
                to_email=settings.ADMIN_EMAIL,
                template="emails/teacher_fee_receipt_alert.html",
                context={
                    "student_name": stud.full_name,
                    "service_details": trans.service_snapshot,
                    "receipt_number": trans.receipt_number,
                },
                attachments=attachments
            )

        pdf_buffer.close()
    except Exception as bg_err:
        import logging
        logging.getLogger(__name__).exception(f"CRITICAL background receipt dispatch failure: {bg_err}")
    finally:
        close_old_connections()


@user_passes_test(lambda u: u.is_staff)
def process_fees_view(request, student_id):
    if request.method != 'POST':
        return HttpResponseForbidden('Only POST allowed')

    from django.utils import timezone
    from users.models import Payment, StudentProfile, FeeTransaction
    from users.utils.receipt_generator import generate_fee_receipt_pdf
    from users.notifications import get_student_service_details
    # sync_student_fee_chain and calculate_hold_extension_days are defined locally in views.py

    try:
        data = json.loads(request.body)
        actions = data.get('actions', [])
        use_default_expiry = data.get('use_default_expiry', True)
        expiry_date_str = data.get('expiry_date')
        save_only = data.get('save_only', False)
        final_dispatch = data.get('final_dispatch', False)

        student = get_object_or_404(StudentProfile, id=student_id)
        
        notification_details = []
        details_list_dicts = []
        selected_year_for_notification = None 
        
        month_map = {
            "January": 1, "February": 2, "March": 3, "April": 4,
            "May": 5, "June": 6, "July": 7, "August": 8,
            "September": 9, "October": 10, "November": 11, "December": 12
        }

        latest_year = 0
        latest_month_num = 0
        explicit_day = None

        # Pre-scan for explicit day
        for action_data in actions:
            if action_data.get('action') in ['add_fee', 'edit_fee']:
                pd_str = action_data.get('payment_date')
                if pd_str:
                    explicit_day = datetime.strptime(pd_str, '%Y-%m-%d').day
                    break
        
        if not explicit_day and student.fee_expiry_date:
            explicit_day = student.fee_expiry_date.day
        if not explicit_day:
            explicit_day = timezone.now().day

        for action_data in actions:
            action_type = action_data.get('action')
            
            if action_type == 'clear_expiry':
                student.fee_expiry_date = None
                student.save(update_fields=['fee_expiry_date'])
                return JsonResponse({'status': 'success', 'message': 'Expiry date cleared successfully.'})

            month = action_data.get('month')
            year = action_data.get('year')
            
            year_int = int(year)
            month_num = month_map.get(month, 1)
            
            if year_int > latest_year or (year_int == latest_year and month_num > latest_month_num):
                latest_year = year_int
                latest_month_num = month_num

            if selected_year_for_notification is None:
                selected_year_for_notification = year

            # If we are only building notification details on final dispatch (payments already saved):
            if final_dispatch:
                if action_type in ['add_fee', 'edit_fee']:
                    amount_val = int(action_data.get('amount', 0))
                    payment_date_str = action_data.get('payment_date')
                    payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
                    
                    notification_details.append(
                        f"{month} (₹{amount_val} on {payment_date.strftime('%d-%b-%Y')})"
                    )
                    details_list_dicts.append({
                        "month": month,
                        "year": year,
                        "amount": amount_val,
                        "date": payment_date.strftime('%d %b %Y'),
                        "type": "paid"
                    })
                elif action_type == 'mark_as_paid':
                    payment = Payment.objects.filter(student=student, month=month, year=year).first()
                    p_date = payment.date_paid if payment and payment.date_paid else timezone.now().date()
                    notification_details.append(
                        f"{month} marked as paid on {p_date.strftime('%d %b %Y')}"
                    )
                    details_list_dicts.append({
                        "month": month,
                        "year": year,
                        "amount": 0,
                        "date": p_date.strftime('%d %b %Y'),
                        "type": "marked"
                    })
                elif action_type == 'delete_fee':
                    notification_details.append(
                        f"{month} payment cleared"
                    )
                    details_list_dicts.append({
                        "month": month,
                        "year": year,
                        "amount": 0,
                        "date": "",
                        "type": "deleted"
                    })
            else:
                # Ordinary processing or save_only
                if action_type == 'delete_fee':
                    Payment.objects.filter(student=student, month=month, year=year).delete()
                    notification_details.append(
                        f"{month} payment cleared"
                    )
                    details_list_dicts.append({
                        "month": month,
                        "year": year,
                        "amount": 0,
                        "date": "",
                        "type": "deleted"
                    })
                else:
                    payment, created = Payment.objects.get_or_create(
                        student=student, month=month, year=year, defaults={'amount': 0}
                    )

                    if action_type == 'add_fee':
                        amount_to_add = int(action_data.get('amount', 0))
                        payment_date_str = action_data.get('payment_date')
                        payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
                        
                        payment.date_paid = payment_date
                        payment.amount = F('amount') + amount_to_add
                        payment.save()
                        
                        payment.refresh_from_db()
                        notification_details.append(
                            f"{month} (Added ₹{amount_to_add}, Total: ₹{payment.amount} on {payment_date.strftime('%d-%b-%Y')})"
                        )
                        details_list_dicts.append({
                            "month": month,
                            "year": year,
                            "amount": amount_to_add,
                            "date": payment_date.strftime('%d %b %Y'),
                            "type": "paid"
                        })

                    elif action_type == 'edit_fee':
                        amount_to_edit = int(action_data.get('amount', 0))
                        payment_date_str = action_data.get('payment_date')
                        payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d').date()
                        
                        payment.date_paid = payment_date
                        payment.amount = amount_to_edit
                        payment.save()
                        
                        payment.refresh_from_db()
                        notification_details.append(
                            f"{month} (Edited to ₹{payment.amount} on {payment_date.strftime('%d-%b-%Y')})"
                        )
                        details_list_dicts.append({
                            "month": month,
                            "year": year,
                            "amount": amount_to_edit,
                            "date": payment_date.strftime('%d %b %Y'),
                            "type": "paid"
                        })

                    elif action_type == 'mark_as_paid':
                        if created:
                            import calendar
                            _, last_day = calendar.monthrange(year_int, month_num)
                            day_to_use = min(explicit_day, last_day)
                            payment.date_paid = datetime(year_int, month_num, day_to_use).date()
                            payment.save()
                        notification_details.append(
                            f"{month} marked as paid on {payment.date_paid.strftime('%d %b %Y')}"
                        )
                        details_list_dicts.append({
                            "month": month,
                            "year": year,
                            "amount": 0,
                            "date": payment.date_paid.strftime('%d %b %Y'),
                            "type": "marked"
                        })
        
        is_clear_expiry = any(a.get('action') == 'clear_expiry' for a in actions)
        
        # Calculate and update fee_expiry_date
        if actions and not is_clear_expiry:
            from dateutil.relativedelta import relativedelta
            import calendar
            
            # 1. Run the chain rule to sync all dates properly
            base_year, base_month, base_day = sync_student_fee_chain(student)
            
            if use_default_expiry:
                if base_year is not None:
                    next_month_date = datetime(base_year, base_month, 1) + relativedelta(months=1)
                    _, last_day = calendar.monthrange(next_month_date.year, next_month_date.month)
                    final_day = min(base_day, last_day)
                    
                    student.fee_expiry_date = datetime(next_month_date.year, next_month_date.month, final_day).date()
                    
                    # Extend expiry by actual hold days
                    hold_days = calculate_hold_extension_days(student)
                    if hold_days > 0 and student.fee_expiry_date:
                        student.fee_expiry_date += timedelta(days=hold_days)
                else:
                    student.fee_expiry_date = None
                
                student.save()
            elif expiry_date_str:
                student.fee_expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                student.save()
        else:
            # Direct edit of expiry date without fee actions
            if expiry_date_str:
                student.fee_expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d').date()
                student.save()
                if save_only:
                    return JsonResponse({
                        'status': 'success',
                        'message': 'Expiry date updated successfully!',
                        'fee_expiry_date': student.fee_expiry_date.strftime('%d %b %Y') if student.fee_expiry_date else 'Not Set'
                    })
                return JsonResponse({'status': 'success', 'message': 'Expiry date updated successfully!'})

        # If it's a save_only AJAX call from a single month card:
        if save_only:
            return JsonResponse({
                'status': 'success',
                'message': 'Saved successfully',
                'fee_expiry_date': student.fee_expiry_date.strftime('%d %b %Y') if student.fee_expiry_date else 'Not Set'
            })

        if notification_details:
            teacher_name = request.user.username 

            # STUDENT DASHBOARD NOTIFICATION
            today_str = timezone.now().strftime("%d %b %Y")
            details_text = "\n".join(notification_details)

            msg = "Your fee has been submitted successfully.\nCheck your email/WhatsApp to download receipt."
            if not student.user.email:
                msg += "\n\nAdd your email in profile settings to receive receipts."
            if not student.whatsapp_number:
                msg += "\nAdd your WhatsApp number in profile settings to receive receipts."

            create_notification(
                user=student.user,
                title="Fee Submitted Successfully",
                message=msg,
                category="payment",
                link="/dashboard/"
            )

            # --- ABCD NEW ACCOUNTING INTEGRATION ---
            try:
                # 1. Build immutable month snapshots
                fee_snapshots = []
                total_trans_amount = 0
                
                for item in details_list_dicts:
                    # Deriving year suffix (e.g. 2026 -> 26)
                    y_suffix = str(item.get("year"))[-2:]
                    m_display = f"({y_suffix}) {item.get('month')}"
                    amt = item.get("amount")
                    
                    # Requirement: If amount is 0 but marked paid, show "Paid" text in snapshot
                    amt_display = amt if amt > 0 else "Paid"
                    
                    fee_snapshots.append({
                        "month": m_display,
                        "amount": amt_display,
                        "status": "paid"
                    })
                    if isinstance(amt, (int, float)):
                        total_trans_amount += amt

                # 2. Capture snapshots and create transaction
                if fee_snapshots:
                    transaction = FeeTransaction.objects.create(
                        student=student,
                        teacher=request.user,
                        receipt_number=FeeTransaction.generate_receipt_number(),
                        payment_date=timezone.now().date(),
                        expiry_date=student.fee_expiry_date,
                        service_snapshot=get_student_service_details(student),
                        months_snapshot=fee_snapshots,
                        total_amount=total_trans_amount
                    )

                    # --- ABCD RECEIPT DISPATCH IN BACKGROUND THREAD ---
                    import threading
                    t = threading.Thread(
                        target=send_receipt_notifications_async,
                        args=(transaction.id, student.id)
                    )
                    t.daemon = True
                    t.start()
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"CRITICAL: FeeTransaction creation failed: {e}")

        return JsonResponse({
            'status': 'success',
            'message': f'Successfully processed {len(notification_details)} month(s). Notifications are being sent in the background.'
        })

    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"Error in process_fees_view: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
@login_required
@user_passes_test(lambda u: u.is_staff)
def delete_payment_view(request, student_id, year, month_name):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)
    
    try:
        payment = get_object_or_404(
            Payment,
            student_id=student_id,
            year=year,
            month=month_name
        )
        student = payment.student
        payment.delete()
        
        # Recalculate expiry date
        from dateutil.relativedelta import relativedelta
        import calendar
        from django.utils import timezone
        
        base_year, base_month, base_day = sync_student_fee_chain(student)
        
        if base_year is not None:
            next_month_date = datetime(base_year, base_month, 1) + relativedelta(months=1)
            _, last_day = calendar.monthrange(next_month_date.year, next_month_date.month)
            final_day = min(base_day, last_day)
            
            student.fee_expiry_date = datetime(next_month_date.year, next_month_date.month, final_day).date()
            # Extend expiry by actual hold days
            hold_days = calculate_hold_extension_days(student)
            if hold_days > 0:
                student.fee_expiry_date += timedelta(days=hold_days)
        else:
            student.fee_expiry_date = None
            
        student.save()
        
        student.save()

        return JsonResponse({
            'status': 'success',
            'message': f'{month_name} {year} has been cleared.'
        })
    
    except Payment.DoesNotExist:
        return JsonResponse({
            'status': 'success',
            'message': 'No payment record found to clear.'
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    
# ======================================================
# VIEW: Teacher Broadcast Message
@login_required
@user_passes_test(is_teacher)
def teacher_broadcast_view(request):
    if request.method == "POST":

        # -----------------------------
        # STEP 1: INPUT & BASIC VALIDATION
        # -----------------------------
        message_type = request.POST.get("message_type", "broadcast").strip()
        banner_type = request.POST.get("banner_type", "text").strip()
        
        subject = request.POST.get("subject", "").strip()
        message = request.POST.get("message", "").strip()
        is_draft = request.POST.get("save_draft") == "true"
        
        # For Banner Image mode OR Text mode, resolve image file if uploaded or attached
        banner_image_file = request.FILES.get("banner_image")
        if not banner_image_file and message_type == "banner":
            attachments_list = request.FILES.getlist("attachments")
            if attachments_list:
                for att in attachments_list:
                    ext = os.path.splitext(att.name)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                        banner_image_file = att
                        break
                if not banner_image_file and attachments_list:
                    banner_image_file = attachments_list[0]

        if message_type == "banner":
            if banner_type == "text":
                banner_subj_text = request.POST.get("banner_subject_text", "").strip()
                banner_msg_text = request.POST.get("banner_message_text", "").strip()
                if banner_subj_text:
                    subject = banner_subj_text
                if banner_msg_text:
                    message = banner_msg_text
            elif banner_type == "image":
                if not subject:
                    subject = "Ad Banner"
                if not message:
                    message = subject

        if not subject or (message_type == "broadcast" and not message):
            return JsonResponse({"status": "error", "message": "Subject and message are required."}, status=400)

        # Parse CTA Buttons
        banner_buttons = []
        raw_buttons = request.POST.get("banner_buttons")
        if raw_buttons:
            try:
                banner_buttons = json.loads(raw_buttons)
            except Exception:
                banner_buttons = []

        # Targeting Parameters (Required for creation)
        target_group = request.POST.get("target_group")
        selected_floors = request.POST.getlist("floors")
        selected_batches = request.POST.getlist("batches")
        selected_user_ids = request.POST.getlist("selected_user_ids[]") or request.POST.getlist("selected_users")
        
        send_whatsapp = request.POST.get("send_whatsapp") == "on"
        send_email = request.POST.get("send_email") == "on"
        
        # Scheduling
        schedule_date = request.POST.get("schedule_date")
        schedule_time = request.POST.get("schedule_time")
        send_at = None
        status = "sent"
        if schedule_date and schedule_time:
            dt_str = f"{schedule_date} {schedule_time}"
            send_at = parse_flexible_datetime(dt_str)
            if send_at:
                status = "scheduled"
            else:
                return JsonResponse({"status": "error", "message": "Invalid date/time format."}, status=400)

        item_label = "Ads Banner" if message_type == "banner" else "Broadcast"

        # -----------------------------
        # SPAM PROTECTION (IMMEDIATE SENDS ONLY)
        # -----------------------------
        if not is_draft and status == "sent":
            last_b = BroadcastMessage.objects.filter(
                sender=request.user,
                is_draft=False,
                status="sent"
            ).order_by('-created_at').first()
            if last_b:
                elapsed = (timezone.now() - last_b.created_at).total_seconds()
                if elapsed < 10:
                    remaining = max(1, int(10 - elapsed))
                    return JsonResponse({
                        "status": "error",
                        "message": f"Please wait {remaining} second(s) before sending another immediate {item_label.lower()} (10-second anti-spam cooldown)."
                    }, status=429)

        # -----------------------------
        # STEP 2: CREATE BROADCAST / BANNER
        # -----------------------------
        with transaction.atomic():
            broadcast = BroadcastMessage.objects.create(
                sender=request.user,
                subject=subject,
                message=message,
                message_type=message_type,
                banner_type=banner_type if message_type == "banner" else None,
                banner_image=banner_image_file if message_type == "banner" else None,
                banner_buttons=banner_buttons if message_type == "banner" else [],
                target_group=target_group,
                floor=",".join(selected_floors) if isinstance(selected_floors, list) else selected_floors,
                batch=",".join(selected_batches) if isinstance(selected_batches, list) else selected_batches,
                send_whatsapp=send_whatsapp,
                send_email=send_email,
                send_at=send_at,
                status="draft" if is_draft else status,
                is_draft=is_draft,
                is_sent=(not is_draft and status == "sent"),
                selected_ids=selected_user_ids if target_group in ["individuals", "individual_selection"] else None
            )

        # -----------------------------
        # 🚨 STEP 3: IMMEDIATE EXIT FOR DRAFTS
        # -----------------------------
        if is_draft:
            return JsonResponse({
                "success": True,
                "message": "Draft saved successfully"
            })

        # ---------------------------------------------------------
        # --- EVERYTHING BELOW THIS LINE ONLY RUNS FOR NON-DRAFTS ---
        # ---------------------------------------------------------

        # -----------------------------
        # STEP 4: TARGET USERS (HEAVY QUERYING)
        # -----------------------------
        recipient_qs = User.objects.none()
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
            if selected_user_ids:
                recipient_qs = User.objects.filter(id__in=selected_user_ids)

        users = list(recipient_qs.filter(is_staff=False).distinct()[:500])
        recipient_count = len(users)

        if recipient_count == 0:
            return JsonResponse({"status": "error", "message": "No recipients found."}, status=400)

        # -----------------------------
        # STEP 5: ATTACHMENTS & NOTIFICATIONS (HEAVY DB WORK)
        # -----------------------------
        with transaction.atomic():
            from .models import BroadcastAttachment
            attachments = request.FILES.getlist("attachments")
            attachment_links = []
            for att in attachments:
                ba = BroadcastAttachment.objects.create(broadcast=broadcast, file=att)
                attachment_links.append({
                    "name": os.path.basename(ba.file.name),
                    "url": f"{settings.SITE_URL}{ba.file.url}"
                })

            if status == "sent":
                for user in users:
                    notif = Notification.objects.create(
                        user=user,
                        title=subject,
                        message=message,
                        category="general",
                        is_read=False
                    )
                    send_realtime_notification(user.id, {
                        'id': notif.id,
                        'title': subject,
                        'message': message,
                        'category': 'general',
                        'link': '/notifications/',
                    })

        # -----------------------------
        # STEP 6: EMAIL / WHATSAPP (EXTERNAL CALLS)
        # -----------------------------
        if status == "sent":
            failed_ids = []
            site_url = getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/")
            banner_img_url = None
            if broadcast.banner_image:
                u = broadcast.banner_image.url
                banner_img_url = u if u.startswith("http") else f"{site_url}{u}"
            elif attachment_links:
                for att in attachment_links:
                    u = att.get("url", "") if isinstance(att, dict) else str(att)
                    ext = os.path.splitext(u)[1].lower()
                    if ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                        banner_img_url = u if u.startswith("http") else f"{site_url}{u}"
                        break

            if send_email:
                for user in users:
                    u_email = get_user_notification_email(user)
                    if u_email:
                        try:
                            send_html_email(
                                subject=subject,
                                to_email=u_email,
                                template="emails/broadcast_email.html",
                                context={
                                    "subject": subject,
                                    "message": message,
                                    "teacher_name": request.user.get_full_name() or request.user.username,
                                    "dashboard_url": f"{site_url}{reverse('users:student_dashboard')}",
                                    "attachment_links": attachment_links,
                                    "banner_image_url": banner_img_url,
                                    "buttons": broadcast.banner_buttons,
                                },
                                fail_silently=False,
                            )
                        except Exception:
                            failed_ids.append(user.id)

            broadcast.failed_user_ids = failed_ids
            broadcast.save(update_fields=["failed_user_ids"])

            if send_whatsapp:
                from users.notifications import send_broadcast_whatsapp
                whatsapp_targets = []
                for user in users:
                    if hasattr(user, 'profile'):
                        whatsapp_targets.append(user.profile)
                    else:
                        ach = StudentAchievement.objects.filter(user=user).first()
                        if ach:
                            whatsapp_targets.append(ach)
                
                if whatsapp_targets:
                    send_broadcast_whatsapp(whatsapp_targets, subject, message, banner_image_url=banner_img_url, attachments=attachment_links, buttons=broadcast.banner_buttons)

        if status == "scheduled":
            return JsonResponse({
                "status": "success",
                "message": f"{item_label} scheduled successfully!"
            })

        return JsonResponse({
            "status": "success",
            "message": f"{item_label} posted to {recipient_count} recipient(s) successfully!"
        })

        # -----------------------------
        # RESPONSE
        if status == "scheduled":
            return JsonResponse({
                "status": "success",
                "message": "Broadcast scheduled successfully."
            })

        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({
                "status": "success",
                "message": f"Broadcast sent to {recipient_count} recipients successfully."
            })
        
        messages.success(request, f"Broadcast sent to {recipient_count} recipients successfully.")
        return redirect("users:teacher_dashboard")

    # -----------------------------
    # GET REQUEST - PREPARE UI DATA
    # -----------------------------
    from .models import Seat, StudentProfile, StudentAchievement
    
    # Dynamic Floors
    floors = Seat.objects.values_list('floor', flat=True).distinct().order_by('floor')
        
    # Dynamic Batches
    batches = StudentProfile.objects.exclude(batch__isnull=True).exclude(batch='').values_list('batch', flat=True).distinct().order_by('batch')
        
    # Individuals List (Searchable) - Inclusive of all statuses
    library_students = StudentProfile.objects.filter(service_type='Library').select_related('user', 'seat').order_by('full_name')
    coaching_students = StudentProfile.objects.filter(service_type='Coaching').select_related('user').order_by('full_name')
    # We can keep pending_students for backward compatibility if template uses it, but it's redundant now.
    pending_students = StudentProfile.objects.filter(status='pending').select_related('user').order_by('full_name')
    alumni = StudentAchievement.objects.filter(status='approved').select_related('user').order_by('first_name')
    
    return render(request, "users/teacher_broadcast.html", {
        "floors": floors,
        "batches": batches,
        "library_students": library_students,
        "coaching_students": coaching_students,
        "pending_students": pending_students,
        "alumni_list": alumni,
        "subject_suggestions": [
            "General Update", "Holiday Notice", "Fee Reminder", "Class Update",
            "Library Notice", "Exam / Test Info", "Winner Announcement", "Event Invitation",
            "New Resource Available", "Special Offer", "Important Announcement", "Urgent Alert",
        ],
    })

@login_required
@user_passes_test(is_teacher)
def get_drafts_api(request):
    """Returns a list of saved drafts for the current teacher."""
    from .models import BroadcastMessage
    drafts = BroadcastMessage.objects.filter(
        sender=request.user,
        is_draft=True
    ).order_by("-created_at")[:20]
    
    data = []
    for d in drafts:
        data.append({
            "id": d.id,
            "subject": d.subject,
            "message": d.message,
            "message_type": d.message_type or "broadcast",
            "banner_type": d.banner_type or "text",
            "banner_image_url": d.banner_image.url if d.banner_image else None,
            "banner_buttons": d.banner_buttons or [],
            "target_group": d.target_group,
            "floor": d.floor,
            "batch": d.batch
        })
    return JsonResponse({"drafts": data})


@login_required
def get_active_student_banner_api(request):
    """
    Returns the latest active, un-dismissed Ads Banner for the logged-in student.
    """
    from .models import BroadcastMessage, BannerViewLog, StudentProfile, StudentAchievement
    user = request.user

    if user.is_staff:
        return JsonResponse({"status": "success", "has_banner": False})

    target_groups = ["everyone"]
    profile = StudentProfile.objects.filter(user=user).first()
    achievement = StudentAchievement.objects.filter(user=user).first()

    if profile:
        target_groups.append("all_students")
        if profile.is_admitted or profile.status == "admitted":
            target_groups.append("admitted")
        if profile.service_type == "Library":
            target_groups.append("library")
            target_groups.append("library_students")
        elif profile.service_type == "Coaching":
            target_groups.append("coaching")
            target_groups.append("coaching_students")

    if achievement:
        target_groups.append("alumni")

    now = timezone.now()
    dismissed_ids = BannerViewLog.objects.filter(user=user).values_list("broadcast_id", flat=True)

    try:
        process_scheduled_broadcasts()
    except Exception:
        pass

    banners = BroadcastMessage.objects.filter(
        message_type="banner",
        is_draft=False
    ).filter(
        Q(status="sent") | Q(status="scheduled", send_at__lte=now)
    ).filter(
        Q(send_at__isnull=True) | Q(send_at__lte=now)
    ).exclude(id__in=dismissed_ids).order_by("-created_at")

    matching_banner = None
    for b in banners:
        tg = b.target_group
        if tg in target_groups:
            if tg in ["library", "library_students"] and b.floor and profile:
                floors = [f.strip() for f in b.floor.split(",") if f.strip()]
                user_floor = profile.seat.floor if hasattr(profile, "seat") and profile.seat else None
                if floors and user_floor and user_floor not in floors:
                    continue
            if tg in ["coaching", "coaching_students"] and b.batch and profile:
                batches = [bt.strip() for bt in b.batch.split(",") if bt.strip()]
                if batches and profile.batch and profile.batch not in batches:
                    continue
            matching_banner = b
            break
        elif tg in ["individuals", "individual_selection"] and b.selected_ids:
            if str(user.id) in [str(uid) for uid in b.selected_ids]:
                matching_banner = b
                break

    if not matching_banner:
        return JsonResponse({"status": "success", "has_banner": False})

    banner_image_url = None
    if matching_banner.banner_image:
        banner_image_url = matching_banner.banner_image.url

    return JsonResponse({
        "status": "success",
        "has_banner": True,
        "banner": {
            "id": matching_banner.id,
            "subject": matching_banner.subject,
            "message": matching_banner.message,
            "banner_type": matching_banner.banner_type or "text",
            "image_url": banner_image_url,
            "buttons": matching_banner.banner_buttons or [],
            "created_at": matching_banner.created_at.strftime("%b %d, %Y")
        }
    })


@login_required
def dismiss_student_banner_api(request, banner_id):
    """
    Logs student's dismissal of an Ads Banner pop-up.
    """
    from .models import BroadcastMessage, BannerViewLog
    banner = get_object_or_404(BroadcastMessage, id=banner_id, message_type="banner")
    BannerViewLog.objects.get_or_create(broadcast=banner, user=request.user)
    return JsonResponse({"status": "success", "message": "Banner dismissed."})


@login_required
@user_passes_test(is_teacher)
def resend_failed_broadcast(request, broadcast_id):
    broadcast = get_object_or_404(BroadcastMessage, id=broadcast_id, sender=request.user)
    
    failed_ids = broadcast.failed_user_ids or []
    if not failed_ids:
        return JsonResponse({"status": "info", "message": "No failed users to resend."})

    from django.contrib.auth.models import User
    users = User.objects.filter(id__in=failed_ids)
    
    # Re-build attachment links
    attachment_links = []
    for att in broadcast.attachments.all():
        attachment_links.append({
            "name": os.path.basename(att.file.name),
            "url": f"{settings.SITE_URL}{att.file.url}"
        })

    new_failed = []
    for user in users:
        u_email = get_user_notification_email(user)
        if u_email:
            try:
                send_html_email(
                    subject=broadcast.subject,
                    to_email=u_email,
                    template="emails/broadcast_email.html",
                    context={
                        "subject": broadcast.subject,
                        "message": broadcast.message,
                        "teacher_name": request.user.get_full_name() or request.user.username,
                        "dashboard_url": f"{settings.SITE_URL}{reverse('users:student_dashboard')}",
                        "attachment_links": attachment_links,
                    },
                    fail_silently=False,
                )
            except Exception:
                new_failed.append(user.id)

    broadcast.failed_user_ids = new_failed
    broadcast.save(update_fields=["failed_user_ids"])

    return JsonResponse({
        "status": "success", 
        "message": f"Resent to {len(users) - len(new_failed)} users. {len(new_failed)} still failed."
    })

@login_required
@user_passes_test(is_teacher)
def delete_broadcast_view(request, pk):
    from .models import BroadcastMessage
    # TASK 2: Ownership-based security
    broadcast = get_object_or_404(BroadcastMessage, pk=pk, sender=request.user)
    
    # TASK 6: REMOVE legacy attachment references
    # Delete multi-attachments
    for att in broadcast.attachments.all():
        try:
            att.file.delete(save=False)
        except: pass
        
    broadcast.delete()
    return JsonResponse({"status": "success", "message": "Broadcast deleted successfully."})

@login_required
@user_passes_test(is_teacher)
def bulk_delete_broadcasts_view(request):
    if request.method != "POST":
        return JsonResponse({"status": "error", "message": "Method not allowed."}, status=405)
        
    from .models import BroadcastMessage
    import json
    
    # Handle both Form and JSON data
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            ids = data.get("ids", [])
        except:
            return JsonResponse({"status": "error", "message": "Invalid JSON."}, status=400)
    else:
        ids = request.POST.getlist("ids[]") or request.POST.getlist("ids")

    if not ids:
        return JsonResponse({"status": "error", "message": "No broadcasts selected."}, status=400)
    
    # TASK 2: Ownership-based security
    broadcasts = BroadcastMessage.objects.filter(pk__in=ids, sender=request.user)
    count = 0
    for b in broadcasts:
        # TASK 6: REMOVE legacy attachment references
        for att in b.attachments.all():
            try: att.file.delete(save=False)
            except: pass
            
        b.delete()
        count += 1
    return JsonResponse({"status": "success", "message": f"{count} broadcasts deleted successfully."})

# ======================================================
# VIEW: Teacher Broadcast Message History Records

@login_required
@user_passes_test(is_teacher)
def broadcast_history_view(request):
    from django.core.paginator import Paginator
    try:
        from .utils import process_scheduled_broadcasts
        process_scheduled_broadcasts()
    except Exception:
        pass
    
    # Combine sent and failed for 'sent' tab, exclude drafts
    all_qs = BroadcastMessage.objects.filter(sender=request.user, is_draft=False).prefetch_related("attachments").order_by("-created_at")
    
    page_num = request.GET.get('page', 1)
    paginator = Paginator(all_qs, 20)
    page_obj = paginator.get_page(page_num)

    def format_b(b):
        # Resolve target description
        target_desc = b.target_group
        if b.target_group == "individuals" and b.selected_ids:
            target_desc = f"{len(b.selected_ids)} Individuals"
        elif b.target_group == "library":
            target_desc = f"Library (Floor {b.floor})" if b.floor else "Library (All)"
        elif b.target_group == "coaching":
            target_desc = f"Coaching ({b.batch})" if b.batch else "Coaching (All)"
        elif b.target_group == "admitted":
            target_desc = "Admitted Students"
        elif b.target_group == "all_students":
            target_desc = "All Students"
        elif b.target_group == "everyone":
            target_desc = "Everyone (Students + Alumni)"
        elif b.target_group == "alumni":
            target_desc = "Alumni"

        return {
            "id": b.id,
            "subject": b.subject,
            "message": b.message[:150],
            "created_at": timezone.localtime(b.created_at).strftime("%d %b %Y, %I:%M %p"),
            "send_at": timezone.localtime(b.send_at).strftime("%d %b %Y, %I:%M %p") if b.send_at else None,
            "status": b.status,
            # FIX 2 & 3: STRICT cleanup - NO legacy fields, NO fallbacks
            "has_attachment": b.attachments.exists(),
            "attachments": [
                {"name": os.path.basename(att.file.name), "url": att.file.url} 
                for att in b.attachments.all()
            ],
            "target": {
                "group": target_desc.title() if b.target_group not in ['individuals', 'everyone'] else target_desc,
                "floor": b.floor,
                "batch": b.batch,
            },
            "delivery": {
                "whatsapp": b.send_whatsapp,
                "email": b.send_email,
            },
            "failed_count": len(b.failed_user_ids) if b.failed_user_ids else 0
        }

    return JsonResponse({
        "items": [format_b(b) for b in page_obj],
        "has_more": page_obj.has_next()
    })

# ======================================================
# API VIEW: Save Push Subscription
@login_required
@require_POST
def save_push_subscription(request):
    data = json.loads(request.body)

    PushSubscription.objects.update_or_create(
        endpoint=data['endpoint'],
        defaults={
            'user': request.user,
            'keys': data['keys']
        }
    )

    return JsonResponse({'status': 'ok'})
# ======================================================

@login_required
def toggle_material_privacy(request, material_id):
    if request.method == 'POST':
        try:
            material = StudyMaterial.objects.get(id=material_id)
            # Check if user is the teacher of the course
            if request.user.user_type == 'teacher':
                material.is_public = not material.is_public
                material.save()
                return JsonResponse({'success': True, 'is_public': material.is_public})
            return JsonResponse({'success': False, 'error': 'Unauthorized'}, status=403)
        except StudyMaterial.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Material not found'}, status=404)
    return JsonResponse({'success': False, 'error': 'Invalid method'}, status=400)

# ======================================================
# STUDENT ACHIEVEMENTS & ALUMNI SYSTEM VIEWS
# ======================================================

@login_required
@deduplicate_request(timeout=2)
def achievement_form_view(request):
    """Form for students to submit their achievements/selections safely with concurrency protection."""
    achievement = StudentAchievement.objects.filter(user=request.user).first()
    if achievement:
        messages.info(request, "You have already submitted an achievement request.")
        return redirect('users:alumni_dashboard')
    
    if request.method == 'POST':
        form = StudentAchievementForm(request.POST, request.FILES, instance=achievement, user=request.user)
        if form.is_valid():
            try:
                with safe_atomic_transaction():
                    # Re-check inside atomic lock to prevent race condition
                    if StudentAchievement.objects.filter(user=request.user).exists():
                        messages.info(request, "An achievement request has already been submitted for your account.")
                        return redirect('users:alumni_dashboard')

                    obj = form.save(commit=False)
                    obj.user = request.user
                    
                    # Fill disabled fields from StudentProfile if they were not in POST
                    if not form.cleaned_data.get('first_name') or not form.cleaned_data.get('last_name'):
                        prof = StudentProfile.objects.filter(user=request.user).first()
                        if prof:
                            first_name, *rest = (prof.full_name or '').split(' ', 1)
                            obj.first_name = first_name
                            obj.last_name = rest[0] if rest else ''
                            obj.gender = prof.sex.capitalize() if prof.sex else 'Male'
                            if obj.gender not in ['Male', 'Female', 'Other']:
                                obj.gender = 'Male'
                            obj.dob = prof.dob
                    
                    # Dynamic fields: Other Achievements
                    other_titles = request.POST.getlist('other_achievement_title[]')
                    other_years = request.POST.getlist('other_achievement_year[]')
                    others = []
                    for t, y in zip(other_titles, other_years):
                        if t.strip():
                            others.append({'title': t, 'year': y})
                    # Email sync
                    email_val = (form.cleaned_data.get('email') or '').strip()
                    if email_val:
                        obj.email = email_val
                    elif not obj.email:
                        prof = StudentProfile.objects.filter(user=request.user).first()
                        obj.email = (prof.email if prof and prof.email else None) or request.user.email or ''

                    obj.save()
            except Exception as e:
                logger.error(f"Error saving achievement form concurrently: {e}")
                messages.error(request, "An error occurred while saving your achievement. Please try again.")
                return render(request, 'users/achievement_form.html', {
                    'form': form,
                    'achievement': achievement,
                    'other_achievements_data': []
                })
            
            # Send Email to Admin/Teacher (outside lock)
            send_html_email(
                subject="New Alumni Achievement Request",
                to_email=settings.ADMIN_EMAIL,
                template="emails/admin_achievement_request.html",
                context={
                    "student_name": request.user.get_full_name() or request.user.username,
                    "achievement_summary": obj.current_post or "Achievement Submission",
                    "action_url": f"{settings.SITE_URL}{reverse('users:teacher_dashboard')}",
                },
                fail_silently=True,
                run_async=True
            )
            
            from .utils import get_user_dashboard_type
            dtype = get_user_dashboard_type(request.user)
            if dtype != 'student' and not (request.user.is_staff or request.user.is_superuser):
                from django.contrib.auth import logout
                logout(request)
                messages.success(request, "Achievement form submitted successfully! Waiting for teacher approval. Log in again to access your dashboard once approved.")
                return redirect('users:login')
            else:
                messages.success(request, "Achievement details submitted! Waiting for teacher approval.")
                return redirect('users:alumni_dashboard')
    else:
        form = StudentAchievementForm(instance=achievement, user=request.user)
        
    other_achievements_data = achievement.other_achievements if achievement and achievement.other_achievements else []

    return render(request, 'users/achievement_form.html', {
        'form': form,
        'achievement': achievement,
        'other_achievements_data': other_achievements_data
    })

@login_required
def edit_alumni_view(request):
    """Edit profile page for alumni — edits personal details on the
    StudentAchievement without resetting approval status."""
    request.session['active_dashboard'] = 'alumni'
    achievement = StudentAchievement.objects.filter(user=request.user).first()
    if not achievement:
        messages.error(request, "No alumni profile found.")
        return redirect('users:alumni_dashboard')

    if request.method == 'POST':
        form = EditAlumniProfileForm(request.POST, request.FILES, instance=achievement, user_editing=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            
            # Dynamic fields: Other Achievements
            other_titles = request.POST.getlist('other_achievement_title[]')
            other_years = request.POST.getlist('other_achievement_year[]')
            others = []
            for t, y in zip(other_titles, other_years):
                if t.strip():
                    others.append({'title': t, 'year': y})
            obj.other_achievements = others
            
            obj.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('users:achievement_detail', pk=achievement.pk)
    else:
        form = EditAlumniProfileForm(instance=achievement, user_editing=request.user)

    other_achievements_data = achievement.other_achievements if achievement and achievement.other_achievements else []

    return render(request, 'users/edit_alumni.html', {
        'form': form,
        'achievement': achievement,
        'other_achievements_data': other_achievements_data,
        'base_template': 'users/alumni_dashboard.html',
    })

def hall_of_fame_view(request):
    """The consolidated ABCD's Hall Of Fame page with dynamic role-based base template."""
    # Determine the base template to extend
    base_template = 'home_page.html'
    is_teacher = False
    
    if request.user.is_authenticated:
        track_visitor_intent(request.user, "viewed_hall_of_fame")
        is_teacher = request.user.is_staff
        
        if is_teacher:
            base_template = 'users/teacher_dashboard.html'
        else:
            # Check if alumni/achiever
            achievement = StudentAchievement.objects.filter(user=request.user).first()
            if achievement:
                # We use student_dashboard.html as base, but we'll need to handle the alumni navbar in it
                # or create a base_alumni.html. For now, let's stick to the user's requested alumni_dashboard
                # but for these "wrapper" views, we'll use student_dashboard and maybe check context.
                base_template = 'users/student_dashboard.html'
            elif hasattr(request.user, 'profile'):
                base_template = 'users/student_dashboard.html'
            else:
                base_template = 'users/guest_page.html'
    
    # Achievements for everyone
    approved = StudentAchievement.objects.filter(status='approved').order_by('-id')
    
    # For teachers: moderation context (pending requests)
    pending = []
    
    if is_teacher:
        pending = StudentAchievement.objects.filter(status='pending').order_by('-id')

    # Navigation context
    profile = None
    achievement = None
    notifications = []
    unread_count = 0
    if request.user.is_authenticated:
        profile = StudentProfile.objects.filter(user=request.user).first()
        achievement = StudentAchievement.objects.filter(user=request.user).first()
        all_notifs = Notification.objects.filter(user=request.user).order_by('-created_at')
        unread_count = all_notifs.filter(is_read=False).count()
        notifications = all_notifs[:10]

    return render(request, 'users/hall_of_fame.html', {
        'approved': approved,
        'pending': pending,
        'is_teacher': is_teacher,
        'base_template': base_template,
        'profile': profile,
        'nav_achievement': achievement,
        'notifications': notifications,
        'unread_count': unread_count,
    })

@staff_member_required
@require_POST
def delete_achievement(request, pk):
    """Permanently delete an achievement record."""
    achievement = get_object_or_404(StudentAchievement, pk=pk)
    name = f"{achievement.first_name} {achievement.last_name}"
    achievement.delete()
    messages.success(request, f"Deleted achievement record for {name}.")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('users:hall_of_fame')
    return redirect(next_url)

def achievement_detail_view(request, pk):
    """The 'CV-style' beautiful page for a single student's achievements."""
    achievement = get_object_or_404(StudentAchievement, pk=pk)
    
    # Determine the base template to extend
    base_template = 'home_page.html'
    is_teacher = False
    
    if request.user.is_authenticated:
        is_teacher = request.user.is_staff
        if is_teacher:
            base_template = 'users/teacher_dashboard.html'
        else:
            achievement_exists = StudentAchievement.objects.filter(user=request.user).exists()
            if achievement_exists or hasattr(request.user, 'profile'):
                base_template = 'users/student_dashboard.html'
            else:
                base_template = 'users/guest_page.html'

    # Permission check: If not approved, only owner or staff can see it
    if achievement.status != 'approved':
        if not is_teacher and (not request.user.is_authenticated or achievement.user != request.user):
            messages.error(request, "This success story is pending approval.")
            return redirect('users:hall_of_fame')

    # For template logic
    can_see_private = request.user.is_authenticated and (request.user.is_staff or request.user == achievement.user)
    can_edit = request.user.is_authenticated and (request.user.is_staff or request.user == achievement.user)

    if request.user.is_authenticated and request.user == achievement.user and achievement.status == 'approved':
        request.session['active_dashboard'] = 'alumni'

    # Navigation context
    profile = None
    user_achievement = None
    notifications = []
    unread_count = 0
    if request.user.is_authenticated:
        profile = StudentProfile.objects.filter(user=request.user).first()
        user_achievement = StudentAchievement.objects.filter(user=request.user).first()
        all_notifs = Notification.objects.filter(user=request.user).order_by('-created_at')
        unread_count = all_notifs.filter(is_read=False).count()
        notifications = all_notifs[:10]

    return render(request, 'users/achievement_detail.html', {
        'achievement': achievement, # The CV being viewed
        'can_see_private': can_see_private,
        'can_edit': can_edit,
        'base_template': base_template,
        'profile': profile,
        'nav_achievement': user_achievement, # The current user's profile link
        'notifications': notifications,
        'unread_count': unread_count,
    })


@staff_member_required
@require_POST
@deduplicate_request(timeout=2)
def approve_achievement(request, pk):
    from django.utils import timezone
    with safe_atomic_transaction():
        achievement = get_object_or_404(StudentAchievement, pk=pk)
        achievement.status = 'approved'
        achievement.approved_at = timezone.now()
        achievement.save()

    # Send Approval Email to Alumni
    send_html_email(
        subject="Congratulations! Your ABCD Alumni Profile is Approved",
        to_email=get_user_notification_email(achievement.user),
        template="emails/alumni_approval.html",
        context={
            "student_name": achievement.full_name,
            "action_url": f"{settings.SITE_URL}{reverse('users:alumni_dashboard')}",
        },
        fail_silently=True,
    )

    # Send WhatsApp Approval to Alumni
    try:
        from users.notifications import send_alumni_approval_whatsapp
        achievement_title = achievement.exam_passed if hasattr(achievement, 'exam_passed') and achievement.exam_passed else "Achievement"
        send_alumni_approval_whatsapp(achievement, achievement_title)
    except Exception as ae:
        logger.warning(f"Failed to dispatch Alumni WhatsApp: {ae}")

    messages.success(request, f"Approved achievement for {achievement.first_name} {achievement.last_name}!")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('users:hall_of_fame')
    return redirect(next_url)

@staff_member_required
@require_POST
@deduplicate_request(timeout=2)
def reject_achievement(request, pk):
    with safe_atomic_transaction():
        achievement = get_object_or_404(StudentAchievement, pk=pk)
        full_name = achievement.full_name
        achievement.delete()
    messages.warning(request, f"Deleted achievement request for {full_name}. User account preserved as guest.")
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('users:hall_of_fame')
    return redirect(next_url)

# -------------------------------------------------------------------
# STUDENT PROGRESS & PERFORMANCE VIEW
# -------------------------------------------------------------------
@staff_member_required
def student_progress_view(request):
    from .models import PerformanceRecord, StudentScore, StudentProfile, Seat
    from .models import StudentAchievement

    # Get original batches and floors
    batches = [b[0] for b in StudentProfile.BATCH_CHOICES]
    floors = [f[0] for f in Seat.FLOOR_CHOICES]
    
    # Get requested filters
    selected_service = request.GET.get('service', 'All')
    selected_batch = request.GET.get('batch', batches[0] if batches else None) if selected_service == 'Coaching' else None
    selected_floor = request.GET.get('floor', floors[0] if floors else None) if selected_service == 'Library' else None

    # Context key for grouping records
    record_group = selected_batch
    if selected_service == 'Library':
        record_group = selected_floor
    elif selected_service == 'Alumni':
        record_group = 'Alumni'
    elif selected_service == 'All':
        record_group = 'All'

    if request.method == 'POST':
        action = request.POST.get('action', 'save')
        
        if action == 'delete':
            record_id = request.POST.get('record_id')
            PerformanceRecord.objects.filter(id=record_id).delete()
            messages.success(request, "Performance record deleted successfully!")
            return redirect(f"{request.path}?service={selected_service}&batch={selected_batch}&floor={selected_floor}")

        # Save or Update
        record_id = request.POST.get('record_id')
        topic = request.POST.get('topic')
        total_marks = int(request.POST.get('total_marks', 100))
        show_in_percentage = request.POST.get('show_in_percentage') == 'on'
        show_in_marks = request.POST.get('show_in_marks') == 'on'
        post_group = request.POST.get('record_group')

        if record_id:
            record = PerformanceRecord.objects.get(id=record_id)
            record.topic = topic
            record.total_marks = total_marks
            record.show_in_percentage = show_in_percentage
            record.show_in_marks = show_in_marks
            record.save()
            # Clear existing scores for update
            record.scores.all().delete()
        else:
            record = PerformanceRecord.objects.create(
                batch=post_group,
                topic=topic,
                total_marks=total_marks,
                show_in_percentage=show_in_percentage,
                show_in_marks=show_in_marks
            )
            # Auto-cleanup: Keep only 5 latest records for this group
            old_records = PerformanceRecord.objects.filter(batch=post_group).order_by('-created_at')[5:]
            for old in old_records:
                old.delete()

        for key, value in request.POST.items():
            if key.startswith('marks_') and value.strip():
                student_id = key.split('_')[1]
                marks = int(value)
                try:
                    student = StudentProfile.objects.get(id=student_id)
                    StudentScore.objects.create(
                        record=record,
                        student=student,
                        marks_obtained=marks
                    )
                    # 🔔 Notify the student about their updated progress
                    create_notification(
                        user=student.user,
                        title="📊 Progress Updated",
                        message=f"Your marks for '{record.topic}' have been recorded: {marks}/{record.total_marks}.",
                        link="/dashboard/",
                        category="general"
                    )
                    try:
                        notifications.send_student_progress_email(student, record.topic, marks, record.total_marks)
                    except Exception:
                        pass
                except StudentProfile.DoesNotExist:
                    pass

        msg = "Progress updated successfully!" if record_id else "New progress update saved!"
        messages.success(request, msg)
        return redirect(f"{request.path}?service={selected_service}&batch={selected_batch}&floor={selected_floor}")

    # Filter students list
    if selected_service == 'Library':
        students = StudentProfile.objects.filter(
            service_type='Library', 
            status='admitted',
            seat__floor=selected_floor
        ).order_by('full_name')
    elif selected_service == 'Alumni':
        students = StudentAchievement.objects.filter(status='approved').order_by('first_name')
    elif selected_service == 'All':
        coaching_students = list(StudentProfile.objects.filter(service_type='Coaching', status='admitted'))
        library_students = list(StudentProfile.objects.filter(service_type='Library', status='admitted'))
        alumni_students = list(StudentAchievement.objects.filter(status='approved'))
        def _get_student_sort_name(x):
            if hasattr(x, 'full_name') and x.full_name:
                return x.full_name.lower()
            fname = getattr(x, 'first_name', '')
            lname = getattr(x, 'last_name', '')
            return f"{fname} {lname}".strip().lower()
        students = sorted(coaching_students + library_students + alumni_students, key=_get_student_sort_name)
    else:
        # Coaching
        students = StudentProfile.objects.filter(
            service_type='Coaching', 
            batch=selected_batch, 
            status='admitted'
        ).order_by('full_name')

    # Fetch records for the visual leaderboard
    if selected_service == 'All':
        records = PerformanceRecord.objects.all().order_by('-created_at')[:5]
    else:
        records = PerformanceRecord.objects.filter(batch=record_group).order_by('-created_at')[:5]

    today = timezone.now().date()

    # Prepare data for JS
    import json
    records_list = []
    for r in records:
        scores = []
        for s in r.scores.all().order_by('-marks_obtained'):
            st_name = "Unknown"
            if s.student:
                if hasattr(s.student, 'full_name') and s.student.full_name:
                    st_name = s.student.full_name
                else:
                    st_name = f"{getattr(s.student, 'first_name', '')} {getattr(s.student, 'last_name', '')}".strip() or "Unknown"
            scores.append({
                'id': str(s.student.id) if s.student else '',
                'name': st_name,
                'marks': s.marks_obtained
            })
        records_list.append({
            'id': str(r.id),
            'topic': r.topic,
            'total': r.total_marks,
            'percent': r.show_in_percentage,
            'marks': r.show_in_marks,
            'scores': scores
        })

    # Prepare global search data for cross-section lookups
    all_students_qs = StudentProfile.objects.filter(status='admitted').select_related('seat')
    all_alumni_qs = StudentAchievement.objects.filter(status='approved')
    all_records_qs = PerformanceRecord.objects.all()

    global_search_data = {
        'students': [
            {
                'id': s.id,
                'name': s.full_name,
                'service': s.service_type,
                'batch': s.batch or '',
                'floor': s.seat.floor if (s.service_type == 'Library' and s.seat) else ''
            } for s in all_students_qs
        ],
        'alumni': [
            {
                'id': a.id,
                'name': f"{a.first_name} {a.last_name}",
                'service': 'Alumni'
            } for a in all_alumni_qs
        ],
        'records': [
            {
                'id': r.id,
                'topic': r.topic,
                'batch': r.batch
            } for r in all_records_qs
        ]
    }

    context = {
        'students': students,
        'batches': batches,
        'floors': floors,
        'selected_batch': selected_batch,
        'selected_floor': selected_floor,
        'selected_service': selected_service,
        'records': records,
        'record_group': record_group,
        'performance_records_json': json.dumps(records_list),
        'global_search_data_json': json.dumps(global_search_data),
        'has_performance': len(records_list) > 0,
        'today': today,
    }

    return render(request, 'users/student_progress.html', context)


# ======================================================================
# GUIDY – PRIVATE MENTORSHIP MESSAGING SYSTEM
# ======================================================================
from .models import (
    GuidanceRequest, ChatSession, Message, BlockedGuidance,
    RestrictedStudent, GroupChatSession, GroupMessage
)


@login_required
@require_POST
def guidy_seek_guidance(request, alumni_pk):
    """
    Student sends a GuidanceRequest to a specific alumni.
    Blocked students are silently rejected (404 equivalent).
    """
    alumni = get_object_or_404(StudentAchievement, pk=alumni_pk, status='approved')

    # Security: Prevent self-guidance
    if alumni.user == request.user:
        return JsonResponse({'success': False, 'error': 'You cannot request guidance from your own profile.'}, status=400)

    # Security: Prevent blocked students from requesting
    if BlockedGuidance.objects.filter(
        alumni=alumni, student=request.user,
        direction=BlockedGuidance.DIRECTION_ALUMNI
    ).exists():
        return JsonResponse({'success': False, 'error': 'unavailable'}, status=403)

    # Security: Prevent restricted students from re-requesting
    if RestrictedStudent.objects.filter(alumni=alumni, student=request.user).exists():
        return JsonResponse({'success': False, 'error': 'restricted'}, status=403)

    # Check if an inactive ChatSession exists between this student and alumni
    inactive_session = ChatSession.objects.filter(
        request__student=request.user,
        request__alumni=alumni,
        is_active=False
    ).first()

    if inactive_session:
        # Reactivate session and clear ended metadata
        inactive_session.is_active = True
        inactive_session.ended_by = None
        inactive_session.session_ended_at = None
        inactive_session.save(update_fields=['is_active', 'ended_by', 'session_ended_at'])

        req = inactive_session.request
        req.status = 'accepted'
        new_msg = request.POST.get('message', '').strip()
        if new_msg:
            req.message = new_msg
        req.save(update_fields=['status', 'message'])

        # Notify the alumni about the re-engagement
        create_notification(
            user=alumni.user,
            title="🔄 Chat Re-activated",
            message=f"{request.user.get_full_name() or request.user.username} has re-activated the chat session.",
            link="/guidy/",
            category="general"
        )
        return JsonResponse({'success': True, 'status': 'accepted', 'session_id': inactive_session.id})

    # Idempotent: prevent duplicate requests
    req, created = GuidanceRequest.objects.get_or_create(
        student=request.user,
        alumni=alumni,
        defaults={
            'status': 'pending',
            'message': request.POST.get('message', '').strip()
        }
    )

    if not created and req.status == 'rejected':
        # Allow re-request after rejection
        req.status = 'pending'
        req.message = request.POST.get('message', '').strip()
        req.save()

    # 🔔 Notify the alumni about the new/renewed guidance request
    if created or req.status == 'pending':
        create_notification(
            user=alumni.user,
            title="📩 New Guidance Request",
            message=f"{request.user.get_full_name() or request.user.username} has sent you a guidance request.",
            link="/guidy/",
            category="general"
        )

        # Send Email to Alumni
        send_html_email(
            subject="New Guidance Request on Guidy",
            to_email=get_user_notification_email(alumni.user),
            template="emails/guidy_request.html",
            context={
                "student_name": request.user.get_full_name() or request.user.username,
                "request_message": req.message,
                "action_url": f"{settings.SITE_URL}{reverse('users:alumni_dashboard')}",
            },
            fail_silently=True,
            run_async=True
        )

    status = req.status
    session_id = None
    try:
        session_id = req.chat_session.id
    except ChatSession.DoesNotExist:
        pass

    return JsonResponse({'success': True, 'status': status, 'session_id': session_id})


def purge_expired_media():
    """
    Auto-purge: physically deletes attachment files older than 10 days
    to free up disk space on the server.
    """
    from datetime import timedelta
    from django.utils import timezone
    from .models import Message, GroupMessage

    cutoff = timezone.now() - timedelta(days=10)

    # 1. Purge older Message files (ONLY media files, excluding text messages)
    expired_messages = Message.objects.filter(
        media_expired=False,
        timestamp__lt=cutoff
    ).exclude(message_type='text').exclude(file='').exclude(file__isnull=True)

    for msg in expired_messages:
        try:
            if msg.file:
                msg.file.delete(save=False) # Physically deletes from disk
        except Exception:
            pass
        msg.media_expired = True
        msg.file = None # Clear database reference
        msg.save(update_fields=['media_expired', 'file'])

    # 2. Purge older GroupMessage files (ONLY media files, excluding text messages)
    expired_group_messages = GroupMessage.objects.filter(
        media_expired=False,
        timestamp__lt=cutoff
    ).exclude(message_type='text').exclude(file='').exclude(file__isnull=True)

    for gmsg in expired_group_messages:
        try:
            if gmsg.file:
                gmsg.file.delete(save=False)
        except Exception:
            pass
        gmsg.media_expired = True
        gmsg.file = None
        gmsg.save(update_fields=['media_expired', 'file'])


def purge_group_chat_session(group):
    """
    Permanently deletes all group messages, physical media files, group avatar,
    and the GroupChatSession database row.
    """
    try:
        if not group or not group.pk:
            return
        import os
        # 1. Delete all attached files for group messages
        for msg in group.messages.exclude(file='').exclude(file__isnull=True):
            if msg.file:
                try:
                    if os.path.isfile(msg.file.path):
                        os.remove(msg.file.path)
                except Exception:
                    pass
        # 2. Delete group avatar
        if group.photo:
            try:
                if os.path.isfile(group.photo.path):
                    os.remove(group.photo.path)
            except Exception:
                pass
        group.messages.all().delete()
        group.delete()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error purging group chat session: {e}")


def purge_expired_group_chats():
    """
    Auto-purge: permanently deletes group chats that were marked deleted 30+ days ago.
    """
    from datetime import timedelta
    from django.utils import timezone
    from .models import GroupChatSession
    cutoff_30d = timezone.now() - timedelta(days=30)
    expired_groups = GroupChatSession.objects.filter(
        deleted_at__isnull=False,
        deleted_at__lte=cutoff_30d
    )
    for g in expired_groups:
        purge_group_chat_session(g)


def resolve_system_message_content(content, user):
    if content.startswith("system_user:"):
        try:
            parts = content.split(" ", 1)
            user_part = parts[0]  # "system_user:5"
            rest_part = parts[1] if len(parts) > 1 else ""
            actor_id = int(user_part.split(":")[1])
            if actor_id == user.id:
                actor_name = "You"
            else:
                from django.contrib.auth.models import User as DjangoUser
                actor_user = DjangoUser.objects.get(id=actor_id)
                from users.utils import get_user_display_name
                actor_name = get_user_display_name(actor_user)
            return f"{actor_name} {rest_part}"
        except Exception:
            return content
    return content


@login_required
def guidy_home(request):
    """
    Main Guidy interface page.
    - Alumni see pending requests + their active chats
    - Students see their active chats
    - Teachers see direct and group chats
    Handles ?session=<id> to open a specific chat.
    """
    cache.set(f'guidy_presence_{request.user.id}', True, timeout=10)
    purge_expired_media()

    # 20-day Auto-Purge of ended sessions
    from django.db.models import Q
    from .models import ChatSession, DirectChatSession
    ended_sessions = ChatSession.objects.filter(is_active=False, session_ended_at__isnull=False)
    for s in ended_sessions:
        days_passed = (timezone.now() - s.session_ended_at).days
        if days_passed >= 20:
            s.delete()

    ended_direct_sessions = DirectChatSession.objects.filter(is_active=False, session_ended_at__isnull=False)
    for s in ended_direct_sessions:
        days_passed = (timezone.now() - s.session_ended_at).days
        if days_passed >= 20:
            s.delete()

    from users.utils import get_profile_photo_url, get_user_dashboard_type, get_user_display_name
    user = request.user

    # Mark all unread Guidy notifications as read (user is visiting Guidy)
    Notification.objects.filter(
        user=user, category='guidy', is_read=False
    ).update(is_read=True, read_at=timezone.now())

    from datetime import timedelta
    ten_days_ago = timezone.now() - timedelta(days=10)

    is_teacher = user.is_staff or user.is_superuser
    is_alumni = False
    alumni_profile = None
    pending_requests = []
    my_sessions = []
    active_session = None
    locked_days_left = 0
    messages_qs = []
    other_user_name = ''
    other_user_photo = None
    other_type = ''
    other_id = ''

    # Detect alumni role
    try:
        alumni_profile = StudentAchievement.objects.get(user=user, status='approved')
        is_alumni = True
    except StudentAchievement.DoesNotExist:
        pass

    # Detect student role
    is_student = StudentProfile.objects.filter(user=user, status='admitted').exists()

    if is_teacher:
        # Teachers don't have pending_requests or restrictions list
        restriction_list = []
        my_sessions = []
        my_groups = GroupChatSession.objects.filter(
            members=user
        ).filter(
            Q(is_active=True) | Q(is_active=False, deleted_at__isnull=False)
        ).exclude(
            deleted_for_users=user
        ).exclude(name__startswith="__direct__")
    else:
        # For non-teachers (can be student, alumni, or BOTH)
        if is_alumni and alumni_profile:
            pending_requests = GuidanceRequest.objects.filter(
                alumni=alumni_profile, status='pending'
            ).select_related('student')
            restriction_list = RestrictedStudent.objects.filter(
                alumni=alumni_profile
            ).select_related('student')
        else:
            restriction_list = []

        # Query combined chat sessions where they are guide (alumni) OR seeker (student) OR direct user_one/two
        session_filter = Q(user_one=user) | Q(user_two=user)
        if is_alumni and alumni_profile:
            session_filter |= Q(request__alumni=alumni_profile)
        if is_student:
            session_filter |= Q(request__student=user)
        
        # If neither, fallback for guest users
        if not session_filter:
            session_filter = Q(request__student=user)

        my_sessions = ChatSession.objects.filter(
            session_filter
        ).filter(
            Q(is_active=True) | Q(is_active=False, session_ended_at__isnull=False)
        ).exclude(
            is_active=False, ended_by=user
        ).select_related('request__student', 'request__alumni', 'request__alumni__user').distinct()

        # Groups
        my_groups = GroupChatSession.objects.filter(
            members=user
        ).filter(
            Q(is_active=True) | Q(is_active=False, deleted_at__isnull=False)
        ).exclude(
            deleted_for_users=user
        ).exclude(name__startswith="__direct__")

    # Open a specific session if requested
    session_id = request.GET.get('session')
    group_id = request.GET.get('group')
    direct_id = request.GET.get('direct')
    active_group = None
    active_direct = None
    group_messages_qs = []
    group_members_str = ""

    if session_id:
        try:
            active_session = ChatSession.objects.get(id=session_id)
            if not active_session.is_active and active_session.ended_by == user:
                active_session = None

            # Security: ensure user belongs to this chat
            if active_session:
                if active_session.request:
                    is_participant = (
                        active_session.request.student == user or 
                        (alumni_profile and active_session.request.alumni == alumni_profile)
                    )
                    if not is_participant:
                        active_session = None
                else:
                    if user != active_session.user_one and user != active_session.user_two:
                        active_session = None

            if active_session and not active_session.is_active and active_session.session_ended_at:
                days_passed = (timezone.now() - active_session.session_ended_at).days
                locked_days_left = max(0, 20 - days_passed)
                
                # THE AUTO PURGE: If 20 days have passed, permanently delete the session.
                if locked_days_left == 0:
                    for msg in active_session.messages.all():
                        if msg.file:
                            try:
                                msg.file.delete(save=False)
                            except Exception:
                                pass
                    active_session.delete()
                    return redirect('users:guidy_home')

            if active_session:
                messages_qs = list(reversed(active_session.messages.exclude(
                    deleted_by=user
                ).exclude(
                    is_deleted_for_all=True, deleted_at__lt=ten_days_ago
                ).select_related('sender', 'reply_to__sender').order_by('-timestamp')[:50]))

                # Mark all messages from the other party as read
                if active_session.is_active:
                    active_session.messages.exclude(sender=user).update(is_read=True)

                # Other user info (for display)
                if active_session.request:
                    if active_session.request.student == user:
                        # User is student, other user is alumni
                        ach = active_session.request.alumni
                        other_u = ach.user
                        other_type = get_user_dashboard_type(other_u) or 'alumni'
                        other_id = other_u.id if other_type == 'teacher' else ach.id
                        other_user_name = get_user_display_name(other_u)
                        other_user_photo = get_profile_photo_url(other_u)
                    else:
                        # User is alumni, other user is student
                        other_user = active_session.request.student
                        other_type = 'student'
                        other_id = other_user.id
                        other_user_name = other_user.get_full_name() or other_user.username
                        other_user_photo = get_profile_photo_url(other_user)
                else:
                    other_user = active_session.user_two if active_session.user_one == user else active_session.user_one
                    other_type = get_user_dashboard_type(other_user) or 'student'
                    if other_type == 'alumni':
                        ach = StudentAchievement.objects.filter(user=other_user, status='approved').first()
                        other_id = ach.id if ach else other_user.id
                    else:
                        other_id = other_user.id
                    other_user_name = get_user_display_name(other_user)
                    other_user_photo = get_profile_photo_url(other_user)

        except ChatSession.DoesNotExist:
            active_session = None

    elif direct_id:
        try:
            active_direct = DirectChatSession.objects.get(id=direct_id)
            if not active_direct.is_active and active_direct.ended_by == user:
                active_direct = None

            # Security: ensure user belongs to this direct chat
            if active_direct:
                if user != active_direct.user1 and user != active_direct.user2:
                    active_direct = None

            if active_direct and not active_direct.is_active and active_direct.session_ended_at:
                days_passed = (timezone.now() - active_direct.session_ended_at).days
                locked_days_left = max(0, 20 - days_passed)

                # THE AUTO PURGE: If 20 days have passed, permanently delete the session.
                if locked_days_left == 0:
                    for msg in active_direct.messages.all():
                        if msg.file:
                            try:
                                msg.file.delete(save=False)
                            except Exception:
                                pass
                    active_direct.delete()
                    return redirect('users:guidy_home')

            if active_direct:
                messages_qs = list(reversed(active_direct.messages.exclude(
                    deleted_by=user
                ).exclude(
                    is_deleted_for_all=True, deleted_at__lt=ten_days_ago
                ).select_related('sender', 'reply_to__sender').order_by('-timestamp')[:50]))

                # Mark all messages from the other party as read
                if active_direct.is_active:
                    active_direct.messages.exclude(sender=user).update(is_read=True)

                # Other user info (for display)
                other_user = active_direct.user2 if active_direct.user1 == user else active_direct.user1
                other_type = get_user_dashboard_type(other_user) or 'student'
                if other_type == 'alumni':
                    ach = StudentAchievement.objects.filter(user=other_user, status='approved').first()
                    other_id = ach.id if ach else other_user.id
                else:
                    other_id = other_user.id
                other_user_name = get_user_display_name(other_user)
                other_user_photo = get_profile_photo_url(other_user)

        except DirectChatSession.DoesNotExist:
            active_direct = None

    elif group_id:
        try:
            active_group = GroupChatSession.objects.filter(
                id=group_id
            ).filter(
                Q(is_active=True) | Q(is_active=False, deleted_at__isnull=False)
            ).exclude(
                deleted_for_users=user
            ).first()
            if active_group and user not in active_group.members.all() and active_group.created_by != user:
                active_group = None
            if active_group:
                group_messages_qs = list(reversed(active_group.messages.exclude(
                    deleted_by=user
                ).exclude(
                    is_deleted_for_all=True, deleted_at__lt=ten_days_ago
                ).select_related('sender', 'reply_to__sender').order_by('-timestamp')[:50]))
                for gm in active_group.messages.exclude(sender=user):
                    gm.read_by.add(user)

                # Resolve system messages content for templates
                for gm in group_messages_qs:
                    if gm.message_type == 'system':
                        gm.resolved_content = resolve_system_message_content(gm.content, user)
                    else:
                        gm.resolved_content = gm.content

                other_type = 'group'
                other_id = active_group.id
                other_user_name = active_group.name
                other_user_photo = active_group.photo.url if active_group.photo else None

                # Compute comma-separated member names, using 'You' for the current user
                member_names = []
                # Let's ensure the current user 'You' is listed first for a clean feel, followed by others
                has_self = False
                for m in active_group.members.all():
                    if m == user:
                        has_self = True
                    else:
                        member_names.append(get_user_display_name(m))
                member_names.sort() # sort others alphabetically
                if has_self:
                    member_names.insert(0, "You")
                group_members_str = ", ".join(member_names)

        except GroupChatSession.DoesNotExist:
            active_group = None

    # Construct unified_chats for the Chats tab
    unified_chats = []

    # 1. 1-to-1 Mentorship Sessions
    for s in my_sessions:
        if s.request:
            if s.request.student == user:
                other_u = s.request.alumni.user
                name = get_user_display_name(other_u)
                photo_url = get_profile_photo_url(other_u)
            else:
                other_u = s.request.student
                name = other_u.get_full_name() or other_u.username
                photo_url = get_profile_photo_url(other_u)
        else:
            other_u = s.user_two if s.user_one == user else s.user_one
            if other_u:
                name = get_user_display_name(other_u)
                photo_url = get_profile_photo_url(other_u)
            else:
                name = 'Inactive Chat'
                photo_url = None

        last = s.messages.exclude(
            deleted_by=user
        ).exclude(
            is_deleted_for_all=True, deleted_at__lt=ten_days_ago
        ).last()
        last_message = 'deleted msg' if (last and last.is_deleted_for_all) else (last.content if last else '')
        last_message_type = last.message_type if last else 'text'
        last_timestamp = last.timestamp if last else s.created_at

        unread_count = s.messages.filter(
            is_read=False
        ).exclude(
            deleted_by=user
        ).exclude(
            is_deleted_for_all=True
        ).exclude(sender=user).count()

        unified_chats.append({
            'id': s.id,
            'is_group_chat': False,
            'is_direct_group': False,
            'name': name,
            'photo_url': photo_url,
            'last_message': last_message,
            'last_message_type': last_message_type,
            'last_timestamp': last_timestamp,
            'unread_count': unread_count,
            'active': (active_session and active_session.id == s.id),
            'is_verified': other_u.is_staff or other_u.is_superuser,
        })

    # 2. General direct 1-to-1 chats (ChatSession with request=None)
    # 2. General direct 1-to-1 chats (DirectChatSession)
    from django.db.models import Q
    from .models import DirectChatSession
    direct_sessions = DirectChatSession.objects.filter(
        Q(user1=user) | Q(user2=user)
    ).filter(
        Q(is_active=True) | Q(is_active=False, session_ended_at__isnull=False)
    ).exclude(
        is_active=False, ended_by=user
    )
    for s in direct_sessions:
        other_u = s.user2 if s.user1 == user else s.user1
        other_dashboard_type = get_user_dashboard_type(other_u)
        
        name = get_user_display_name(other_u)

        photo_url = get_profile_photo_url(other_u)

        last = s.messages.exclude(
            deleted_by=user
        ).exclude(
            is_deleted_for_all=True, deleted_at__lt=ten_days_ago
        ).last()
        last_message = 'deleted msg' if (last and last.is_deleted_for_all) else (last.content if last else '')
        last_message_type = last.message_type if last else 'text'
        last_timestamp = last.timestamp if last else s.created_at

        unread_count = s.messages.filter(
            is_read=False
        ).exclude(
            deleted_by=user
        ).exclude(
            is_deleted_for_all=True
        ).exclude(sender=user).count()

        is_verified = other_u.is_staff or other_u.is_superuser
        unified_chats.append({
            'id': s.id,
            'is_group_chat': False,
            'is_direct_group': False,  # True 1-on-1 direct chat
            'is_direct_session': True, # Mark this as new direct session
            'name': name,
            'photo_url': photo_url,
            'last_message': last_message,
            'last_message_type': last_message_type,
            'last_timestamp': last_timestamp,
            'unread_count': unread_count,
            'active': (active_direct and active_direct.id == s.id),
            'is_verified': is_verified,
        })

    # Sort unified chats by last message/timestamp
    unified_chats.sort(key=lambda x: x['last_timestamp'], reverse=True)

    # Calculate total chats unread count
    total_chats_unread = sum(c['unread_count'] for c in unified_chats)

    # Notification counts for badge
    guidy_badge = get_guidy_badge_count(user)

    my_photo = get_profile_photo_url(user)
    my_display_name = get_user_display_name(user)
    my_subtext = "Guest User"
    my_teacher_profile = None
    my_emails_list = []
    my_mobiles_list = []
    my_whatsapps_list = []
    
    if is_teacher:
        from users.models import TeacherProfile
        my_teacher_profile, _ = TeacherProfile.objects.get_or_create(user=user)
        my_subtext = my_teacher_profile.role_title or "Teacher"
        my_emails_list = [e.strip() for e in my_teacher_profile.emails.split(',') if e.strip()]
        my_mobiles_list = [m.strip() for m in my_teacher_profile.mobile_numbers.split(',') if m.strip()]
        for w in my_teacher_profile.whatsapp_numbers.split(','):
            w = w.strip()
            if w:
                clean = "".join(c for c in w if c.isdigit())
                my_whatsapps_list.append({'original': w, 'clean': clean})
    elif is_alumni:
        my_subtext = "Alumni Guide"
    else:
        if is_student:
            my_subtext = "Student"

    other_user_active = False
    other_is_verified = False
    is_blocked = False
    if active_direct or active_session:
        if active_direct:
            other_user = active_direct.user2 if active_direct.user1 == request.user else active_direct.user1
        else:
            if active_session.request:
                other_user = active_session.request.student if active_session.request.alumni.user == request.user else active_session.request.alumni.user
            else:
                other_user = active_session.user_two if active_session.user_one == request.user else active_session.user_one
        other_user_active = bool(cache.get(f'guidy_presence_{other_user.id}'))
        other_is_verified = other_user.is_staff or other_user.is_superuser
        from .models import GuidyBlock
        is_blocked = GuidyBlock.objects.filter(blocker=request.user, blocked=other_user).exists()

    # Determine if user has any chat history (for welcome vs returning empty state)
    has_any_chat_history = bool(unified_chats) or \
        GuidanceRequest.objects.filter(
            Q(alumni__user=user) | Q(student=user)
        ).exists() or \
        GroupChatSession.objects.filter(members=user).exists()

    # Fetch teachers' User IDs for direct chat buttons in procedure popups
    from django.contrib.auth.models import User as DjangoUser
    from .models import DirectChatSession
    sandeep_user = DjangoUser.objects.filter(email='abcd2013baq@gmail.com').first()
    asst_user = DjangoUser.objects.filter(email='vd19055@gmail.com').first()
    sandeep_id = sandeep_user.id if sandeep_user else None
    asst_id = asst_user.id if asst_user else None

    sandeep_chatted = False
    asst_chatted = False
    sandeep_photo = None
    asst_photo = None

    if sandeep_user:
        sandeep_chatted = DirectChatSession.objects.filter(
            (Q(user1=user) & Q(user2=sandeep_user)) |
            (Q(user1=sandeep_user) & Q(user2=user)),
            is_active=True
        ).exists()
        sandeep_photo = get_profile_photo_url(sandeep_user)

    if asst_user:
        asst_chatted = DirectChatSession.objects.filter(
            (Q(user1=user) & Q(user2=asst_user)) |
            (Q(user1=asst_user) & Q(user2=user)),
            is_active=True
        ).exists()
        asst_photo = get_profile_photo_url(asst_user)

    # Calculate processed groups with last messages
    my_groups_processed = []
    for g in my_groups:
        last = g.messages.exclude(
            deleted_by=user
        ).exclude(
            is_deleted_for_all=True, deleted_at__lt=ten_days_ago
        ).last()
        
        last_message = ''
        last_message_type = 'text'
        last_timestamp = g.created_at
        last_message_prefix = ''
        
        if last:
            if last.is_deleted_for_all:
                last_message = 'deleted msg'
            elif last.message_type == 'system':
                last_message = resolve_system_message_content(last.content, user)
            else:
                last_message = last.content
            last_message_type = last.message_type
            last_timestamp = last.timestamp
            
            if last.message_type != 'system':
                if last.sender == user:
                    last_message_prefix = 'You: '
                elif last.sender.is_staff or last.sender.is_superuser:
                    last_message_prefix = f"{get_user_display_name(last.sender)}: "
                else:
                    full_name = get_user_display_name(last.sender)
                    first_name = full_name.strip().split(' ')[0] if full_name else last.sender.username
                    last_message_prefix = f"{first_name}: "

        group_unread_count = g.messages.filter(
            is_deleted_for_all=False
        ).exclude(sender=user).exclude(read_by=user).count()
            
        my_groups_processed.append({
            'id': g.id,
            'name': g.name,
            'photo_url': g.photo.url if g.photo else None,
            'last_message': last_message,
            'last_message_type': last_message_type,
            'last_timestamp': last_timestamp,
            'last_message_prefix': last_message_prefix,
            'unread_count': group_unread_count,
        })
        
    my_groups_processed.sort(key=lambda x: x['last_timestamp'], reverse=True)
    total_groups_unread = sum(g['unread_count'] for g in my_groups_processed)

    # Calculate group deletion lifecycle status
    is_deleted_group = False
    group_deleted_by_name = ""
    group_days_left = 30
    if active_group and (not active_group.is_active or active_group.deleted_at):
        is_deleted_group = True
        if active_group.deleted_by_user:
            group_deleted_by_name = get_user_display_name(active_group.deleted_by_user)
        else:
            group_deleted_by_name = "Admin/Teacher"
        if active_group.deleted_at:
            from datetime import timedelta
            delta = timezone.now() - active_group.deleted_at
            group_days_left = max(0, 30 - delta.days)

    context = {
        'has_any_chat_history': has_any_chat_history,
        'is_teacher': is_teacher,
        'is_alumni': is_alumni,
        'is_student': is_student,
        'alumni_profile': alumni_profile,
        'pending_requests': pending_requests,
        'unified_chats': unified_chats,
        'total_chats_unread': total_chats_unread,
        'total_groups_unread': total_groups_unread,
        'my_groups': my_groups_processed,
        'restriction_list': restriction_list,
        'active_session': active_session,
        'active_direct': active_direct,
        'active_group': active_group,
        'is_deleted_group': is_deleted_group,
        'group_deleted_by_name': group_deleted_by_name,
        'group_days_left': group_days_left,
        'group_members_str': group_members_str,
        'locked_days_left': locked_days_left,
        'messages_list': messages_qs,
        'group_messages_list': group_messages_qs,
        'other_user_name': other_user_name,
        'other_user_photo': other_user_photo,
        'other_type': other_type,
        'other_id': other_id,
        'other_user_active': other_user_active,
        'other_is_verified': other_is_verified,
        'is_blocked': is_blocked,
        'guidy_badge': guidy_badge,
        'my_photo': my_photo,
        'my_display_name': my_display_name,
        'my_subtext': my_subtext,
        'my_teacher_profile': my_teacher_profile,
        'my_emails_list': my_emails_list,
        'my_mobiles_list': my_mobiles_list,
        'my_whatsapps_list': my_whatsapps_list,
        'notifications': Notification.objects.filter(user=request.user).order_by("-created_at")[:10],
        'sandeep_id': sandeep_id,
        'asst_id': asst_id,
        'sandeep_chatted': sandeep_chatted,
        'asst_chatted': asst_chatted,
        'sandeep_photo': sandeep_photo,
        'asst_photo': asst_photo,
    }
    return render(request, 'users/guidy.html', context)


@login_required
@require_POST
def guidy_respond(request, request_pk):
    """
    Alumni accepts or rejects a GuidanceRequest.
    On Accept: ChatSession is auto-created.
    """
    guidance_req = get_object_or_404(GuidanceRequest, pk=request_pk)

    # Security: only the alumni whose profile matches can respond
    try:
        alumni_profile = StudentAchievement.objects.get(user=request.user, status='approved')
    except StudentAchievement.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    if guidance_req.alumni != alumni_profile:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    if guidance_req.student == request.user:
        return JsonResponse({'success': False, 'error': 'You cannot respond to guidance requests from yourself.'}, status=400)

    action = request.POST.get('action')  # 'accept' or 'reject'

    if action == 'accept':
        guidance_req.status = 'accepted'
        guidance_req.save()
        session, _ = ChatSession.objects.get_or_create(request=guidance_req)
        # 🔔 Notify student that guidance was accepted
        create_notification(
            user=guidance_req.student,
            title="🎓 Guidance Accepted",
            message=f"{alumni_profile.first_name} has accepted your guidance request. You can now start chatting!",
            link="/guidy/",
            category="general"
        )
        send_realtime_notification(guidance_req.student.id, {
            'title': "🎓 Guidance Accepted",
            'message': f"{alumni_profile.first_name} has accepted your guidance request. Click to open chat!",
            'category': 'guidy',
            'link': "/guidy/"
        })
        # 🔔 Notify alumni about new incoming guidance request (for context in their dashboard)
        create_notification(
            user=guidance_req.alumni.user,
            title="💬 Chat Started",
            message=f"You accepted a guidance request from {guidance_req.student.get_full_name()}. Chat is now active.",
            link="/guidy/",
            category="general"
        )
        return JsonResponse({'success': True, 'action': 'accepted', 'session_id': session.id})

    elif action == 'reject':
        guidance_req.status = 'rejected'
        guidance_req.save()
        # 🔔 Notify student that guidance was rejected
        create_notification(
            user=guidance_req.student,
            title="Guidance Request Declined",
            message=f"Your guidance request to {alumni_profile.first_name} was not accepted at this time.",
            category="general"
        )
        return JsonResponse({'success': True, 'action': 'rejected'})

    return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)


@login_required
@require_POST
def guidy_send_message(request, session_id=None, direct_id=None):
    """
    Sends a message inside an active ChatSession or DirectChatSession.
    Both student and alumni/teachers can send.
    """
    from .models import DirectChatSession
    from users.utils import get_user_display_name, get_profile_photo_url
    user = request.user

    session = None
    direct_session = None

    if session_id:
        session = get_object_or_404(ChatSession, id=session_id, is_active=True)
        if session.request:
            is_participant = (
                session.request.student == user or
                session.request.alumni.user == user
            )
        else:
            is_participant = (
                session.user_one == user or
                session.user_two == user
            )
    elif direct_id:
        direct_session = get_object_or_404(DirectChatSession, id=direct_id, is_active=True)
        is_participant = (
            direct_session.user1 == user or
            direct_session.user2 == user
        )
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    if not is_participant:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    # Determine other participant for block check
    if session:
        if session.request:
            other_user = session.request.alumni.user if session.request.student == user else session.request.student
        else:
            other_user = session.user_two if session.user_one == user else session.user_one
    else:
        other_user = direct_session.user2 if direct_session.user1 == user else direct_session.user1

    from .models import GuidyBlock
    if GuidyBlock.objects.filter(blocker=other_user, blocked=user).exists():
        return JsonResponse({'success': False, 'error': 'You are blocked by this user.'}, status=403)
    if GuidyBlock.objects.filter(blocker=user, blocked=other_user).exists():
        return JsonResponse({'success': False, 'error': 'You have blocked this user. Unblock them to chat.'}, status=403)

    content = request.POST.get('content', '').strip()
    msg_type = request.POST.get('message_type', 'text')
    reply_to_id = request.POST.get('reply_to_id')
    uploaded_file = request.FILES.get('file')

    if uploaded_file:
        ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx', 'txt', 'mp3', 'wav', 'ogg', 'm4a'}
        ALLOWED_MIME_TYPES = {
            'image/jpeg', 'image/png', 'application/pdf', 
            'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
            'text/plain', 'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp4', 'audio/x-m4a'
        }
        ext = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else ''
        if ext not in ALLOWED_EXTENSIONS or uploaded_file.content_type not in ALLOWED_MIME_TYPES:
            return JsonResponse({'success': False, 'error': 'Security blocked: Invalid file type. Only images, PDFs, Word docs, text, and audio files are allowed.'}, status=400)

        if uploaded_file.size > 15 * 1024 * 1024:
            return JsonResponse({'success': False, 'error': 'File exceeds 15MB limit.'}, status=400)

        import datetime
        from django.utils import timezone
        time_limit = timezone.now() - datetime.timedelta(days=1)
        if session:
            media_count = Message.objects.filter(
                session=session,
                sender=user,
                timestamp__gte=time_limit
            ).exclude(file='').exclude(file__isnull=True).count()
        else:
            media_count = Message.objects.filter(
                direct_session=direct_session,
                sender=user,
                timestamp__gte=time_limit
            ).exclude(file='').exclude(file__isnull=True).count()

        if media_count >= 5:
            return JsonResponse({'success': False, 'error': 'Daily media limit (5/day) reached for this chat. Try again tomorrow.'}, status=400)

    if not content and not uploaded_file:
        return JsonResponse({'success': False, 'error': 'Empty message'}, status=400)

    reply_to_obj = None
    if reply_to_id:
        try:
            if session:
                reply_to_obj = Message.objects.get(id=reply_to_id, session=session)
            else:
                reply_to_obj = Message.objects.get(id=reply_to_id, direct_session=direct_session)
        except Message.DoesNotExist:
            pass

    # Determine message type from file
    if uploaded_file:
        ext = uploaded_file.name.rsplit('.', 1)[-1].lower()
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'):
            msg_type = 'image'
        elif ext in ('mp3', 'wav', 'ogg', 'm4a'):
            msg_type = 'audio'
        elif ext in ('mp4', 'webm', 'mov', 'avi'):
            msg_type = 'video'
        else:
            msg_type = 'document'

    msg = Message.objects.create(
        session=session,
        direct_session=direct_session,
        sender=user,
        content=content,
        message_type=msg_type,
        reply_to=reply_to_obj,
        file=uploaded_file if uploaded_file else None,
        file_name=uploaded_file.name if uploaded_file else '',
    )

    # 🔔 Consolidated Guidy notification for the OTHER participant
    try:
        if session:
            if session.request:
                other_user = (
                    session.request.alumni.user
                    if session.request.student == user
                    else session.request.student
                )
            else:
                other_user = session.user_two if session.user_one == user else session.user_one
        else:
            other_user = direct_session.user2 if direct_session.user1 == user else direct_session.user1

        from django.db import models as django_models
        unread_total = Message.objects.filter(
            is_read=False,
            is_deleted_for_all=False,
        ).filter(
            django_models.Q(session__is_active=True) | django_models.Q(direct_session__is_active=True)
        ).filter(
            django_models.Q(session__request__student=other_user) |
            django_models.Q(session__request__alumni__user=other_user) |
            django_models.Q(session__user_one=other_user) |
            django_models.Q(session__user_two=other_user) |
            django_models.Q(direct_session__user1=other_user) |
            django_models.Q(direct_session__user2=other_user)
        ).exclude(sender=other_user)
        unread_count = unread_total.count()
        if unread_count > 0:
            sender_name = get_user_display_name(user)
            notif = Notification.objects.filter(user=other_user, category='guidy', is_read=False).first()
            if notif:
                notif.title = '💬 New Guidy Messages'
                notif.message = f'You have {unread_count} unread message{"s" if unread_count != 1 else ""} in Guidy.'
                notif.link = '/guidy/'
                notif.save()
            else:
                Notification.objects.create(
                    user=other_user,
                    category='guidy',
                    is_read=False,
                    title='💬 New Guidy Messages',
                    message=f'You have {unread_count} unread message{"s" if unread_count != 1 else ""} in Guidy.',
                    link='/guidy/'
                )

            # Fire WhatsApp-style mobile push notification
            push_title = sender_name
            
            if msg.message_type == 'text':
                push_body = msg.content[:60] + '...' if len(msg.content) > 60 else msg.content
            elif msg.message_type == 'image':
                push_body = "📷 Photo"
            elif msg.message_type == 'audio':
                push_body = "🎵 Audio"
            elif msg.message_type == 'video':
                push_body = "🎥 Video"
            else:
                push_body = "📎 Document"
                
            push_url = f"/guidy/?{'direct=' + str(direct_session.id) if direct_session else 'session=' + str(session.id)}"
            threading.Thread(
                target=_send_push_bg,
                args=(other_user, push_title, push_body, push_url),
                daemon=True
            ).start()
    except Exception as e:
        import traceback
        with open('guidy_errors.log', 'a', encoding='utf-8') as f:
            f.write(f"\n--- Guidy Send Message Exception ---\n")
            traceback.print_exc(file=f)

    reply_preview = None
    if reply_to_obj:
        reply_preview = {
            'id': reply_to_obj.id,
            'content': reply_to_obj.content[:80],
            'sender': get_user_display_name(reply_to_obj.sender),
            'type': reply_to_obj.message_type,
        }

    msg_dict = {
        'id': msg.id,
        'content': msg.content,
        'message_type': msg.message_type,
        'file_url': msg.file.url if msg.file else None,
        'file_name': msg.file_name,
        'timestamp': localtime(msg.timestamp).strftime('%H:%M'),
        'date': localtime(msg.timestamp).strftime('%Y-%m-%d'),
        'is_mine': False,
        'is_read': False,
        'sender_name': get_user_display_name(user),
        'sender_photo': get_profile_photo_url(user),
        'reply_to': reply_preview,
        'is_pinned': msg.is_pinned,
        'media_expired': msg.media_expired,
        'is_verified': (msg.sender.is_staff or msg.sender.is_superuser),
    }

    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            c_type = 'group' if group else ('direct' if target_user else 'guidance')
            s_id = group.id if group else (target_user.id if target_user else session.id)
            async_to_sync(channel_layer.group_send)(
                f"guidy_{c_type}_{s_id}",
                {
                    'type': 'chat_message_broadcast',
                    'sender_id': user.id,
                    'message': msg_dict,
                }
            )
    except Exception:
        pass

    sender_msg_dict = dict(msg_dict)
    sender_msg_dict['is_mine'] = True

    return JsonResponse({
        'success': True,
        'message': sender_msg_dict
    })


def get_guidy_badge_count(user):
    """Calculate the total unread messages (direct + mentorship + group) + pending requests for a user."""
    if not user.is_authenticated:
        return 0

    from django.core.cache import cache
    cache_key = f"guidy_badge_count_{user.id}"
    cached_val = cache.get(cache_key)
    if cached_val is not None:
        return cached_val

    from django.db.models import Q
    from users.models import Message as GuidyMessage, GroupMessage, GuidanceRequest, StudentAchievement

    total_badge_count = 0

    # 1. Unread direct/mentorship messages
    unread_direct_count = GuidyMessage.objects.filter(
        is_read=False,
        is_deleted_for_all=False
    ).exclude(sender=user).filter(
        Q(direct_session__is_active=True, direct_session__user1=user) |
        Q(direct_session__is_active=True, direct_session__user2=user) |
        Q(session__is_active=True, session__request__student=user) |
        Q(session__is_active=True, session__request__alumni__user=user) |
        Q(session__is_active=True, session__user_one=user) |
        Q(session__is_active=True, session__user_two=user)
    ).count()
    total_badge_count += unread_direct_count

    # 2. Unread group messages
    unread_group_count = GroupMessage.objects.filter(
        group__is_active=True,
        is_deleted_for_all=False
    ).filter(
        Q(group__members=user) | Q(group__created_by=user)
    ).exclude(sender=user).exclude(read_by=user).distinct().count()
    total_badge_count += unread_group_count

    # 3. Pending guidance requests for approved alumni
    try:
        alumni_ach = StudentAchievement.objects.filter(user=user, status='approved').first()
        if alumni_ach:
            pending_reqs = GuidanceRequest.objects.filter(
                alumni=alumni_ach, status='pending'
            ).count()
            total_badge_count += pending_reqs
    except Exception:
        pass

    try:
        cache.set(cache_key, total_badge_count, 5)  # Cache for 5 seconds
    except Exception:
        pass
    return total_badge_count


@login_required
def guidy_poll_messages(request, session_id=None, direct_id=None):
    """
    Lightweight polling endpoint: returns all messages after a given message id.
    Called every 3 seconds by the frontend JS.
    """
    cache.set(f'guidy_presence_{request.user.id}', True, timeout=10)
    from .models import DirectChatSession
    from users.utils import get_user_display_name, get_profile_photo_url
    user = request.user

    if session_id:
        session = get_object_or_404(ChatSession, id=session_id, is_active=True)
        if session.request:
            is_participant = (
                session.request.student == user or
                session.request.alumni.user == user
            )
        else:
            is_participant = (
                session.user_one == user or
                session.user_two == user
            )
    elif direct_id:
        session = get_object_or_404(DirectChatSession, id=direct_id, is_active=True)
        is_participant = (
            session.user1 == user or
            session.user2 == user
        )
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    if not is_participant:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    after_id = request.POST.get('last_msg_id') or request.GET.get('after', 0)
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0

    from datetime import timedelta
    ten_days_ago = timezone.now() - timedelta(days=10)
    new_msgs = session.messages.filter(
        id__gt=after_id
    ).exclude(
        deleted_by=user
    ).exclude(
        is_deleted_for_all=True, deleted_at__lt=ten_days_ago
    ).select_related('sender', 'reply_to__sender').order_by('timestamp')

    # Mark incoming messages as read
    new_msgs.exclude(sender=user).update(is_read=True)

    data = []
    for msg in new_msgs:
        if msg.is_deleted_for_sender and msg.sender == user:
            continue
        reply_preview = None
        if msg.reply_to:
            reply_preview = {
                'id': msg.reply_to.id,
                'content': msg.reply_to.content[:80],
                'sender': get_user_display_name(msg.reply_to.sender),
                'type': msg.reply_to.message_type,
            }
        data.append({
            'id': msg.id,
            'content': msg.content or ("⏳ Media expired" if msg.media_expired else ""),
            'message_type': msg.message_type,
            'file_url': msg.file.url if msg.file else None,
            'file_name': msg.file_name,
            'timestamp': localtime(msg.timestamp).strftime('%H:%M'),
            'date': localtime(msg.timestamp).strftime('%Y-%m-%d'),
            'is_mine': (msg.sender == user),
            'is_read': msg.is_read,
            'sender_name': get_user_display_name(msg.sender),
            'sender_photo': get_profile_photo_url(msg.sender),
            'is_pinned': msg.is_pinned,
            'reply_to': reply_preview,
            'is_deleted_for_all': msg.is_deleted_for_all,
            'media_expired': msg.media_expired,
            'is_verified': (msg.sender.is_staff or msg.sender.is_superuser),
        })

    # Fetch read message ids sent by request.user
    import json
    pending_ids_str = request.POST.get('pending_read_ids') or request.GET.get('pending_read_ids', '[]')
    try:
        pending_ids = json.loads(pending_ids_str)
    except:
        pending_ids = []

    newly_read = session.messages.filter(id__in=pending_ids, is_read=True).values_list('id', flat=True)

    if direct_id:
        other_user = session.user2 if session.user1 == request.user else session.user1
    else:
        if session.request:
            other_user = session.request.student if session.request.alumni.user == request.user else session.request.alumni.user
        else:
            other_user = session.user_two if session.user_one == request.user else session.user_one
    other_user_active = bool(cache.get(f'guidy_presence_{other_user.id}'))

    return JsonResponse({
        'success': True,
        'messages': data,
        'read_message_ids': list(newly_read),
        'other_user_active': other_user_active,
        'guidy_badge_count': get_guidy_badge_count(user)
    })


@login_required
@require_POST
def guidy_end_session(request, session_id=None, direct_id=None):
    """
    Deactivates a ChatSession or DirectChatSession and purges messages based on user role.
    If Alumni/Teacher/Admin ends it, it deletes all messages in the session.
    If a Student ends it, it only deletes messages sent by the student.
    """
    if direct_id:
        session = get_object_or_404(DirectChatSession, id=direct_id)
        is_participant = (
            session.user1 == request.user or
            session.user2 == request.user
        )
    else:
        session = get_object_or_404(ChatSession, id=session_id)
        # Security check: verify the user is a participant
        if session.request:
            is_participant = (
                session.request.student == request.user or
                session.request.alumni.user == request.user
            )
        else:
            is_participant = (
                session.user_one == request.user or
                session.user_two == request.user
            )

    user = request.user
    if not is_participant and not user.is_staff and not user.is_superuser:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    # Deactivate session and log end metadata
    from django.utils import timezone
    session.is_active = False
    session.ended_by = user
    session.session_ended_at = timezone.now()
    session.save(update_fields=['is_active', 'ended_by', 'session_ended_at'])

    # Determine role logic: staff, admin, or alumni
    is_student = not user.is_staff and not user.is_superuser and getattr(user, 'studentprofile', None) is not None

    if is_student:
        # Student wipe: only delete messages sent by the student
        session.messages.filter(sender=user).delete()
    else:
        # Total wipe: Admin/Alumni ends it, delete all messages
        session.messages.all().delete()

    return JsonResponse({'success': True, 'message': 'Session ended and messages cleared.'})


@login_required
@require_POST
def guidy_restrict_student(request, request_pk):
    """
    Alumni restricts a student — different from blocking.
    Restriction: student cannot send new guidance requests to this alumni.
    Session is NOT closed (restriction is a softer action).
    """
    guidance_req = get_object_or_404(GuidanceRequest, pk=request_pk)
    try:
        alumni_profile = StudentAchievement.objects.get(user=request.user, status='approved')
    except StudentAchievement.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    if guidance_req.alumni != alumni_profile:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    action = request.POST.get('action', 'restrict')  # 'restrict' or 'unrestrict'
    if action == 'unrestrict':
        RestrictedStudent.objects.filter(
            alumni=alumni_profile, student=guidance_req.student
        ).delete()
        return JsonResponse({'success': True, 'action': 'unrestricted'})

    RestrictedStudent.objects.get_or_create(
        alumni=alumni_profile,
        student=guidance_req.student,
        defaults={'reason': request.POST.get('reason', '')}
    )
    return JsonResponse({'success': True, 'action': 'restricted'})


@login_required
@require_POST
def guidy_delete_message(request, session_id=None, msg_id=None, direct_id=None, group_id=None):
    """
    Delete a message:
    - 'for_me': soft-deletes only for the sender
    - 'for_all': hides from both sides/all members (only within 60 minutes of sending)
    """
    from django.utils import timezone as tz
    import datetime
    from .models import DirectChatSession, GroupChatSession, GroupMessage

    user = request.user

    if session_id:
        session = get_object_or_404(ChatSession, id=session_id)
        msg = get_object_or_404(Message, id=msg_id, session=session)
        if session.request:
            is_participant = (
                session.request.student == user or
                session.request.alumni.user == user
            )
        else:
            is_participant = (
                session.user_one == user or
                session.user_two == user
            )
    elif direct_id:
        direct_session = get_object_or_404(DirectChatSession, id=direct_id)
        msg = get_object_or_404(Message, id=msg_id, direct_session=direct_session)
        is_participant = (
            direct_session.user1 == user or
            direct_session.user2 == user
        )
    elif group_id:
        group = get_object_or_404(GroupChatSession, id=group_id, is_active=True)
        msg = get_object_or_404(GroupMessage, id=msg_id, group=group)
        is_participant = user in group.members.all() or group.created_by == user
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    if not is_participant:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    delete_type = request.POST.get('delete_type', 'for_me')  # 'for_me' or 'for_all'

    if delete_type == 'for_all':
        # Only allow within 60 minutes of sending
        age = tz.now() - msg.timestamp
        if age > datetime.timedelta(minutes=60) and msg.sender != user:
            return JsonResponse({'success': False, 'error': 'Time limit exceeded'}, status=400)
        if msg.sender != user:
            return JsonResponse({'success': False, 'error': 'Can only delete your own messages for all'}, status=403)
        if msg.file:
            msg.file.delete(save=False) # Physically deletes file from hard drive to free space
        msg.content = "" # Wipe the text from the database
        msg.file_name = ""
        msg.message_type = "text"
        msg.is_deleted_for_all = True
        msg.deleted_at = tz.now()
        msg.save(update_fields=['content', 'file_name', 'message_type', 'is_deleted_for_all', 'deleted_at'])
    else:
        msg.deleted_by.add(user)
        if not group_id and msg.deleted_by.count() >= 2:
            if msg.file:
                msg.file.delete(save=False)
            msg.delete()

    return JsonResponse({'success': True, 'msg_id': msg_id, 'delete_type': delete_type})


@login_required
@require_POST
def guidy_clear_chat(request, session_id=None, direct_id=None):
    """
    Clears all messages in a specific chat session or direct session for the current user.
    """
    from .models import DirectChatSession
    user = request.user

    if session_id:
        session = get_object_or_404(ChatSession, id=session_id)
        if session.request:
            is_participant = (
                session.request.student == user or
                session.request.alumni.user == user
            )
        else:
            is_participant = (
                session.user_one == user or
                session.user_two == user
            )
    elif direct_id:
        session = get_object_or_404(DirectChatSession, id=direct_id)
        is_participant = (
            session.user1 == user or
            session.user2 == user
        )
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    if not is_participant:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    for msg in session.messages.all():
        msg.deleted_by.add(user)
        if msg.deleted_by.count() >= 2:
            if msg.file:
                msg.file.delete(save=False)
            msg.delete()
    return JsonResponse({'success': True})


@login_required
@require_POST
def guidy_group_clear_chat(request, group_id):
    """
    Clears all messages in a specific group chat session for the current user.
    Adds the user to the deleted_by ManyToManyField of all messages in this group.
    """
    group = get_object_or_404(GroupChatSession, id=group_id, is_active=True)
    if request.user not in group.members.all() and group.created_by != request.user:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    # Simply hide the messages for this specific user. 
    # The 10-day auto-purge will handle physical file deletion safely.
    for msg in group.messages.all():
        msg.deleted_by.add(request.user)
        
    return JsonResponse({'success': True})



@login_required
@require_POST
def guidy_pin_message(request, session_id=None, msg_id=None, direct_id=None, group_id=None):
    """Pin or unpin a message in a chat session, direct session, or group chat."""
    from .models import DirectChatSession, GroupChatSession, GroupMessage
    user = request.user

    if session_id:
        session = get_object_or_404(ChatSession, id=session_id)
        msg = get_object_or_404(Message, id=msg_id, session=session)
        if session.request:
            is_participant = (
                session.request.student == user or
                session.request.alumni.user == user
            )
        else:
            is_participant = (
                session.user_one == user or
                session.user_two == user
            )
    elif direct_id:
        direct_session = get_object_or_404(DirectChatSession, id=direct_id)
        msg = get_object_or_404(Message, id=msg_id, direct_session=direct_session)
        is_participant = (
            direct_session.user1 == user or
            direct_session.user2 == user
        )
    elif group_id:
        group = get_object_or_404(GroupChatSession, id=group_id, is_active=True)
        msg = get_object_or_404(GroupMessage, id=msg_id, group=group)
        is_participant = user in group.members.all() or group.created_by == user
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    if not is_participant:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    msg.is_pinned = not msg.is_pinned
    msg.save(update_fields=['is_pinned'])
    return JsonResponse({'success': True, 'is_pinned': msg.is_pinned, 'msg_id': msg_id})


@login_required
@require_POST
def guidy_star_message(request, session_id=None, msg_id=None, direct_id=None, group_id=None):
    """Star or unstar a message. Tracked per-user."""
    from .models import DirectChatSession, GroupChatSession, GroupMessage
    user = request.user

    if session_id:
        session = get_object_or_404(ChatSession, id=session_id)
        msg = get_object_or_404(Message, id=msg_id, session=session)
        if session.request:
            is_participant = (
                session.request.student == user or
                session.request.alumni.user == user
            )
        else:
            is_participant = (
                session.user_one == user or
                session.user_two == user
            )
    elif direct_id:
        direct_session = get_object_or_404(DirectChatSession, id=direct_id)
        msg = get_object_or_404(Message, id=msg_id, direct_session=direct_session)
        is_participant = (
            direct_session.user1 == user or
            direct_session.user2 == user
        )
    elif group_id:
        group = get_object_or_404(GroupChatSession, id=group_id, is_active=True)
        msg = get_object_or_404(GroupMessage, id=msg_id, group=group)
        is_participant = user in group.members.all() or group.created_by == user
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    if not is_participant:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    if group_id:
        if user in msg.starred_by.all():
            msg.starred_by.remove(user)
            starred = False
        else:
            msg.starred_by.add(user)
            starred = True
    else:
        if msg.sender == user:
            msg.is_starred_by_sender = not msg.is_starred_by_sender
            msg.save(update_fields=['is_starred_by_sender'])
            starred = msg.is_starred_by_sender
        else:
            msg.is_starred_by_receiver = not msg.is_starred_by_receiver
            msg.save(update_fields=['is_starred_by_receiver'])
            starred = msg.is_starred_by_receiver

    return JsonResponse({'success': True, 'is_starred': starred, 'msg_id': msg_id})


@login_required
def guidy_search_messages(request, session_id=None, direct_id=None):
    """Search messages within a chat session or direct session."""
    from django.db.models import Q
    import datetime
    from .models import DirectChatSession

    user = request.user

    if session_id:
        session = get_object_or_404(ChatSession, id=session_id)
        if session.request:
            is_participant = (
                session.request.student == user or
                session.request.alumni.user == user
            )
        else:
            is_participant = (
                session.user_one == user or
                session.user_two == user
            )
    elif direct_id:
        session = get_object_or_404(DirectChatSession, id=direct_id)
        is_participant = (
            session.user1 == user or
            session.user2 == user
        )
    else:
        return JsonResponse({'success': False, 'error': 'Invalid request'}, status=400)

    if not is_participant:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'success': True, 'results': []})

    parsed_date = None
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%y'):
        try:
            parsed_date = datetime.datetime.strptime(q, fmt).date()
            break
        except ValueError:
            pass

    query_filter = Q(content__icontains=q)
    if parsed_date:
        query_filter |= Q(timestamp__date=parsed_date)

    matches = session.messages.filter(
        query_filter,
        is_deleted_for_all=False
    ).order_by('timestamp')[:50]

    results = [{
        'id': m.id,
        'content': m.content,
        'timestamp': localtime(m.timestamp).strftime('%H:%M %d/%m/%Y'),
        'is_mine': (m.sender == user)
    } for m in matches]

    return JsonResponse({'success': True, 'results': results})


@login_required
def guidy_profile_info(request, entity_type, entity_id):
    """
    Returns profile info for the chat header name click.
    entity_type: 'student', 'alumni', 'teacher', 'guest', or 'group'
    """
    from django.db.models import Q as DQ
    from users.utils import get_profile_photo_url, get_user_display_name
    from django.contrib.auth.models import User as DjangoUser

    # 1. Group Chat
    if entity_type == 'group':
        from .models import GroupChatSession
        group = get_object_or_404(GroupChatSession, pk=entity_id)
        members_data = []
        has_teacher_member = False
        for m in group.members.all():
            m_name = get_user_display_name(m)
            m_is_teacher = (m.is_staff or m.is_superuser)
            if m_is_teacher:
                has_teacher_member = True
            members_data.append({
                'id': m.id,
                'name': m_name,
                'photo': get_profile_photo_url(m),
                'is_admin': (m == group.created_by),
                'is_verified': m_is_teacher,
                'is_teacher': m_is_teacher,
            })
            
        # Sort members so that request.user is at the very top of the list
        members_data.sort(key=lambda x: 0 if x['id'] == request.user.id else 1)
            
        group_photo = group.photo.url if getattr(group, 'photo', None) else None
        is_deleted = bool(not group.is_active or group.deleted_at)
        deleted_by_name = get_user_display_name(group.deleted_by_user) if group.deleted_by_user else "Admin/Teacher"
        
        return JsonResponse({
            'success': True,
            'is_group': True,
            'id': group.id,
            'name': group.name,
            'photo': group_photo,
            'role': 'Group Chat',
            'admin_id': group.created_by.id if group.created_by else None,
            'created_at': group.created_at.strftime('%d %b %Y'),
            'description': group.description,
            'members': members_data,
            'has_teacher_member': has_teacher_member,
            'is_deleted': is_deleted,
            'deleted_by_name': deleted_by_name,
        })

    # 2. Teacher
    if entity_type == 'teacher':
        from users.models import TeacherProfile
        teacher_user = get_object_or_404(DjangoUser, id=entity_id)
        profile, _ = TeacherProfile.objects.get_or_create(user=teacher_user)
        photo_url = get_profile_photo_url(teacher_user)
        name = get_user_display_name(teacher_user)
        return JsonResponse({
            'success': True,
            'is_group': False,
            'name': name,
            'photo': photo_url,
            'role': profile.role_title or 'Teacher',
            'detail1': profile.detail1 or '',
            'detail2': profile.detail2 or '',
            'detail3': profile.detail3 or '',
            'about': profile.about or '',
            'emails': profile.emails or '',
            'mobile_numbers': profile.mobile_numbers or '',
            'whatsapp_numbers': profile.whatsapp_numbers or '',
            'member_since': teacher_user.date_joined.strftime('%d %b %Y'),
            'is_verified': True,
        })

    # 3. Alumni
    if entity_type == 'alumni':
        ach = StudentAchievement.objects.filter(DQ(id=entity_id) | DQ(user_id=entity_id), status='approved').first()
        if ach:
            return JsonResponse({
                'success': True,
                'is_group': False,
                'name': ach.full_name,
                'photo': get_profile_photo_url(ach.user),
                'role': 'Alumni Achiever',
                'detail1': ach.current_post or '',
                'detail2': ach.working_city or '',
                'detail3': ach.short_achievement or '',
                'about': ach.about_yourself[:200] if ach.about_yourself else '',
                'member_since': ach.user.date_joined.strftime('%d %b %Y') if ach.user else '',
                'is_verified': False,
            })

    # 4. Student (either by user_id or StudentProfile id)
    if entity_type == 'student':
        from .models import StudentProfile
        profile = StudentProfile.objects.filter(DQ(user_id=entity_id) | DQ(id=entity_id)).first()
        if profile:
            batch_floor = ""
            if profile.service_type == 'Library' and profile.seat:
                batch_floor = f"Library - Floor: {profile.seat.floor}"
            elif profile.service_type == 'Coaching':
                batch_floor = f"Coaching - {profile.batch}" if profile.batch else "Coaching"
                
            seat_num = f"Seat: {profile.seat.seat_number}" if (profile.seat and profile.seat.seat_number) else ""

            return JsonResponse({
                'success': True,
                'is_group': False,
                'name': profile.full_name,
                'photo': get_profile_photo_url(profile.user),
                'role': profile.service_type or 'Student',
                'detail1': batch_floor,
                'detail2': seat_num,
                'detail3': '',
                'about': '',
                'member_since': profile.user.date_joined.strftime('%d %b %Y') if profile.user else '',
                'is_verified': False,
            })

    # 5. Guest / Fallback (for guests, or if StudentProfile/StudentAchievement does not exist)
    fallback_user = DjangoUser.objects.filter(id=entity_id).first()
    if fallback_user:
        # Check if the fallback user is actually a teacher/staff
        if fallback_user.is_staff or fallback_user.is_superuser:
            from users.models import TeacherProfile
            profile, _ = TeacherProfile.objects.get_or_create(user=fallback_user)
            photo_url = get_profile_photo_url(fallback_user)
            name = get_user_display_name(fallback_user)
            return JsonResponse({
                'success': True,
                'is_group': False,
                'name': name,
                'photo': photo_url,
                'role': profile.role_title or 'Teacher',
                'detail1': profile.detail1 or '',
                'detail2': profile.detail2 or '',
                'detail3': profile.detail3 or '',
                'about': profile.about or '',
                'emails': profile.emails or '',
                'mobile_numbers': profile.mobile_numbers or '',
                'whatsapp_numbers': profile.whatsapp_numbers or '',
                'member_since': fallback_user.date_joined.strftime('%d %b %Y'),
                'is_verified': True,
            })
            
        # Otherwise show them as guest or fallback
        name = get_user_display_name(fallback_user)
        photo_url = get_profile_photo_url(fallback_user)
        return JsonResponse({
            'success': True,
            'is_group': False,
            'name': name,
            'photo': photo_url,
            'role': 'Guest User',
            'detail1': '',
            'detail2': '',
            'detail3': '',
            'about': '',
            'member_since': fallback_user.date_joined.strftime('%d %b %Y'),
            'is_verified': False,
        })

    return JsonResponse({'success': False, 'error': 'Not found'}, status=404)


# ── GROUP CHAT VIEWS ──────────────────────────────────────────────────────────

@login_required
@require_POST
def guidy_create_group(request):
    """
    Creates a new group chat session.
    - Teachers can add anyone.
    - Students and alumni can only add users with whom they have an active ChatSession (connection).
    """
    user = request.user
    is_teacher = user.is_staff or user.is_superuser
    is_alumni = StudentAchievement.objects.filter(user=user, status='approved').exists()
    from .models import StudentProfile
    is_student = StudentProfile.objects.filter(user=user).exists()

    if not (is_teacher or is_alumni or is_student):
        return JsonResponse({'success': False, 'error': 'Not authorized to create groups'}, status=403)

    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'success': False, 'error': 'Group name required'}, status=400)

    # Get allowed member IDs for validation
    allowed_member_ids = set()
    if not is_teacher:
        if is_student:
            # Connected alumni
            sessions = ChatSession.objects.filter(request__student=user, is_active=True)
            allowed_member_ids = {s.request.alumni.user.id for s in sessions}
        elif is_alumni:
            # Connected students
            alumni_profile = StudentAchievement.objects.filter(user=user, status='approved').first()
            if alumni_profile:
                sessions = ChatSession.objects.filter(request__alumni=alumni_profile, is_active=True)
                allowed_member_ids = {s.request.student.id for s in sessions}

    member_ids = request.POST.get('member_ids', '')
    if not member_ids:
        return JsonResponse({'success': False, 'error': 'At least one member must be selected'}, status=400)

    ids = [int(i.strip()) for i in member_ids.split(',') if i.strip().isdigit()]
    
    # Validation for non-teachers
    if not is_teacher:
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        for uid in ids:
            if uid not in allowed_member_ids:
                return JsonResponse({'success': False, 'error': 'Cannot add dummy or unconnected members'}, status=400)
            if is_student:
                target_u = UserModel.objects.filter(id=uid).first()
                if target_u and (target_u.is_staff or target_u.is_superuser):
                    return JsonResponse({'success': False, 'error': 'Students cannot add teachers to groups'}, status=400)

    # Get optional description and photo
    description = request.POST.get('description', '').strip()
    photo_file = request.FILES.get('photo')

    # Validate photo size (max 2 MB)
    if photo_file and photo_file.size > 2 * 1024 * 1024:
        return JsonResponse({'success': False, 'error': 'Photo must be under 2 MB'}, status=400)

    group = GroupChatSession.objects.create(
        name=name,
        created_by=user,
        description=description,
    )
    if photo_file:
        group.photo = photo_file
        group.save()
    group.members.add(user)

    # Log group creation
    GroupMessage.objects.create(
        group=group,
        sender=user,
        content=f"system_user:{user.id} created this group",
        message_type='system'
    )

    from users.utils import get_user_display_name
    from django.contrib.auth import get_user_model
    UserModel = get_user_model()
    added_names = []
    
    for uid in ids:
        try:
            u = UserModel.objects.get(id=uid)
            group.members.add(u)
            added_names.append(get_user_display_name(u))
        except Exception:
            pass

    if added_names:
        added_names.sort()
        names_str = ", ".join(added_names)
        GroupMessage.objects.create(
            group=group,
            sender=user,
            content=f"system_user:{user.id} added {names_str}",
            message_type='system'
        )

    return JsonResponse({'success': True, 'group_id': group.id, 'name': group.name})


@login_required
@require_POST
def guidy_group_send_message(request, group_id):
    """Send a message to a group chat session."""
    group = get_object_or_404(GroupChatSession, id=group_id, is_active=True)
    user = request.user

    if user not in group.members.all() and group.created_by != user:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    content = request.POST.get('content', '').strip()
    uploaded_file = request.FILES.get('file')

    if uploaded_file:
        ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx', 'txt', 'mp3', 'wav', 'ogg', 'm4a'}
        ALLOWED_MIME_TYPES = {
            'image/jpeg', 'image/png', 'application/pdf', 
            'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 
            'text/plain', 'audio/mpeg', 'audio/wav', 'audio/ogg', 'audio/mp4', 'audio/x-m4a'
        }
        ext = uploaded_file.name.split('.')[-1].lower() if '.' in uploaded_file.name else ''
        if ext not in ALLOWED_EXTENSIONS or uploaded_file.content_type not in ALLOWED_MIME_TYPES:
            return JsonResponse({'success': False, 'error': 'Security blocked: Invalid file type. Only images, PDFs, Word docs, text, and audio files are allowed.'}, status=400)

        if uploaded_file.size > 15 * 1024 * 1024:
            return JsonResponse({'success': False, 'error': 'File exceeds 15MB limit.'}, status=400)

        import datetime
        from django.utils import timezone
        time_limit = timezone.now() - datetime.timedelta(days=1)
        media_count = GroupMessage.objects.filter(
            group=group,
            sender=user,
            timestamp__gte=time_limit
        ).exclude(file='').exclude(file__isnull=True).count()

        if media_count >= 5:
            return JsonResponse({'success': False, 'error': 'Daily media limit (5/day) reached for this group. Try again tomorrow.'}, status=400)
    reply_to_id = request.POST.get('reply_to_id')
    msg_type = 'text'

    if not content and not uploaded_file:
        return JsonResponse({'success': False, 'error': 'Empty message'}, status=400)

    reply_to_obj = None
    if reply_to_id:
        try:
            reply_to_obj = GroupMessage.objects.get(id=reply_to_id, group=group)
        except GroupMessage.DoesNotExist:
            pass

    if uploaded_file:
        ext = uploaded_file.name.rsplit('.', 1)[-1].lower()
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            msg_type = 'image'
        elif ext in ('mp3', 'wav', 'ogg', 'm4a'):
            msg_type = 'audio'
        elif ext in ('mp4', 'webm', 'mov', 'avi'):
            msg_type = 'video'
        else:
            msg_type = 'document'

    msg = GroupMessage.objects.create(
        group=group,
        sender=user,
        content=content,
        message_type=msg_type,
        reply_to=reply_to_obj,
        file=uploaded_file if uploaded_file else None,
        file_name=uploaded_file.name if uploaded_file else '',
    )
    msg.read_by.add(user)  # Sender has read it

    from users.utils import get_user_display_name, get_profile_photo_url

    # 🔔 Consolidated Guidy notification for each OTHER group member
    try:
        sender_name = get_user_display_name(user)
        for member in group.members.exclude(id=user.id):
            unread_count = GroupMessage.objects.filter(
                group__members=member,
                group__is_active=True,
                is_deleted_for_all=False,
            ).exclude(read_by=member).exclude(sender=member).count()
            if unread_count > 0:
                # Safe update or create to avoid MultipleObjectsReturned
                notif = Notification.objects.filter(user=member, category='guidy', is_read=False).first()
                if notif:
                    notif.title = '💬 New Guidy Messages'
                    notif.message = f'You have {unread_count} unread message{"s" if unread_count != 1 else ""} in Guidy.'
                    notif.link = '/guidy/'
                    notif.save()
                else:
                    Notification.objects.create(
                        user=member,
                        category='guidy',
                        is_read=False,
                        title='💬 New Guidy Messages',
                        message=f'You have {unread_count} unread message{"s" if unread_count != 1 else ""} in Guidy.',
                        link='/guidy/'
                    )

                # Fire WhatsApp-style mobile push notification for group members
                push_title = f"{group.name} ({sender_name})"
                
                if msg.message_type == 'text':
                    push_body = msg.content[:60] + '...' if len(msg.content) > 60 else msg.content
                elif msg.message_type == 'image':
                    push_body = "📷 Photo"
                elif msg.message_type == 'audio':
                    push_body = "🎵 Audio"
                elif msg.message_type == 'video':
                    push_body = "🎥 Video"
                else:
                    push_body = "📎 Document"
                    
                push_url = f"/guidy/?group={group.id}"
                threading.Thread(
                    target=_send_push_bg,
                    args=(member, push_title, push_body, push_url),
                    daemon=True
                ).start()
    except Exception as e:
        import traceback
        with open('guidy_errors.log', 'a', encoding='utf-8') as f:
            f.write(f"\n--- Guidy Group Send Message Exception ---\n")
            traceback.print_exc(file=f)

    reply_preview = None
    if reply_to_obj:
        reply_preview = {
            'id': reply_to_obj.id,
            'content': reply_to_obj.content[:80],
            'sender': get_user_display_name(reply_to_obj.sender),
            'type': reply_to_obj.message_type,
        }

    return JsonResponse({
        'success': True,
        'message': {
            'id': msg.id,
            'content': resolve_system_message_content(msg.content, user) if msg.message_type == 'system' else msg.content,
            'message_type': msg.message_type,
            'file_url': msg.file.url if msg.file else None,
            'file_name': msg.file_name,
            'timestamp': localtime(msg.timestamp).strftime('%H:%M'),
            'date': localtime(msg.timestamp).strftime('%Y-%m-%d'),
            'is_mine': True,
            'is_read': False,
            'sender_name': get_user_display_name(user),
            'sender_photo': get_profile_photo_url(user),
            'media_expired': msg.media_expired,
            'is_verified': (msg.sender.is_staff or msg.sender.is_superuser),
            'reply_to': reply_preview,
        }
    })


@login_required
def guidy_group_poll(request, group_id):
    """Poll for new group messages."""
    group = get_object_or_404(GroupChatSession, id=group_id, is_active=True)
    user = request.user
    from users.utils import get_user_display_name, get_profile_photo_url

    if user not in group.members.all() and group.created_by != user:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    after_id = request.POST.get('last_msg_id') or request.GET.get('after', 0)
    try:
        after_id = int(after_id)
    except ValueError:
        after_id = 0
    from datetime import timedelta
    ten_days_ago = timezone.now() - timedelta(days=10)
    new_msgs = group.messages.filter(
        id__gt=after_id
    ).exclude(
        deleted_by=user
    ).exclude(
        is_deleted_for_all=True, deleted_at__lt=ten_days_ago
    ).select_related('sender', 'reply_to__sender').order_by('timestamp')

    for gm in new_msgs.exclude(sender=user):
        gm.read_by.add(user)

    data = []
    for m in new_msgs:
        reply_preview = None
        if m.reply_to:
            reply_preview = {
                'id': m.reply_to.id,
                'content': m.reply_to.content[:80],
                'sender': get_user_display_name(m.reply_to.sender),
                'type': m.reply_to.message_type,
            }
        data.append({
            'id': m.id,
            'content': resolve_system_message_content(m.content, user) if m.message_type == 'system' else (m.content or ("⏳ Media expired" if m.media_expired else "")),
            'message_type': m.message_type,
            'file_url': m.file.url if m.file else None,
            'file_name': m.file_name,
            'timestamp': localtime(m.timestamp).strftime('%H:%M'),
            'date': localtime(m.timestamp).strftime('%Y-%m-%d'),
            'is_mine': (m.sender == user),
            'is_read': m.read_by.exclude(id=user.id).exists(),
            'sender_name': get_user_display_name(m.sender),
            'sender_photo': get_profile_photo_url(m.sender),
            'is_pinned': m.is_pinned,
            'is_deleted_for_all': m.is_deleted_for_all,
            'media_expired': m.media_expired,
            'is_verified': (m.sender.is_staff or m.sender.is_superuser),
            'reply_to': reply_preview,
        })

    # Fetch read message ids sent by request.user
    import json
    pending_ids_str = request.POST.get('pending_read_ids') or request.GET.get('pending_read_ids', '[]')
    try:
        pending_ids = json.loads(pending_ids_str)
    except:
        pending_ids = []

    newly_read = group.messages.filter(id__in=pending_ids, sender=user).exclude(read_by=user).filter(read_by__isnull=False).distinct().values_list('id', flat=True)

    return JsonResponse({
        'success': True,
        'messages': data,
        'read_message_ids': list(newly_read),
        'guidy_badge_count': get_guidy_badge_count(user)
    })


def guidy_check_status(request, alumni_pk):
    """
    Public/student-facing endpoint: returns the button state for the
    'Seek Guidance' button on achievement_detail.html.
    Called via JS on page load.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'state': 'unauthenticated'})

    alumni = get_object_or_404(StudentAchievement, pk=alumni_pk, status='approved')

    # Check if the current user is blocked by alumni
    if BlockedGuidance.objects.filter(
        alumni=alumni, student=request.user,
        direction=BlockedGuidance.DIRECTION_ALUMNI
    ).exists():
        return JsonResponse({'state': 'blocked'})

    # Check if the current user is restricted
    if RestrictedStudent.objects.filter(alumni=alumni, student=request.user).exists():
        return JsonResponse({'state': 'restricted'})

    # Check existing request
    try:
        req = GuidanceRequest.objects.get(student=request.user, alumni=alumni)
        if req.status == 'accepted':
            try:
                session = req.chat_session
                return JsonResponse({'state': 'chat_open', 'session_id': session.id})
            except ChatSession.DoesNotExist:
                return JsonResponse({'state': 'pending'})
        elif req.status == 'pending':
            return JsonResponse({'state': 'pending'})
        else:  # rejected
            return JsonResponse({'state': 'none'})
    except GuidanceRequest.DoesNotExist:
        return JsonResponse({'state': 'none'})


# -------------------------------------------------------------------
# NOTIFICATION MANAGEMENT VIEWS
# -------------------------------------------------------------------

@login_required
@require_http_methods(["GET", "POST"])
def delete_notification_view(request, notification_id):
    """
    Manually delete a specific notification completely from DB.
    Used by both students and teachers (X button).
    """
    try:
        notification = Notification.objects.get(id=notification_id, user=request.user)
        notification.delete()
        status = 'success'
        message = "Notification deleted."
    except Notification.DoesNotExist:
        status = 'success'
        message = "Notification already deleted."
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
        return JsonResponse({'status': 'success', 'message': message})
        
    if status == 'success':
        messages.success(request, message)
    else:
        messages.error(request, message)
    return redirect(request.META.get('HTTP_REFERER', 'users:student_dashboard'))


@login_required
def mark_all_notifications_read_view(request):
    """
    Marks all unread notifications as read for the current user.
    Sets read_at for cleanup tracking.
    """
    Notification.objects.filter(user=request.user, is_read=False).update(
        is_read=True, 
        read_at=timezone.now()
    )
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return JsonResponse({'status': 'success'})
        
    return redirect(request.META.get('HTTP_REFERER', 'users:student_dashboard'))


@login_required
@require_http_methods(["GET", "POST"])
def bulk_delete_notifications_view(request):
    """
    Deletes multiple notifications selected via checkboxes completely from DB.
    Supports JSON payloads, form-encoded POST, and 'all' selection.
    """
    notification_ids = []
    
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
            notification_ids = data.get('notification_ids', [])
        except Exception:
            notification_ids = []
    else:
        notification_ids = request.POST.getlist('notification_ids')
        if not notification_ids:
            notification_ids = request.GET.getlist('notification_ids')

    clean_ids = []
    select_all = False
    for nid in notification_ids:
        if str(nid).lower() == 'all':
            select_all = True
            break
        try:
            clean_ids.append(int(nid))
        except (ValueError, TypeError):
            pass

    if select_all:
        deleted_count, _ = Notification.objects.filter(user=request.user).delete()
    elif clean_ids:
        deleted_count, _ = Notification.objects.filter(id__in=clean_ids, user=request.user).delete()
    else:
        deleted_count = 0

    is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

    if is_ajax:
        return JsonResponse({
            'status': 'success',
            'message': f"{deleted_count} notification(s) deleted.",
            'deleted_count': deleted_count
        })

    if deleted_count > 0:
        messages.success(request, f"{deleted_count} notification(s) deleted.")
    else:
        messages.warning(request, "No notifications selected.")

    return redirect(request.META.get('HTTP_REFERER', 'users:student_dashboard'))


@login_required
def notifications_api_view(request):
    """
    Unified API to return notifications for current user.
    Handles different roles (student, alumni, guest vs teacher)
    to return appropriate statistics and notification items.
    """
    from django.utils.timesince import timesince
    from users.utils import get_profile_photo_url, get_user_dashboard_type
    
    user = request.user
    dashboard_type = get_user_dashboard_type(user)
    if dashboard_type is None:
        dashboard_type = 'guest'
        
    today = timezone.now().date()
    
    if dashboard_type == 'teacher' or user.is_staff or user.is_superuser:
        # --- Teacher / Staff Dashboard ---
        pending_students = StudentProfile.objects.filter(
            status='pending',
            is_manual_pending=False
        ).select_related('seat', 'user')
        
        pending_hold_requests = SeatHoldRequest.objects.filter(
            status='pending'
        ).select_related('seat', 'student')
        
        cancel_hold_requests = SeatHoldRequest.objects.filter(
            status='approved',
            cancel_requested=True
        ).select_related('seat', 'student')
        
        pending_achievements = StudentAchievement.objects.filter(
            status='pending'
        ).select_related('user')
        
        pending_partial_requests = SeatSpecialRequest.objects.filter(
            status='pending'
        ).select_related('student', 'seat', 'user')
        
        from .models import DismissedFeeAlert
        raw_overdue_students = StudentProfile.objects.filter(
            status='admitted',
            fee_expiry_date__isnull=False,
            fee_expiry_date__lte=today
        ).select_related('user', 'seat').order_by('fee_expiry_date')
        
        dismissed_map = set(
            DismissedFeeAlert.objects.filter(teacher=user)
            .values_list('student_id', 'expiry_date')
        )

        overdue_students = []
        for s in raw_overdue_students:
            if (s.id, s.fee_expiry_date) in dismissed_map:
                continue
            overdue_students.append(s)
        
        active_complaints = Complaint.objects.exclude(
            status=Complaint.STATUS_RESOLVED
        ).select_related("student", "student__user")
        
        # Counts
        overdue_count = len(overdue_students)
        total_admission_requests = pending_students.count()
        total_hold_requests = pending_hold_requests.count() + cancel_hold_requests.count()
        total_pending_achievements = pending_achievements.count()
        pending_complaints_count = active_complaints.count()
        
        total_notification_count = (
            total_admission_requests
            + total_hold_requests
            + pending_partial_requests.count()
            + pending_complaints_count
            + total_pending_achievements
            + overdue_count
        )
        
        # System Alerts notifications
        all_notifs = Notification.objects.filter(user=user).order_by("-created_at")
        active_notifications = []
        for n in all_notifs:
            if n.category == "fee_teacher" and n.meta and 'expiry_date' in n.meta:
                try:
                    notif_expiry = datetime.strptime(n.meta['expiry_date'], '%Y-%m-%d').date()
                    if notif_expiry < today:
                        continue
                except Exception:
                    try:
                        import datetime as dt_mod
                        notif_expiry = dt_mod.date.fromisoformat(n.meta['expiry_date'])
                        if notif_expiry < today:
                            continue
                    except Exception:
                        pass
            active_notifications.append(n)
            
        notifications_slice = active_notifications[:25]
        
        # Pre-fetch students for notifications
        student_ids = [n.meta['student_id'] for n in notifications_slice if n.meta and 'student_id' in n.meta]
        students_map = {}
        if student_ids:
            students_map = {s.id: s for s in StudentProfile.objects.filter(id__in=student_ids).select_related('seat', 'user')}
            
        notif_list = []
        for n in notifications_slice:
            student_obj = None
            if n.meta and 'student_id' in n.meta:
                s_obj = students_map.get(n.meta['student_id'])
                if s_obj:
                    student_obj = {
                        'id': s_obj.id,
                        'full_name': s_obj.full_name,
                        'photo_url': get_profile_photo_url(s_obj.user),
                        'mobile_number': s_obj.mobile_number,
                        'service_type': s_obj.service_type
                    }
                    
            notif_list.append({
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'link': n.link,
                'category': n.category,
                'is_read': n.is_read,
                'created_at_date': n.created_at.strftime("%d %b"),
                'created_at_time': timesince(n.created_at) + " ago",
                'student_obj': student_obj,
                'meta': n.meta if isinstance(n.meta, dict) else {}
            })
            
        overdue_list = []
        for s in overdue_students:
            first_name = s.full_name.strip().split()[0] if s.full_name else "Student"
            service_detail_str = s.service_type or ""
            if s.service_type == 'Coaching':
                if s.batch:
                    service_detail_str = f"Coaching ({s.batch})"
            elif s.service_type == 'Library':
                shift_label = s.shift.replace('_', ' ').title() if s.shift else "General"
                service_detail_str = f"Library ({shift_label})"
            elif s.service_type == 'Both':
                service_detail_str = "Coaching & Library"
            
            expiry_str = s.fee_expiry_date.strftime("%d %b") if s.fee_expiry_date else ""
            subtext_str = f"{service_detail_str} • Expired: {expiry_str}"

            overdue_list.append({
                'id': s.id,
                'full_name': s.full_name,
                'first_name': first_name,
                'service_type': s.service_type,
                'service_details': subtext_str,
                'fee_expiry_date': s.fee_expiry_date.strftime("%d %b"),
                'mobile_number': s.mobile_number,
                'whatsapp_number': s.whatsapp_number or s.mobile_number,
                'photo_url': get_profile_photo_url(s.user)
            })
            
        return JsonResponse({
            'role': 'teacher',
            'total_notification_count': total_notification_count,
            'total_admission_requests': total_admission_requests,
            'total_hold_requests': total_hold_requests,
            'total_pending_achievements': total_pending_achievements,
            'pending_complaints_count': pending_complaints_count,
            'overdue_students': overdue_list,
            'notifications': notif_list
        })
        
    else:
        # --- Student / Guest / Alumni Dashboard ---
        notifications_qs = Notification.objects.filter(user=user).order_by('-created_at')
        if dashboard_type == 'alumni':
            notifications_qs = notifications_qs.exclude(category__in=['payment', 'hold'])
            
        notif_list = []
        for n in notifications_qs[:25]:
            notif_list.append({
                'id': n.id,
                'title': n.title,
                'message': n.message,
                'link': n.link,
                'category': n.category,
                'is_read': n.is_read,
                'created_at': n.created_at.strftime("%d %b %Y, %I:%M %p")
            })
            
        fee_alert = None
        profile = getattr(user, 'profile', None)
        if profile and profile.fee_expiry_date:
            expiry_threshold = today + timedelta(days=10)
            if profile.fee_expiry_date <= today:
                fee_alert = {
                    'type': 'overdue',
                    'date_str': profile.fee_expiry_date.strftime("%d %b %Y")
                }
            elif profile.fee_expiry_date <= expiry_threshold:
                fee_alert = {
                    'type': 'warning',
                    'date_str': profile.fee_expiry_date.strftime("%d %b %Y")
                }
                
        return JsonResponse({
            'role': 'student',
            'unread_count': notifications_qs.filter(is_read=False).count(),
            'notifications': notif_list,
            'fee_alert': fee_alert
        })


@login_required
@require_POST
def mark_notification_unread_view(request, notification_id):
    """
    Manually mark a notification as unread.
    """
    notification = get_object_or_404(Notification, id=notification_id, user=request.user)
    notification.is_read = False
    notification.read_at = None
    notification.save()
    return JsonResponse({'status': 'success'})


@login_required
@require_POST
def dismiss_fee_expired_alerts(request):
    """
    Teacher API view to bulk dismiss fee expired alerts for selected students.
    Saves a DismissedFeeAlert record for each student matching their current fee_expiry_date.
    """
    if not (request.user.is_staff or request.user.is_superuser):
        return JsonResponse({'status': 'error', 'message': 'Permission denied'}, status=403)
    
    import json
    student_ids = []
    try:
        if request.body:
            data = json.loads(request.body)
            student_ids = data.get('student_ids', [])
    except Exception:
        pass

    if not student_ids:
        student_ids = request.POST.getlist('student_ids')

    if not student_ids:
        return JsonResponse({'status': 'error', 'message': 'No students selected.'}, status=400)

    students = StudentProfile.objects.filter(id__in=student_ids, fee_expiry_date__isnull=False)
    dismissed_count = 0
    from .models import DismissedFeeAlert
    for s in students:
        DismissedFeeAlert.objects.get_or_create(
            teacher=request.user,
            student=s,
            expiry_date=s.fee_expiry_date
        )
        dismissed_count += 1

    return JsonResponse({
        'status': 'success',
        'message': f'Successfully dismissed {dismissed_count} student(s) from Fee Expired List.',
        'dismissed_count': dismissed_count
    })



# ─────────────────────────────────────────────────────────────────────────────
# TO-DO HUB VIEWS (Isolated Logic)
# ─────────────────────────────────────────────────────────────────────────────

from .models import TodoTask
from .utils import get_user_dashboard_type

def _get_base_template(user):
    dtype = get_user_dashboard_type(user)
    if dtype is None and user and user.is_authenticated:
        dtype = 'guest'
    mapping = {
        'teacher': 'users/teacher_dashboard.html',
        'student': 'users/student_dashboard.html',
        'alumni':  'users/student_dashboard.html',
        'guest':   'users/guest_page.html',
    }
    return mapping.get(dtype, 'home_page.html')

@login_required
def todo_hub_page(request):
    """Renders the main To-Do Hub container."""
    user = request.user
    dashboard_type = get_user_dashboard_type(user)
    if dashboard_type is None and user.is_authenticated:
        dashboard_type = 'guest'
    
    if dashboard_type is None:
        return redirect('users:guest_page')

    # Base dashboard context (notifications, etc)
    extra = {}
    all_notifications = Notification.objects.filter(user=user).order_by('-created_at')
    unread_count = all_notifications.filter(is_read=False).count()
    
    if dashboard_type in ('student', 'alumni'):
        profile = StudentProfile.objects.filter(user=user).first()
        achievement = StudentAchievement.objects.filter(user=user).first()
        extra = {
            'profile': profile,
            'nav_achievement': achievement,
            'unread_count': unread_count,
            'is_alumni': (dashboard_type == 'alumni'),
        }
    elif dashboard_type == 'guest':
        extra = {
            'profile': None,
            'nav_achievement': None,
            'unread_count': unread_count,
            'is_alumni': False,
        }
    elif dashboard_type == 'teacher':
        extra = {
            'total_notification_count': unread_count,
        }

    context = {
        'base_dashboard': _get_base_template(user),
        'dashboard_type': dashboard_type,
        'notifications': all_notifications[:15],
        **extra,
    }
    return render(request, 'users/todo.html', context)

@login_required
def todo_search_students(request):
    """
    Search students and alumni for the 'To Add Fee' picker.
    Returns: id, name, type, photo_url, detail (service info).
    """
    q = request.GET.get('q', '').strip()
    
    # Fetch all if q=all
    students = StudentProfile.objects.filter(is_admitted=True)
    alumni = StudentAchievement.objects.filter(status='approved')
    
    if q and q != 'all':
        students = students.filter(full_name__icontains=q)
        alumni = alumni.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))
    
    results = []
    for s in students:
        # One-line service detail: Floor/Seat for library, Batch for coaching
        service_info = s.service_type
        if s.service_type == 'Library':
            seat = SeatAssignment.objects.filter(student=s, is_active=True).first()
            if seat:
                service_info = f"Library - {seat.seat.floor}/{seat.seat.seat_number}"
            else:
                service_info = "Library (No Seat)"
        elif s.service_type == 'Coaching':
            service_info = f"Coaching - {s.batch if s.batch else 'General'}"

        s_photo_url = None
        if s and s.photo:
            try:
                s_photo_url = s.photo.url
            except (ValueError, AttributeError):
                s_photo_url = None

        results.append({
            'id': f"s_{s.id}",
            'name': s.full_name,
            'type': 'Student',
            'photo_url': s_photo_url,
            'detail': service_info
        })
    
    for a in alumni:
        a_photo_url = None
        if a and a.photo:
            try:
                a_photo_url = a.photo.url
            except (ValueError, AttributeError):
                a_photo_url = None

        results.append({
            'id': f"a_{a.id}",
            'name': a.full_name,
            'type': 'Alumni',
            'photo_url': a_photo_url,
            'detail': a.current_post if a.current_post else "Alumni Success"
        })
        
    return JsonResponse({'students': results})

@login_required
@require_POST
def todo_add_fee_reminder(request):
    """
    Saves a fee reminder as a TodoTask.
    Metadata stores the list of students and amounts.
    """
    if not is_teacher(request.user):
        return JsonResponse({'success': False, 'error': 'Permission denied'})
        
    try:
        data = json.loads(request.body)
        auto_delete = data.get('auto_delete', True)
        delete_hours = float(data.get('delete_hours', 6))
        student_selections = data.get('students', []) # [{"id": 1, "amount": 500}, ...]
        
        if not student_selections:
            return JsonResponse({'success': False, 'error': 'No students selected'})
            
        enriched_metadata = []
        for sel in student_selections:
            sid_raw = str(sel.get('id'))
            amount = sel.get('amount')
            
            if sid_raw.startswith('s_'):
                sid = sid_raw[2:]
                student = StudentProfile.objects.filter(id=sid).first()
                name = student.full_name if student else "Unknown"
                service = student.service_type if student else "Library"
                photo_url = None
                if student and student.photo:
                    try:
                        photo_url = student.photo.url
                    except (ValueError, AttributeError):
                        photo_url = None
            elif sid_raw.startswith('a_'):
                sid = sid_raw[2:]
                alumni = StudentAchievement.objects.filter(id=sid).first()
                name = alumni.full_name if alumni else "Unknown"
                service = "Alumni"
                photo_url = None
                if alumni and alumni.photo:
                    try:
                        photo_url = alumni.photo.url
                    except (ValueError, AttributeError):
                        photo_url = None
            elif sid_raw.startswith('m_'):
                # Manual entry created in UI
                name = sel.get('name', 'Unknown')
                service = "Custom Entry"
                photo_url = None
            else:
                # Fallback for old data or direct IDs
                sid = sid_raw
                student = StudentProfile.objects.filter(id=sid).first()
                name = student.full_name if student else "Unknown"
                service = student.service_type if student else "Library"
                photo_url = None
                if student and student.photo:
                    try:
                        photo_url = student.photo.url
                    except (ValueError, AttributeError):
                        photo_url = None
                
            enriched_metadata.append({
                'id': sid_raw,
                'name': name,
                'amount': amount,
                'detail': service,
                'photo_url': photo_url
            })
            
        delete_at = timezone.now() + timedelta(hours=delete_hours) if auto_delete else None
        
        task = TodoTask.objects.create(
            user=request.user,
            category='FEES',
            metadata=enriched_metadata,
            auto_delete=auto_delete,
            delete_at=delete_at
        )
        
        return JsonResponse({'success': True, 'task_id': task.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def todo_get_tasks(request):
    """Returns tasks for the current user based on category, with search filtering."""
    try:
        from .utils import process_todo_notifications
        process_todo_notifications()
    except Exception:
        pass

    is_trash = request.GET.get('is_trash', 'false') == 'true'
    category = request.GET.get('category', 'FEES')
    q = request.GET.get('q', '').strip()
    
    if is_trash:
        tasks = TodoTask.objects.filter(user=request.user, is_trash=True).order_by('-trashed_at')
    else:
        if category == 'ALL':
            tasks = TodoTask.objects.filter(user=request.user, is_trash=False).order_by('-created_at')
        else:
            tasks = TodoTask.objects.filter(user=request.user, category=category, is_trash=False).order_by('-created_at')
            
    if q:
        filtered = []
        q_lower = q.lower()
        for t in tasks:
            cat_display = t.get_category_display()
            dt_str = t.created_at.strftime("%b %d, %Y | %I:%M %p")
            title = ""
            desc = ""
            student_names = ""
            
            # Extract fields for search matching
            if isinstance(t.metadata, dict):
                desc = t.metadata.get('description') or t.metadata.get('note') or t.metadata.get('content') or ""
                
            if t.category == 'BREAKDOWN':
                if isinstance(t.metadata, dict) and t.metadata.get('title'):
                    title = t.metadata.get('title')
                elif isinstance(t.metadata, dict) and t.metadata.get('task_name'):
                    title = t.metadata.get('task_name')
                else:
                    title = f"{cat_display} : {dt_str}"
            elif t.category == 'TODO':
                if isinstance(t.metadata, dict) and t.metadata.get('task_name'):
                    title = t.metadata.get('task_name')
                else:
                    title = f"{cat_display} : {dt_str}"
            elif t.category == 'NOTE':
                if isinstance(t.metadata, dict):
                    title = t.metadata.get('title') or 'Untitled Note'
                else:
                    title = f"{cat_display} : {dt_str}"
            elif t.category == 'REMINDER':
                if isinstance(t.metadata, dict):
                    title = t.metadata.get('title') or 'Reminder'
                else:
                    title = f"{cat_display} : {dt_str}"
            elif t.category == 'FEES':
                title = f"{cat_display} : {dt_str}"
                # fees metadata could be a list of student records
                if isinstance(t.metadata, list):
                    student_names = " ".join([item.get('name', '') for item in t.metadata if isinstance(item, dict)])
                elif isinstance(t.metadata, dict):
                    students = t.metadata.get('students') or []
                    if isinstance(students, list):
                        student_names = " ".join([s.get('name', '') for s in students if isinstance(s, dict)])
                    else:
                        student_names = t.metadata.get('student_name', '')
            
            # Combine elements for search matching
            combined = f"{title} {desc} {student_names}".lower()
            if q_lower in combined:
                filtered.append(t)
        tasks = filtered
    
    data = []
    now = timezone.now()
    
    for t in tasks:
        # Dynamic Heading: {Category} : {Date} | {Time}
        # Example: Fee : May 09, 2026 | 10:30 PM
        cat_display = t.get_category_display()
        dt_str = t.created_at.strftime("%b %d, %Y | %I:%M %p")
        
        # Breakdown tasks have their own titles
        if t.category == 'BREAKDOWN' and isinstance(t.metadata, dict) and t.metadata.get('title'):
            title = t.metadata.get('title')
        elif t.category == 'TODO' and isinstance(t.metadata, dict) and t.metadata.get('task_name'):
            title = t.metadata.get('task_name')
        elif t.category == 'NOTE' and isinstance(t.metadata, dict):
            title = t.metadata.get('title') or 'Untitled Note'
        elif t.category == 'REMINDER' and isinstance(t.metadata, dict):
            title = t.metadata.get('title', 'Reminder')
        else:
            title = f"{cat_display} : {dt_str}"
        
        time_left_str = "No Limit"
        time_left_sec = None
        
        if t.is_trash:
            # Trash items always have a 15-day purge cycle
            if t.trashed_at:
                purge_at = t.trashed_at + timedelta(days=15)
                if now >= purge_at:
                    time_left_str = "Purging..."
                    time_left_sec = 0
                else:
                    diff = purge_at - now
                    time_left_sec = int(diff.total_seconds())
                    days = diff.days
                    hours = (time_left_sec // 3600) % 24
                    time_left_str = f"Purge in {days}d {hours}h"
            else:
                time_left_str = "Purge soon"
                time_left_sec = 0
        elif t.auto_delete and t.delete_at:
            if now >= t.delete_at:
                time_left_str = "Expired"
                time_left_sec = 0
            else:
                diff = t.delete_at - now
                time_left_sec = int(diff.total_seconds())
                
                hours, remainder = divmod(time_left_sec, 3600)
                minutes, _ = divmod(remainder, 60)
                
                if diff.days > 0:
                    time_left_str = f"{diff.days}d {hours % 24}h left"
                else:
                    time_left_str = f"{hours}h {minutes}m left"

        data.append({
            'id': t.id,
            'title': title,
            'category': t.category,
            'students': t.metadata,
            'metadata': t.metadata,
            'time_left_str': time_left_str,
            'time_left_sec': time_left_sec,
            'is_done': t.is_done,
            'is_pinned': t.is_pinned if hasattr(t, 'is_pinned') else False,
            'is_trash': t.is_trash,
            'created_at': t.created_at.isoformat(),
            'auto_delete': t.auto_delete,
            'delete_at': t.delete_at.isoformat() if t.delete_at else None,
            'reminder_meta': t.metadata if t.category == 'REMINDER' else None,
            'last_notified_at': t.last_notified_at.isoformat() if t.last_notified_at else None,
        })
        
    return JsonResponse({'tasks': data})

@login_required
@require_POST
def todo_trash_task(request, task_id):
    """Soft delete: Move task to trash."""
    task = get_object_or_404(TodoTask, id=task_id, user=request.user)
    task.is_trash = True
    task.trashed_at = timezone.now()
    task.save(update_fields=['is_trash', 'trashed_at'])
    return JsonResponse({'success': True})

@login_required
@require_POST
def todo_recover_task(request, task_id):
    """Recover task from trash and reset timer."""
    task = get_object_or_404(TodoTask, id=task_id, user=request.user)
    task.is_trash = False
    task.trashed_at = None
    task.auto_delete = False # Rule: reset duration/timer to 0:0
    task.delete_at = None
    task.save(update_fields=['is_trash', 'trashed_at', 'auto_delete', 'delete_at'])
    return JsonResponse({'success': True})

@login_required
@require_POST
def todo_permanent_delete_task(request, task_id):
    """Permanently delete task from DB."""
    task = get_object_or_404(TodoTask, id=task_id, user=request.user)
    task.delete()
    return JsonResponse({'success': True})

@login_required
@require_POST
def todo_bulk_action(request):
    """Handle bulk trash, recovery, or permanent deletion."""
    try:
        data = json.loads(request.body)
        task_ids = data.get('task_ids', [])
        action = data.get('action') # 'trash', 'recover', 'delete'
        
        tasks = TodoTask.objects.filter(id__in=task_ids, user=request.user)
        
        if action == 'trash':
            tasks.update(is_trash=True, trashed_at=timezone.now())
        elif action == 'recover':
            tasks.update(is_trash=False, trashed_at=None, auto_delete=False, delete_at=None)
        elif action == 'delete':
            tasks.delete()
        else:
            return JsonResponse({'success': False, 'error': 'Invalid action'})
            
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def todo_update_task(request, task_id):
    """Update an existing task's metadata and settings."""
    task = get_object_or_404(TodoTask, id=task_id, user=request.user)
    try:
        data = json.loads(request.body)
        if task.category == 'FEES' and 'students' in data:
            students = data.get('students', [])
            enriched_metadata = []
            for sel in students:
                sid_raw = str(sel.get('id'))
                amount = sel.get('amount')
                if sid_raw.startswith('s_'):
                    sid = sid_raw[2:]
                    student = StudentProfile.objects.filter(id=sid).first()
                    name = student.full_name if student else "Unknown"
                    service = student.service_type if student else "Library"
                    photo_url = student.photo.url if student and student.photo else None
                elif sid_raw.startswith('a_'):
                    sid = sid_raw[2:]
                    alumni = StudentAchievement.objects.filter(id=sid).first()
                    name = alumni.full_name if alumni else "Unknown"
                    service = "Alumni"
                    photo_url = alumni.photo.url if alumni and alumni.photo else None
                elif sid_raw.startswith('m_'):
                    # Manual entry created in UI
                    name = sel.get('name', 'Unknown')
                    service = "Custom Entry"
                    photo_url = None
                else:
                    sid = sid_raw
                    student = StudentProfile.objects.filter(id=sid).first()
                    name = student.full_name if student else "Unknown"
                    service = student.service_type if student else "Library"
                    photo_url = student.photo.url if student and student.photo else None
                
                enriched_metadata.append({
                    'id': sid_raw,
                    'name': name,
                    'amount': amount,
                    'detail': service,
                    'photo_url': photo_url
                })
            task.metadata = enriched_metadata
        else:
            task.metadata = data.get('students', task.metadata)
        
        # Change 4: Breakdown tasks have fixed auto_delete=True
        if task.category == 'BREAKDOWN':
            task.auto_delete = True
            deadline_str = data.get('deadline')
            if deadline_str:
                dt = parse_flexible_datetime(deadline_str)
                if dt and not is_aware(dt):
                    dt = make_aware(dt)
                task.delete_at = dt
        else:
            task.auto_delete = data.get('auto_delete', task.auto_delete)
            if task.auto_delete:
                delete_hours = float(data.get('delete_hours', 6))
                task.delete_at = task.created_at + timedelta(hours=delete_hours)
            else:
                task.delete_at = None
        
        if task.category == 'TODO':
            meta = data.get('metadata', task.metadata or {})
            if isinstance(meta, dict) and 'is_pinned' in meta:
                task.is_pinned = bool(meta.get('is_pinned', False))
            
        task.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})



@login_required
@require_POST
def todo_add_breakdown(request):
    """Saves a task breakdown with subtasks and deadline."""
    try:
        data = json.loads(request.body)
        title = data.get('title')
        deadline_str = data.get('deadline')
        subtasks = data.get('subtasks', []) # [{name, time_hrs, is_done, order}]
        
        if not title or not deadline_str:
            return JsonResponse({'success': False, 'error': 'Title and Deadline are required.'})
            
        deadline = parse_flexible_datetime(deadline_str)
        if not deadline:
            return JsonResponse({'success': False, 'error': 'Invalid deadline format.'})
        if not is_aware(deadline):
            deadline = make_aware(deadline)

        # Server-side validation
        for s in subtasks:
            if s.get('is_done', False):
                continue
            if not str(s.get('name', '')).strip():
                return JsonResponse({'success': False, 'error': 'All subtasks must have a name.'})
            try:
                hrs = float(s.get('hours', 0))
                if hrs <= 0:
                    return JsonResponse({'success': False, 'error': 'Subtask hours must be greater than 0.'})
            except (ValueError, TypeError):
                return JsonResponse({'success': False, 'error': 'Invalid hours value in subtask.'})

        if len(subtasks) > 50:
            return JsonResponse({'success': False, 'error': 'Maximum 50 subtasks allowed.'})
        
        enriched_subtasks = []
        for s in subtasks:
            enriched = dict(s)
            enriched['remaining_hours'] = float(s.get('hours', 0))
            enriched_subtasks.append(enriched)

        metadata = {
            'title': title,
            'subtasks': enriched_subtasks,
            'total_hours': data.get('total_hours', 0),
            'active_started_at': timezone.now().isoformat(),
        }
        
        task = TodoTask.objects.create(
            user=request.user,
            category='BREAKDOWN',
            metadata=metadata,
            auto_delete=True,
            delete_at=deadline
        )
        
        return JsonResponse({'success': True, 'task_id': task.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_POST
def todo_update_metadata(request, task_id):
    """Generic metadata update for subtask completion, etc."""
    task = get_object_or_404(TodoTask, id=task_id, user=request.user)
    try:
        data = json.loads(request.body)
        task.metadata = data.get('metadata', task.metadata)
        task.is_done = data.get('is_done', task.is_done)
        
        deadline_str = data.get('deadline')
        if deadline_str and task.category == 'BREAKDOWN':
            dt = parse_flexible_datetime(deadline_str)
            if dt and not is_aware(dt):
                dt = make_aware(dt)
            task.delete_at = dt
            task.auto_delete = True

        if task.category == 'BREAKDOWN':
            task.auto_delete = True
            
        if task.category == 'TODO':
            meta = data.get('metadata', task.metadata or {})
            if isinstance(meta, dict) and 'is_pinned' in meta:
                task.is_pinned = bool(meta.get('is_pinned', False))

        if task.category == 'NOTE':
            meta = data.get('metadata', {})
            if isinstance(meta, dict):
                if 'is_pinned' in meta:
                    task.is_pinned = bool(meta.get('is_pinned', False))
                # Clamp images to max 3
                if 'images' in meta:
                    meta['images'] = meta['images'][:3]
                task.metadata = meta

        task.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def todo_add_todo_task(request):
    """Saves a new To-Do task."""
    try:
        data = json.loads(request.body)
        task_name = data.get('task_name', '').strip()
        if not task_name:
            return JsonResponse({'success': False, 'error': 'Task name is required.'})
        
        metadata = {
            'task_name': task_name,
            'description': data.get('description', ''),
            'color': data.get('color', '#7b61ff'),
            'is_pinned': data.get('is_pinned', False),
            'order': data.get('order', 0)
        }
        
        task = TodoTask.objects.create(
            user=request.user,
            category='TODO',
            metadata=metadata,
            is_done=False,
            is_pinned=False,
            auto_delete=False,
            delete_at=None
        )
        return JsonResponse({'success': True, 'task_id': task.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def todo_add_note_task(request):
    """Saves a new Notebook note."""
    try:
        data = json.loads(request.body)
        metadata = {
            'title':       data.get('title', '').strip(),
            'content':     data.get('content', ''),
            'note_color':  data.get('note_color', '#fef08a'),
            'note_type':   data.get('note_type', 'quick'),
            'images':      data.get('images', [])[:3],
            'is_pinned':   data.get('is_pinned', False),
            'rotation':    data.get('rotation', 0),
        }
        task = TodoTask.objects.create(
            user=request.user,
            category='NOTE',
            metadata=metadata,
            is_done=False,
            is_pinned=bool(metadata['is_pinned']),
            auto_delete=False,
            delete_at=None
        )
        return JsonResponse({'success': True, 'task_id': task.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def todo_add_reminder(request):
    """Creates a new REMINDER TodoTask from a JSON body.

    Required fields
    ---------------
    title       : non-empty string
    recurrence  : one of 'once' | 'daily' | 'weekly' | 'monthly' | 'every_n_days'

    Optional fields
    ---------------
    note            : str  (default '')
    fire_at         : ISO datetime string — required when recurrence='once'
    time_str        : HH:MM 24 h string — required for all recurring types
    days_of_week    : list[int 0-6] — required for 'weekly'
    day_of_month    : int 1-31 — required for 'monthly'
    interval_days   : int >= 1 — required for 'every_n_days'
    until_date      : ISO date string (optional for recurring)
    email_notify    : bool (default False)
    alarm_enabled   : bool (default True)
    """
    try:
        data = json.loads(request.body)

        # ── Required fields ──────────────────────────────────────────
        title = str(data.get('title', '')).strip()
        if not title:
            return JsonResponse({'success': False, 'error': 'title is required.'})

        valid_recurrences = {'once', 'daily', 'weekly', 'monthly', 'every_n_days'}
        recurrence = data.get('recurrence')
        if recurrence not in valid_recurrences:
            return JsonResponse({'success': False, 'error': f'recurrence must be one of: {", ".join(sorted(valid_recurrences))}'})

        # ── Build metadata ───────────────────────────────────────────
        metadata = {
            'title':          title,
            'recurrence':     recurrence,
            'note':           str(data.get('note', '')),
            'email_notify':   bool(data.get('email_notify', False)),
            'alarm_enabled':  bool(data.get('alarm_enabled', True)),
        }

        # Conditional fields — include only when present in body
        for optional_key in ('time_str', 'days_of_week', 'day_of_month', 'interval_days', 'fire_at', 'until_date'):
            if optional_key in data:
                metadata[optional_key] = data[optional_key]

        # ── auto_delete / delete_at logic ────────────────────────────
        if recurrence == 'once':
            fire_at_raw = data.get('fire_at')
            if not fire_at_raw:
                return JsonResponse({'success': False, 'error': 'fire_at is required when recurrence is "once".'})
            dt = parse_flexible_datetime(str(fire_at_raw))
            if dt is None:
                return JsonResponse({'success': False, 'error': 'fire_at is not a valid datetime string.'})
            if not is_aware(dt):
                dt = make_aware(dt)
            auto_delete = True
            delete_at = dt
        else:
            # Recurring: optional until_date sets the expiry
            until_raw = data.get('until_date')
            delete_at = None
            if until_raw:
                until_dt = parse_flexible_datetime(str(until_raw))
                if until_dt is not None:
                    if not is_aware(until_dt):
                        until_dt = make_aware(until_dt)
                    delete_at = until_dt
            auto_delete = False

        task = TodoTask.objects.create(
            user=request.user,
            category='REMINDER',
            metadata=metadata,
            auto_delete=auto_delete,
            delete_at=delete_at,
            is_done=False,
            is_pinned=False,
        )
        return JsonResponse({'success': True, 'task_id': task.id})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@require_POST
def todo_update_reminder(request, task_id):
    """Partially updates an existing REMINDER TodoTask.

    Merges the supplied JSON body keys into the task's existing metadata
    without wiping keys that were not included in the request.

    Top-level body keys handled specially
    --------------------------------------
    is_done     : bool → task.is_done
    is_pinned   : bool → task.is_pinned

    Metadata keys that may be updated
    ----------------------------------
    title, recurrence, note, fire_at, time_str, days_of_week,
    day_of_month, interval_days, until_date, email_notify, alarm_enabled

    When recurrence changes to 'once' and fire_at is also supplied,
    auto_delete and delete_at are recomputed automatically.
    """
    task = get_object_or_404(TodoTask, id=task_id, user=request.user, category='REMINDER')
    try:
        data = json.loads(request.body)

        # Ensure metadata is a mutable dict
        current_meta = task.metadata if isinstance(task.metadata, dict) else {}

        # ── Merge metadata fields ────────────────────────────────────
        for key in ('title', 'recurrence', 'note', 'fire_at', 'time_str',
                    'days_of_week', 'day_of_month', 'interval_days', 'until_date'):
            if key in data:
                current_meta[key] = data[key]

        if 'email_notify' in data:
            current_meta['email_notify'] = bool(data['email_notify'])

        if 'alarm_enabled' in data:
            current_meta['alarm_enabled'] = bool(data['alarm_enabled'])

        task.metadata = current_meta

        # ── Top-level task flags ─────────────────────────────────────
        if 'is_done' in data:
            task.is_done = bool(data['is_done'])

        if 'is_pinned' in data:
            task.is_pinned = bool(data['is_pinned'])

        # ── Recompute auto_delete / delete_at when switching to 'once' ──
        new_recurrence = current_meta.get('recurrence')
        if new_recurrence == 'once' and 'fire_at' in data:
            dt = parse_flexible_datetime(str(data['fire_at']))
            if dt is not None:
                if not is_aware(dt):
                    dt = make_aware(dt)
                task.auto_delete = True
                task.delete_at = dt

        task.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
def guidy_contacts_api(request):
    """
    Returns classified contacts for creating groups or starting direct chats.
    - Teachers see all students, alumni, and other teachers.
    - Students see connected alumni.
    - Alumni see connected students.
    """
    from django.db.models import Q
    from django.contrib.auth.models import User as DjangoUser
    from users.utils import get_profile_photo_url, get_user_dashboard_type, get_user_display_name
    from .models import StudentProfile, StudentAchievement, ChatSession, GroupChatSession

    user = request.user
    is_teacher = user.is_staff or user.is_superuser
    is_alumni = StudentAchievement.objects.filter(user=user, status='approved').exists()
    is_student = StudentProfile.objects.filter(user=user).exists()

    # Find users who already have a direct chat with this user
    from .models import DirectChatSession
    chatted_user_ids = set()
    direct_chats = DirectChatSession.objects.filter(
        Q(user1=user) | Q(user2=user), is_active=True
    )
    for s in direct_chats:
        other_m = s.user2 if s.user1 == user else s.user1
        chatted_user_ids.add(other_m.id)

    sections_map = {
        'coaching batch -1': [],
        'coaching batch -2': [],
        'coaching batch -3': [],
        'coaching batch -4': [],
        'coaching spoken -1': [],
        'coaching spoken -2': [],
        'library 1st': [],
        'library ground': [],
        'alumni': [],
        'teachers': [],
        'guests': [],
        'contacts': [], # For students/alumni
    }

    if is_teacher:
        # 1. Students
        for sp in StudentProfile.objects.filter(status='admitted').select_related('user', 'seat'):
            sec = None
            if sp.service_type == 'Coaching':
                b = sp.batch
                if b == 'Grammar Batch 1':
                    sec = 'coaching batch -1'
                elif b == 'Grammar Batch 2':
                    sec = 'coaching batch -2'
                elif b == 'Grammar Batch 3':
                    sec = 'coaching batch -3'
                elif b == 'Grammar Batch 4':
                    sec = 'coaching batch -4'
                elif b == 'Spoken English 1':
                    sec = 'coaching spoken -1'
                elif b == 'Spoken English 2':
                    sec = 'coaching spoken -2'
            elif sp.service_type == 'Library':
                if sp.seat and sp.seat.floor == '1st Floor':
                    sec = 'library 1st'
                else:
                    sec = 'library ground'

            if sec:
                sections_map[sec].append({
                    'id': sp.user.id,
                    'name': sp.full_name,
                    'photo': get_profile_photo_url(sp.user),
                    'already_chatted': sp.user.id in chatted_user_ids,
                    'category': 'student'
                })

        # 2. Alumni
        for ach in StudentAchievement.objects.filter(status='approved').select_related('user'):
            sections_map['alumni'].append({
                'id': ach.user.id,
                'name': get_user_display_name(ach.user),
                'photo': get_profile_photo_url(ach.user),
                'already_chatted': ach.user.id in chatted_user_ids,
                'category': 'alumni'
            })

        # 3. Other Teachers
        for tu in DjangoUser.objects.filter(Q(is_staff=True) | Q(is_superuser=True)).exclude(id=user.id):
            name = get_user_display_name(tu)

            sections_map['teachers'].append({
                'id': tu.id,
                'name': name,
                'photo': get_profile_photo_url(tu),
                'already_chatted': tu.id in chatted_user_ids,
                'category': 'teacher',
                'is_verified': True,
            })

        # 4. Guest Users (Not admitted student, not approved alumni, not staff/superuser)
        admitted_student_user_ids = StudentProfile.objects.filter(status='admitted').values_list('user_id', flat=True)
        approved_alumni_user_ids = StudentAchievement.objects.filter(status='approved').values_list('user_id', flat=True)
        
        guest_users = DjangoUser.objects.filter(
            is_staff=False,
            is_superuser=False
        ).exclude(
            id__in=admitted_student_user_ids
        ).exclude(
            id__in=approved_alumni_user_ids
        ).select_related('profile')

        for gu in guest_users:
            sections_map['guests'].append({
                'id': gu.id,
                'name': gu.get_full_name() or gu.username,
                'photo': get_profile_photo_url(gu),
                'already_chatted': gu.id in chatted_user_ids,
                'category': 'guest'
            })

        order = [
            'coaching batch -1', 'coaching batch -2', 'coaching batch -3', 'coaching batch -4',
            'coaching spoken -1', 'coaching spoken -2', 'library 1st', 'library ground',
            'alumni', 'teachers', 'guests'
        ]
    else:
        # Students / Alumni see only connected contacts (mentorships)
        if is_student:
            sessions = ChatSession.objects.filter(request__student=user, is_active=True).select_related('request__alumni__user')
            for s in sessions:
                sections_map['contacts'].append({
                    'id': s.request.alumni.user.id,
                    'name': s.request.alumni.full_name,
                    'photo': get_profile_photo_url(s.request.alumni.user),
                    'already_chatted': True,
                    'category': 'alumni'
                })
        elif is_alumni:
            al_profile = StudentAchievement.objects.filter(user=user, status='approved').first()
            if al_profile:
                sessions = ChatSession.objects.filter(request__alumni=al_profile, is_active=True).select_related('request__student')
                for s in sessions:
                    sections_map['contacts'].append({
                        'id': s.request.student.id,
                        'name': s.request.student.get_full_name() or s.request.student.username,
                        'photo': get_profile_photo_url(s.request.student),
                        'already_chatted': True,
                        'category': 'student'
                    })
        
        # Add direct chat contacts for students/alumni
        chatted_users_already_added = {c['id'] for c in sections_map['contacts']}
        for uid in chatted_user_ids:
            if uid not in chatted_users_already_added:
                try:
                    tu = DjangoUser.objects.get(id=uid)
                    from users.utils import get_user_dashboard_type
                    category = get_user_dashboard_type(tu) or 'guest'
                    
                    name = get_user_display_name(tu)

                    sections_map['contacts'].append({
                        'id': tu.id,
                        'name': name,
                        'photo': get_profile_photo_url(tu),
                        'already_chatted': True,
                        'category': category
                    })
                except DjangoUser.DoesNotExist:
                    pass
        order = ['contacts']

    response_sections = []
    for key in order:
        contacts = sections_map[key]
        if contacts:
            contacts.sort(key=lambda x: x['already_chatted'], reverse=True)
            response_sections.append({
                'title': key,
                'contacts': contacts
            })

    return JsonResponse({'success': True, 'sections': response_sections})


@login_required
@require_POST
def guidy_teacher_direct_chat(request):
    """Starts or opens a direct 1-to-1 chat with a student/alumni/teacher/guest using DirectChatSession."""
    user = request.user
    other_user_id = request.POST.get('user_id')
    if not other_user_id:
        return JsonResponse({'success': False, 'error': 'User ID required'}, status=400)

    from django.contrib.auth.models import User as DjangoUser
    from .models import DirectChatSession
    from django.db.models import Q
    other_user = get_object_or_404(DjangoUser, id=other_user_id)

    # Permission check: At least one of the users must be a teacher (staff/superuser)
    user_is_teacher = user.is_staff or user.is_superuser
    other_is_teacher = other_user.is_staff or other_user.is_superuser
    
    if not (user_is_teacher or other_is_teacher):
        return JsonResponse({'success': False, 'error': 'Only direct chats involving a teacher are permitted.'}, status=403)
    
    direct_session = DirectChatSession.objects.filter(
        (Q(user1=user) & Q(user2=other_user)) | 
        (Q(user1=other_user) & Q(user2=user))
    ).first()
    
    if not direct_session:
        u1, u2 = sorted([user, other_user], key=lambda u: u.id)
        direct_session = DirectChatSession.objects.create(
            user1=u1,
            user2=u2,
            is_active=True
        )

    return JsonResponse({'success': True, 'direct_id': direct_session.id})


@login_required
@require_POST
def guidy_update_teacher_profile(request):
    """Allows teachers to update their profile details and photo in Guidy."""
    user = request.user
    if not (user.is_staff or user.is_superuser):
        return JsonResponse({'success': False, 'error': 'Only teachers/staff can edit profiles'}, status=403)

    from users.models import TeacherProfile
    profile, _ = TeacherProfile.objects.get_or_create(user=user)

    display_name = request.POST.get('name')
    about = request.POST.get('about')
    role_title = request.POST.get('role_title')
    mobile_number = request.POST.get('mobile_number')
    detail1 = request.POST.get('detail1')
    detail2 = request.POST.get('detail2')
    detail3 = request.POST.get('detail3')
    emails = request.POST.get('emails')
    mobile_numbers = request.POST.get('mobile_numbers')
    whatsapp_numbers = request.POST.get('whatsapp_numbers')

    if display_name is not None:
        profile.display_name = display_name.strip()
    if about is not None:
        profile.about = about.strip()
    if role_title is not None:
        profile.role_title = role_title.strip()
    if mobile_number is not None:
        profile.mobile_number = mobile_number.strip()
    if detail1 is not None:
        profile.detail1 = detail1.strip()
    if detail2 is not None:
        profile.detail2 = detail2.strip()
    if detail3 is not None:
        profile.detail3 = detail3.strip()
    if emails is not None:
        profile.emails = emails.strip()
    if mobile_numbers is not None:
        profile.mobile_numbers = mobile_numbers.strip()
        parts = [p.strip() for p in mobile_numbers.split(',') if p.strip()]
        if parts:
            profile.mobile_number = parts[0]
        else:
            profile.mobile_number = ''
    if whatsapp_numbers is not None:
        profile.whatsapp_numbers = whatsapp_numbers.strip()

    photo_action = request.POST.get('photo_action')
    remove_photo = request.POST.get('remove_photo')
    
    if photo_action == 'remove' or remove_photo == 'true':
        if profile.photo:
            try:
                import os
                if os.path.isfile(profile.photo.path):
                    os.remove(profile.photo.path)
            except Exception:
                pass
        profile.photo = None
    elif 'photo' in request.FILES:
        profile.photo = request.FILES['photo']

    profile.save()

    photo_url = get_profile_photo_url(user)
    return JsonResponse({
        'success': True,
        'photo_url': photo_url,
        'name': profile.display_name,
        'about': profile.about,
        'role_title': profile.role_title,
        'mobile_number': profile.mobile_number,
        'emails': profile.emails,
        'mobile_numbers': profile.mobile_numbers,
        'whatsapp_numbers': profile.whatsapp_numbers,
        'detail1': profile.detail1,
        'detail2': profile.detail2,
        'detail3': profile.detail3,
    })


@login_required
def guidy_search_group_messages(request, group_id):
    """Search messages within a group/direct chat session. Returns matching message IDs."""
    from django.db.models import Q
    import datetime
    from .models import GroupChatSession

    group = get_object_or_404(GroupChatSession, id=group_id, is_active=True)
    user = request.user

    if user not in group.members.all() and group.created_by != user:
        return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

    q = request.GET.get('q', '').strip()
    if not q:
        return JsonResponse({'success': True, 'results': []})

    parsed_date = None
    for fmt in ('%d/%m/%Y', '%d-%m-%Y', '%Y-%m-%d', '%d/%m/%y', '%d-%m-%y'):
        try:
            parsed_date = datetime.datetime.strptime(q, fmt).date()
            break
        except ValueError:
            pass

    query_filter = Q(content__icontains=q)
    if parsed_date:
        query_filter |= Q(timestamp__date=parsed_date)

    matches = group.messages.filter(
        query_filter,
        is_deleted_for_all=False
    ).order_by('timestamp')[:50]

    results = [{
        'id': m.id,
        'content': m.content,
        'timestamp': localtime(m.timestamp).strftime('%H:%M %d/%m/%Y'),
        'is_mine': (m.sender == user)
    } for m in matches]

    return JsonResponse({'success': True, 'results': results})


@login_required
@require_POST
def guidy_group_update_settings(request, group_id):
    """Allows the group admin (creator) or a teacher member to change name, photo, and description."""
    from .models import GroupChatSession
    group = get_object_or_404(GroupChatSession, id=group_id, is_active=True)
    is_admin = (group.created_by == request.user)
    is_teacher_member = (request.user.is_staff or request.user.is_superuser) and request.user in group.members.all()
    if not (is_admin or is_teacher_member):
        return JsonResponse({'success': False, 'error': 'Only the group admin or a teacher member can update settings'}, status=403)

    name = request.POST.get('name', '').strip()
    photo_file = request.FILES.get('photo')
    description = request.POST.get('description')
    remove_photo = request.POST.get('remove_photo') == 'true'

    # Validate photo size (max 2 MB)
    if photo_file and photo_file.size > 2 * 1024 * 1024:
        return JsonResponse({'success': False, 'error': 'Photo must be under 2 MB'}, status=400)

    if name and name != group.name:
        GroupMessage.objects.create(
            group=group,
            sender=request.user,
            content=f"system_user:{request.user.id} changed the group name to \"{name}\"",
            message_type='system'
        )
        group.name = name

    if remove_photo:
        if group.photo:
            group.photo.delete(save=False)
            group.photo = None
            GroupMessage.objects.create(
                group=group,
                sender=request.user,
                content=f"system_user:{request.user.id} removed this group's profile picture",
                message_type='system'
            )
    elif photo_file:
        if group.photo:
            group.photo.delete(save=False)
        GroupMessage.objects.create(
            group=group,
            sender=request.user,
            content=f"system_user:{request.user.id} changed this group's profile picture",
            message_type='system'
        )
        group.photo = photo_file

    if description is not None and description.strip() != group.description:
        GroupMessage.objects.create(
            group=group,
            sender=request.user,
            content=f"system_user:{request.user.id} changed the group description",
            message_type='system'
        )
        group.description = description.strip()

    group.save()
    
    photo_url = group.photo.url if group.photo else None
    return JsonResponse({
        'success': True,
        'name': group.name,
        'description': group.description,
        'photo_url': photo_url
    })


@login_required
@require_POST
def guidy_group_manage_members(request, group_id):
    """Allows the group admin or a teacher member to manage members, or any member to leave/exit.
    Supports bulk operations via comma-separated member_ids."""
    from .models import GroupChatSession, StudentProfile, ChatSession
    group = get_object_or_404(GroupChatSession, id=group_id, is_active=True)

    action = request.POST.get('action')  # 'add', 'remove', or 'exit'
    member_id = request.POST.get('member_id', '')
    member_ids_raw = request.POST.get('member_ids', '')

    if not action:
        return JsonResponse({'success': False, 'error': 'Action is required'}, status=400)

    from django.contrib.auth.models import User as DjangoUser

    # Build list of target member IDs (supports single member_id or comma-separated member_ids)
    target_ids = []
    if member_ids_raw:
        target_ids = [int(i.strip()) for i in member_ids_raw.split(',') if i.strip().isdigit()]
    elif member_id:
        target_ids = [int(member_id)]

    if not target_ids:
        return JsonResponse({'success': False, 'error': 'member_id or member_ids required'}, status=400)

    # Exiting self (leave group) — only uses first ID
    if action == 'exit':
        exit_user = get_object_or_404(DjangoUser, id=target_ids[0])
        if exit_user != request.user:
            return JsonResponse({'success': False, 'error': 'You can only exit yourself'}, status=403)
        if exit_user == group.created_by:
            group.is_active = False
            group.deleted_by_user = exit_user
            group.deleted_at = timezone.now()
            group.save()
            group.deleted_for_users.add(exit_user)
            from .models import GroupMessage
            GroupMessage.objects.create(
                group=group,
                sender=exit_user,
                content=f"system_user:{exit_user.id} deleted this group. Messages and media will automatically be purged in 30 days.",
                message_type='system'
            )
            member_count = group.members.count()
            cleared_count = group.deleted_for_users.count()
            if member_count == 0 or cleared_count >= member_count:
                purge_group_chat_session(group)
                return JsonResponse({'success': True, 'group_deleted': True, 'group_purged': True})
            return JsonResponse({'success': True, 'group_deleted': True})
        if exit_user in group.members.all():
            group.members.remove(exit_user)
            from .models import GroupMessage
            GroupMessage.objects.create(
                group=group,
                sender=exit_user,
                content=f"system_user:{exit_user.id} left",
                message_type='system'
            )
            return JsonResponse({'success': True})
        return JsonResponse({'success': False, 'error': 'Not a member of this group'}, status=400)

    # Permission check: admin OR teacher-member
    is_admin = (group.created_by == request.user)
    is_teacher_member = (request.user.is_staff or request.user.is_superuser) and request.user in group.members.all()
    if not (is_admin or is_teacher_member):
        return JsonResponse({'success': False, 'error': 'Only the group admin or a teacher member can manage members'}, status=403)

    if action == 'add':
        is_teacher = request.user.is_staff or request.user.is_superuser
        added_names = []
        for tid in target_ids:
            try:
                target_user = DjangoUser.objects.get(id=tid)
            except DjangoUser.DoesNotExist:
                continue
            # Skip if already a member
            if target_user in group.members.all():
                continue
            # Non-teacher requesters: validate connection
            if not is_teacher:
                is_student = StudentProfile.objects.filter(user=request.user).exists()
                if is_student:
                    sessions = ChatSession.objects.filter(request__student=request.user, is_active=True)
                    allowed_member_ids = {s.request.alumni.user.id for s in sessions}
                    if target_user.id not in allowed_member_ids:
                        continue
                    if target_user.is_staff or target_user.is_superuser:
                        continue
            group.members.add(target_user)
            from users.utils import get_user_display_name
            added_names.append(get_user_display_name(target_user))
        
        if added_names:
            added_names.sort()
            from .models import GroupMessage
            GroupMessage.objects.create(
                group=group,
                sender=request.user,
                content=f"system_user:{request.user.id} added {', '.join(added_names)}",
                message_type='system'
            )
        return JsonResponse({'success': True, 'added': len(added_names)})

    elif action == 'remove':
        removed_names = []
        for tid in target_ids:
            try:
                target_user = DjangoUser.objects.get(id=tid)
            except DjangoUser.DoesNotExist:
                continue
            # Cannot remove the group creator
            if target_user == group.created_by:
                continue
            # Cannot remove a teacher member
            if target_user.is_staff or target_user.is_superuser:
                continue
            if target_user in group.members.all():
                group.members.remove(target_user)
                from users.utils import get_user_display_name
                removed_names.append(get_user_display_name(target_user))
        
        if removed_names:
            removed_names.sort()
            from .models import GroupMessage
            GroupMessage.objects.create(
                group=group,
                sender=request.user,
                content=f"system_user:{request.user.id} removed {', '.join(removed_names)}",
                message_type='system'
            )
        return JsonResponse({'success': True, 'removed': len(removed_names)})

    elif action == 'delete':
        is_admin = (group.created_by == request.user)
        is_teacher_member = (request.user.is_staff or request.user.is_superuser) and request.user in group.members.all()
        if not (is_admin or is_teacher_member):
            return JsonResponse({'success': False, 'error': 'Only the group admin or a teacher member can delete the group'}, status=403)

        group.is_active = False
        group.deleted_by_user = request.user
        group.deleted_at = timezone.now()
        group.save()
        group.deleted_for_users.add(request.user)

        from .models import GroupMessage
        GroupMessage.objects.create(
            group=group,
            sender=request.user,
            content=f"system_user:{request.user.id} deleted this group. Messages and media will automatically be purged in 30 days.",
            message_type='system'
        )

        member_count = group.members.count()
        cleared_count = group.deleted_for_users.count()
        if member_count == 0 or cleared_count >= member_count:
            purge_group_chat_session(group)
            return JsonResponse({'success': True, 'group_deleted': True, 'group_purged': True})

        return JsonResponse({'success': True, 'group_deleted': True})

    return JsonResponse({'success': False, 'error': 'Invalid action'}, status=400)


@login_required
@require_POST
def guidy_delete_group_for_user(request, group_id):
    """Allows a member to delete / clear a deleted group from their own chat list."""
    from .models import GroupChatSession
    group = get_object_or_404(GroupChatSession, id=group_id)
    if request.user not in group.members.all() and group.created_by != request.user:
        return JsonResponse({'success': False, 'error': 'Not a member of this group'}, status=403)
    
    group.deleted_for_users.add(request.user)
    
    # Early Master Purge check: if all members have cleared it, purge immediately
    member_count = group.members.count()
    cleared_count = group.deleted_for_users.count()
    if not group.is_active and (member_count == 0 or cleared_count >= member_count):
        purge_group_chat_session(group)
        return JsonResponse({'success': True, 'group_purged': True})
        
    return JsonResponse({'success': True, 'cleared': True})


@login_required
def guidy_load_older(request):
    """
    Returns older messages for a chat session, direct session, or group session.
    """
    from datetime import timedelta
    from django.utils import timezone
    from django.http import JsonResponse
    from django.shortcuts import get_object_or_404
    from .models import ChatSession, DirectChatSession, GroupChatSession, StudentAchievement
    from users.utils import get_user_display_name, get_profile_photo_url

    chat_type = request.GET.get('type')
    chat_id = request.GET.get('id')
    oldest_id = request.GET.get('oldest_id')

    if not chat_type or not chat_id or not oldest_id:
        return JsonResponse({'success': False, 'error': 'Missing parameters'}, status=400)

    try:
        chat_id = int(chat_id)
        oldest_id = int(oldest_id)
    except ValueError:
        return JsonResponse({'success': False, 'error': 'Invalid parameter types'}, status=400)

    user = request.user
    ten_days_ago = timezone.now() - timedelta(days=10)

    if chat_type == 'session':
        session = get_object_or_404(ChatSession, id=chat_id)
        if not session.is_active and session.ended_by == user:
            return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)
        if session.request:
            is_participant = (
                session.request.student == user or
                session.request.alumni.user == user
            )
        else:
            is_participant = (
                session.user_one == user or
                session.user_two == user
            )
        if not is_participant:
            return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

        messages_qs = session.messages.filter(
            id__lt=oldest_id
        ).exclude(
            deleted_by=user
        ).exclude(
            is_deleted_for_all=True, deleted_at__lt=ten_days_ago
        ).select_related('sender', 'reply_to__sender').order_by('-timestamp')[:50]

    elif chat_type == 'direct':
        session = get_object_or_404(DirectChatSession, id=chat_id)
        if not session.is_active and session.ended_by == user:
            return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)
        is_participant = (
            session.user1 == user or
            session.user2 == user
        )
        if not is_participant:
            return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

        messages_qs = session.messages.filter(
            id__lt=oldest_id
        ).exclude(
            deleted_by=user
        ).exclude(
            is_deleted_for_all=True, deleted_at__lt=ten_days_ago
        ).select_related('sender', 'reply_to__sender').order_by('-timestamp')[:50]

    elif chat_type == 'group':
        session = get_object_or_404(GroupChatSession, id=chat_id, is_active=True)
        if user not in session.members.all() and session.created_by != user:
            return JsonResponse({'success': False, 'error': 'Forbidden'}, status=403)

        messages_qs = session.messages.filter(
            id__lt=oldest_id
        ).exclude(
            deleted_by=user
        ).exclude(
            is_deleted_for_all=True, deleted_at__lt=ten_days_ago
        ).select_related('sender', 'reply_to__sender').order_by('-timestamp')[:50]

    else:
        return JsonResponse({'success': False, 'error': 'Invalid chat type'}, status=400)

    data = []
    for msg in messages_qs:
        reply_preview = None
        if msg.reply_to:
            reply_preview = {
                'id': msg.reply_to.id,
                'content': msg.reply_to.content[:80],
                'sender': get_user_display_name(msg.reply_to.sender),
                'type': msg.reply_to.message_type,
            }

        # Determine read status
        if chat_type == 'group':
            is_read = msg.read_by.exclude(id=user.id).exists()
        else:
            is_read = msg.is_read

        data.append({
            'id': msg.id,
            'content': resolve_system_message_content(msg.content, user) if msg.message_type == 'system' else (msg.content or ("⏳ Media expired" if msg.media_expired else "")),
            'message_type': msg.message_type,
            'file_url': msg.file.url if msg.file else None,
            'file_name': msg.file_name,
            'timestamp': localtime(msg.timestamp).strftime('%H:%M'),
            'date': localtime(msg.timestamp).strftime('%Y-%m-%d'),
            'is_mine': (msg.sender == user),
            'is_read': is_read,
            'sender_name': get_user_display_name(msg.sender),
            'sender_photo': get_profile_photo_url(msg.sender),
            'is_pinned': msg.is_pinned,
            'reply_to': reply_preview,
            'is_deleted_for_all': msg.is_deleted_for_all,
            'media_expired': msg.media_expired,
            'is_verified': (msg.sender.is_staff or msg.sender.is_superuser),
        })

    return JsonResponse({
        'success': True,
        'messages': data
    })


@login_required
@require_POST
def guidy_block_user(request, user_id):
    """Blocks a user in Guidy."""
    from django.contrib.auth.models import User as DjangoUser
    from .models import GuidyBlock
    target_user = get_object_or_404(DjangoUser, id=user_id)
    if target_user == request.user:
        return JsonResponse({'success': False, 'error': 'Cannot block yourself'}, status=400)
    
    GuidyBlock.objects.get_or_create(blocker=request.user, blocked=target_user)
    return JsonResponse({'success': True, 'message': 'User blocked successfully'})


@login_required
@require_POST
def guidy_unblock_user(request, user_id):
    """Unblocks a user in Guidy."""
    from django.contrib.auth.models import User as DjangoUser
    from .models import GuidyBlock
    target_user = get_object_or_404(DjangoUser, id=user_id)
    
    GuidyBlock.objects.filter(blocker=request.user, blocked=target_user).delete()
    return JsonResponse({'success': True, 'message': 'User unblocked successfully'})


@login_required
def guidy_blocked_list(request):
    """Returns the list of users blocked by the current user."""
    from .models import GuidyBlock, StudentAchievement
    from .utils import get_profile_photo_url, get_user_dashboard_type, get_user_display_name
    
    blocks = GuidyBlock.objects.filter(blocker=request.user).select_related('blocked')
    data = []
    for b in blocks:
        u = b.blocked
        role = get_user_dashboard_type(u) or 'student'
        name = get_user_display_name(u)

        data.append({
            'id': u.id,
            'name': name,
            'photo_url': get_profile_photo_url(u),
            'role': role.capitalize(),
        })
    return JsonResponse({'success': True, 'blocked_users': data})


@login_required
def update_contact_info_api(request):
    """
    AJAX endpoint to update student's contact details (email and/or WhatsApp number)
    when locked out upon dashboard access.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)
    
    try:
        data = json.loads(request.body or '{}')
        email = (data.get('email') or '').strip()
        whatsapp = (data.get('whatsapp_number') or '').strip()
        
        from users.models import StudentProfile, StudentAchievement
        from django.contrib.auth.models import User as DjangoUser
        from django.db import models
        
        user = request.user
        try:
            profile = StudentProfile.objects.get(user=user)
        except StudentProfile.DoesNotExist:
            return JsonResponse({'status': 'error', 'message': 'Student profile not found.'}, status=404)
        
        # Validate Email if provided
        if email:
            email = email.lower().strip()
            import re
            if not re.match(r'^[\w\.-]+@[\w\.-]+\.\w+$', email):
                return JsonResponse({'status': 'error', 'message': 'Please enter a valid email address.'}, status=400)
            
            # Check unique email across DjangoUser, StudentProfile (all statuses including pending/admitted), and StudentAchievement
            if DjangoUser.objects.filter(email__iexact=email).exclude(pk=user.pk).exists() or \
               StudentProfile.objects.filter(email__iexact=email).exclude(user=user).exists() or \
               StudentAchievement.objects.filter(email__iexact=email).exclude(user=user).exists():
                return JsonResponse({'status': 'error', 'message': 'This email address is already registered in the system.'}, status=400)

        # Validate Whatsapp if provided
        if whatsapp:
            whatsapp = whatsapp.strip()
            if not whatsapp.isdigit() or len(whatsapp) != 10:
                return JsonResponse({'status': 'error', 'message': 'WhatsApp number must be exactly 10 digits.'}, status=400)
            
            # Check uniqueness of whatsapp number across StudentProfile and StudentAchievement
            if StudentProfile.objects.filter(models.Q(whatsapp_number=whatsapp) | models.Q(mobile_number=whatsapp)).exclude(user=user).exists() or \
               StudentAchievement.objects.filter(models.Q(whatsapp_number=whatsapp) | models.Q(mobile_number=whatsapp)).exclude(user=user).exists():
                return JsonResponse({'status': 'error', 'message': 'This contact number is already registered by another student.'}, status=400)
        
        # Save to DB
        if email:
            # Only set user.email if User model currently has no email (e.g. manual student)
            if not user.email:
                user.email = email
                user.save(update_fields=['email'])
            profile.email = email
        if whatsapp:
            profile.whatsapp_number = whatsapp
            
        profile.save()
        
        # Sync to StudentAchievement (alumni profile) if exists
        achievement = StudentAchievement.objects.filter(user=user).first()
        if achievement:
            if email:
                achievement.email = email
            if whatsapp:
                achievement.whatsapp_number = whatsapp
            achievement.save()
            
        return JsonResponse({'status': 'success', 'message': 'Contact information updated successfully.'})
    
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def request_seat_switch_api(request):
    """
    API endpoint for students to request/update a seat/shift switch.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    from users.models import StudentProfile, Seat, SeatSwitchRequest
    import json

    try:
        student = StudentProfile.objects.get(user=request.user)
    except StudentProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Student profile not found.'}, status=404)

    try:
        data = json.loads(request.body or '{}')
        seat_number = str(data.get('seat_number') or '').strip()
        floor = str(data.get('floor') or '').strip()
        shift = str(data.get('shift') or '').strip()
        is_temporary = bool(data.get('is_temporary', False))
        temp_hold_days = int(data.get('temp_hold_days', 0))

        if not seat_number or not floor or not shift:
            return JsonResponse({'status': 'error', 'message': 'seat_number, floor and shift are required.'}, status=400)

        target_seat = Seat.objects.filter(floor=floor, seat_number=seat_number).first()
        if not target_seat:
            return JsonResponse({'status': 'error', 'message': 'Target seat not found.'}, status=404)

        # Create or update pending request
        req, created = SeatSwitchRequest.objects.get_or_create(
            student=student,
            status='pending',
            defaults={
                'target_seat': target_seat,
                'target_shift': shift,
                'is_temporary': is_temporary,
                'temp_hold_days': temp_hold_days
            }
        )

        if not created:
            req.target_seat = target_seat
            req.target_shift = shift
            req.is_temporary = is_temporary
            req.temp_hold_days = temp_hold_days
            req.save()

        return JsonResponse({'status': 'success', 'message': 'Seat switch request submitted successfully.'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def cancel_seat_switch_api(request):
    """
    API endpoint for students to cancel and delete their pending seat/shift switch request.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    from users.models import StudentProfile, SeatSwitchRequest

    try:
        student = StudentProfile.objects.get(user=request.user)
        SeatSwitchRequest.objects.filter(student=student, status='pending').delete()
        return JsonResponse({'status': 'success', 'message': 'Pending switch request cancelled and deleted.'})
    except StudentProfile.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Student profile not found.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@user_passes_test(lambda u: u.is_staff)
def approve_seat_switch(request, pk):
    """
    Teacher endpoint to approve a pending seat switch request.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    from django.db import transaction
    from users.models import SeatSwitchRequest, SeatAssignment
    from users.utils import create_notification
    
    try:
        with transaction.atomic():
            req = SeatSwitchRequest.objects.select_for_update().get(pk=pk, status='pending')
            student = req.student
            target_seat = req.target_seat
            target_shift = req.target_shift

            # --- CONFLICT CHECK ---
            conflict_assignment = SeatAssignment.objects.filter(
                seat=target_seat,
                is_active=True,
                shift_type__in=[target_shift, 'full'] if target_shift != 'full' else ['morning', 'evening', 'full']
            ).select_related('student').first()

            if conflict_assignment:
                is_partial_mode = req.is_temporary
                is_owner_on_hold = conflict_assignment.hold_status == 'active' and not conflict_assignment.is_partial
                
                if not (is_partial_mode and is_owner_on_hold):
                    return JsonResponse({
                        'status': 'conflict',
                        'message': f"Seat is already occupied by {conflict_assignment.student.full_name}",
                        'occupied_by': conflict_assignment.student.full_name,
                        'request_id': req.id
                    }, status=409)

            # --- DEACTIVATE OLD SEAT ---
            old_seat = student.seat
            if old_seat:
                old_assignments = SeatAssignment.objects.filter(student=student, is_active=True)
                for a in old_assignments:
                    a.deactivate()

            # --- PERFORM SWITCH ---
            is_partial_mode = req.is_temporary
            
            new_assignment = SeatAssignment.objects.create(
                seat=target_seat,
                student=student,
                shift_type=target_shift,
                is_active=True,
                is_partial=is_partial_mode,
                allow_hold_override=True
            )
            
            if is_partial_mode:
                owner = SeatAssignment.objects.filter(
                    seat=target_seat,
                    is_active=True,
                    hold_status='active',
                    is_partial=False
                ).first()
                if owner and owner.hold_end_date:
                    new_assignment.hold_end_date = owner.hold_end_date
                    new_assignment.save(update_fields=['hold_end_date'])

            student.seat = target_seat
            student.shift = target_shift
            student.save(update_fields=['seat', 'shift'])

            if old_seat:
                old_seat.recalc_status(save=True)
            target_seat.recalc_status(save=True)

            req.status = 'approved'
            req.save(update_fields=['status'])

            create_notification(
                user=student.user,
                title="Seat Switch Approved",
                message=f"Your request to switch to seat {target_seat.seat_number} ({target_shift.capitalize()}) has been approved!",
                category="seat_change"
            )

            try:
                notifications.send_seat_switch_approval_email(student, target_seat, target_shift)
            except Exception:
                pass

            return JsonResponse({'status': 'success', 'message': 'Request approved successfully.'})

    except SeatSwitchRequest.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Request not found or already processed.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@user_passes_test(lambda u: u.is_staff)
def reject_seat_switch(request, pk):
    """
    Teacher endpoint to reject a pending seat switch request.
    """
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)

    from users.models import SeatSwitchRequest
    from users.utils import create_notification

    try:
        req = SeatSwitchRequest.objects.get(pk=pk, status='pending')
        student = req.student

        req.status = 'rejected'
        req.save(update_fields=['status'])
        req.delete()  # Remove request to vanish it

        create_notification(
            user=student.user,
            title="Seat Switch Rejected",
            message=f"Your request to switch to seat {req.target_seat.seat_number} has been rejected.",
            category="seat_change"
        )

        try:
            notifications.send_seat_rejection_email(student, req.target_seat, req.target_shift)
        except Exception:
            pass

        return JsonResponse({'status': 'success', 'message': 'Request rejected successfully.'})

    except SeatSwitchRequest.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Request not found or already processed.'}, status=404)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


# ==============================================================================
# SEO: ROBOTS.TXT & DYNAMIC XML SITEMAP
# ==============================================================================

def robots_txt_view(request):
    """
    SEO robots.txt view allowing search engine indexation of public pages
    while protecting authenticated and administrative routes.
    """
    from django.http import HttpResponse
    try:
        site_url = f"{request.scheme}://{request.get_host()}".rstrip('/')
    except Exception:
        site_url = getattr(settings, 'SITE_URL', 'https://abcd2013.online').rstrip('/')

    lines = [
        "User-agent: *",
        "Allow: /",
        "Allow: /about/",
        "Allow: /services/",
        "Allow: /contact/",
        "Allow: /courses/",
        "Allow: /admission-form/",
        "Allow: /library-availability/",
        "Allow: /hall-of-fame/",
        "Allow: /resolved-complaints/",
        "Allow: /static/",
        "",
        "Disallow: /admin/",
        "Disallow: /teacher/",
        "Disallow: /dashboard/",
        "Disallow: /alumni/",
        "Disallow: /todo/",
        "Disallow: /guidy/",
        "Disallow: /api/",
        "Disallow: /auth/",
        "Disallow: /post-login/",
        "",
        f"Sitemap: {site_url}/sitemap.xml",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def sitemap_xml_view(request):
    """
    Dynamic XML Sitemap generating clean URLs for search engine discovery.
    """
    from django.http import HttpResponse
    from django.utils import timezone
    from users.models import Course

    try:
        site_url = f"{request.scheme}://{request.get_host()}".rstrip('/')
    except Exception:
        site_url = getattr(settings, 'SITE_URL', 'https://abcd2013.online').rstrip('/')

    now_str = timezone.now().strftime('%Y-%m-%d')

    # Static public routes
    static_urls = [
        {'loc': f"{site_url}/", 'priority': '1.0', 'changefreq': 'daily'},
        {'loc': f"{site_url}/about/", 'priority': '0.8', 'changefreq': 'monthly'},
        {'loc': f"{site_url}/services/", 'priority': '0.8', 'changefreq': 'monthly'},
        {'loc': f"{site_url}/contact/", 'priority': '0.7', 'changefreq': 'monthly'},
        {'loc': f"{site_url}/admission-form/", 'priority': '0.9', 'changefreq': 'weekly'},
        {'loc': f"{site_url}/library-availability/", 'priority': '0.9', 'changefreq': 'daily'},
        {'loc': f"{site_url}/courses/", 'priority': '0.9', 'changefreq': 'weekly'},
        {'loc': f"{site_url}/hall-of-fame/", 'priority': '0.8', 'changefreq': 'weekly'},
        {'loc': f"{site_url}/resolved-complaints/", 'priority': '0.6', 'changefreq': 'weekly'},
        {'loc': f"{site_url}/login/", 'priority': '0.5', 'changefreq': 'monthly'},
        {'loc': f"{site_url}/register/", 'priority': '0.5', 'changefreq': 'monthly'},
    ]

    # Dynamic active courses
    dynamic_urls = []
    try:
        courses = Course.objects.filter(is_active=True).values_list('id', flat=True)
        for c_id in courses:
            dynamic_urls.append({
                'loc': f"{site_url}/courses/{c_id}/",
                'priority': '0.8',
                'changefreq': 'weekly'
            })
    except Exception:
        pass

    all_urls = static_urls + dynamic_urls

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for item in all_urls:
        xml_lines.append('  <url>')
        xml_lines.append(f"    <loc>{item['loc']}</loc>")
        xml_lines.append(f"    <lastmod>{now_str}</lastmod>")
        xml_lines.append(f"    <changefreq>{item['changefreq']}</changefreq>")
        xml_lines.append(f"    <priority>{item['priority']}</priority>")
        xml_lines.append('  </url>')

    xml_lines.append('</urlset>')
    xml_content = "\n".join(xml_lines)

    return HttpResponse(xml_content, content_type="application/xml")


# -------------------------------------------------------------------
# GOOGLE OAUTH PIPELINE HELPERS
# -------------------------------------------------------------------
def link_existing_account_by_email(backend, details, user=None, *args, **kwargs):
    """
    If a user with the same email already exists, link the social account
    to that existing user instead of failing or creating a duplicate user.
    """
    if user:
        return {'user': user}

    email = details.get('email')
    if not email:
        return None

    existing_user = User.objects.filter(email__iexact=email).first()
    if existing_user:
        return {'user': existing_user, 'is_new': False}
    
    return None


def set_new_user_flag(backend, user, response, is_new=False, *args, **kwargs):
    """
    Pipeline step for new Google registrations.
    New users start as guests until they fill out the Admission or Achievement form.
    """
    if is_new and user:
        user.is_active = True
        user.save()
    return None





