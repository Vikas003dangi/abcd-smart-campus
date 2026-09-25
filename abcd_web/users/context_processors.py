from django.core.cache import cache
from .models import StudentProfile, Notification, StudentAchievement
from .models import GuidanceRequest, Message as GuidyMessage, BlockedGuidance

def student_context(request):
    """
    Context processor to provide student profile, unread notification count,
    alumni achievement, and Guidy notification badge to all templates.
    Cached for 5 seconds to prevent redundant DB queries on consecutive page loads.
    """
    default_context = {
        'profile': None,
        'nav_achievement': None,
        'unread_count': 0,
        'guidy_badge_count': 0,
        'base_template': 'home_page.html',
        'is_approved_coaching': False,
        'is_approved_library': False,
        'is_approved_alumni': False,
        'has_pending_coaching': False,
        'has_pending_library': False,
        'has_pending_alumni': False,
        'has_dual_profile': False,
        'is_dual_user': False,
        'has_student_profile': False,
        'has_alumni_profile': False,
        'current_dashboard_role': 'guest',
        'user_home_base_url': '/',
    }

    try:
        if not request.user.is_authenticated:
            return default_context

        active_dash = request.session.get('active_dashboard', '')
        cache_key = f"student_context_data_{request.user.id}_{active_dash}"
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            pass

        from django.conf import settings
        context = {
            'profile': None,
            'nav_achievement': None,
            'unread_count': 0,
            'guidy_badge_count': 0,
            'base_template': 'home_page.html',
            'user_home_base_url': '/',
            'VAPID_PUBLIC_KEY': getattr(settings, 'VAPID_PUBLIC_KEY', ''),
        }
        
        from django.db.models import Q
        if request.user.is_staff or request.user.is_superuser:
            dtype = 'teacher'
        elif active_dash == 'alumni' and StudentAchievement.objects.filter(user=request.user).exists():
            dtype = 'alumni'
        elif active_dash == 'student' and StudentProfile.objects.filter(user=request.user).exists():
            dtype = 'student'
        else:
            from .utils import get_user_dashboard_type
            dtype = get_user_dashboard_type(request.user)

        if dtype is None:
            dtype = 'guest'
        if dtype == 'guest' and request.session.get('active_dashboard') in ['student', 'alumni']:
            request.session['active_dashboard'] = 'guest'

        mapping = {
            'teacher': 'users/teacher_dashboard.html',
            'student': 'users/student_dashboard.html',
            'alumni':  'users/alumni_dashboard.html',
            'guest':   'users/guest_page.html',
        }
        context['base_template'] = mapping.get(dtype, 'home_page.html')

        home_base_mapping = {
            'teacher': '/teacher/',
            'student': '/dashboard/',
            'alumni':  '/alumni/dashboard/',
            'guest':   '/guest-home/',
        }
        context['user_home_base_url'] = home_base_mapping.get(dtype, '/')

        try:
            from users.views import get_guidy_badge_count
            context['guidy_badge_count'] = get_guidy_badge_count(request.user)
        except Exception:
            context['guidy_badge_count'] = 0

        if not (request.user.is_staff or request.user.is_superuser):
            try:
                context['unread_count'] = Notification.objects.filter(
                    user=request.user, 
                    is_read=False
                ).count()
            except Exception:
                context['unread_count'] = 0
            
            # Default permission and status flags
            is_approved_coaching = False
            is_approved_library = False
            has_pending_coaching = False
            has_pending_library = False
            is_approved_alumni = False
            has_pending_alumni = False
            
            # Safely query StudentProfile
            profile = StudentProfile.objects.filter(user=request.user).first()
            if profile:
                context['profile'] = profile
                if profile.status in ['admitted', 'on_hold'] or profile.is_admitted:
                    if profile.service_type in ['Coaching', 'Both']:
                        is_approved_coaching = True
                    if profile.service_type in ['Library', 'Both']:
                        is_approved_library = True
                
                if profile.coaching_pending or (profile.status == 'pending' and profile.service_type in ['Coaching', 'Both']):
                    has_pending_coaching = True
                if profile.library_pending or (profile.status == 'pending' and profile.service_type in ['Library', 'Both']):
                    has_pending_library = True

            # Safely query StudentAchievement (alumni)
            ach = StudentAchievement.objects.filter(user=request.user).first()
            if ach:
                context['nav_achievement'] = ach
                if ach.status == 'approved':
                    is_approved_alumni = True
                elif ach.status == 'pending':
                    has_pending_alumni = True

            is_dual = bool(profile and ach)
            is_coaching_taken = is_approved_coaching or has_pending_coaching
            is_library_taken = is_approved_library or has_pending_library
            can_apply_admission = not (is_coaching_taken and is_library_taken)

            context.update({
                'is_approved_coaching': is_approved_coaching,
                'is_approved_library': is_approved_library,
                'is_approved_alumni': is_approved_alumni,
                'has_pending_coaching': has_pending_coaching,
                'has_pending_library': has_pending_library,
                'has_pending_alumni': has_pending_alumni,
                'can_apply_admission': can_apply_admission,
                'has_dual_profile': is_dual,
                'is_dual_user': is_dual,
                'has_student_profile': bool(profile),
                'has_alumni_profile': bool(ach),
                'current_dashboard_role': active_dash or dtype,
            })

        try:
            cache.set(cache_key, context, 5)  # Cache for 5 seconds
        except Exception:
            pass

        return context
    except Exception:
        return default_context
