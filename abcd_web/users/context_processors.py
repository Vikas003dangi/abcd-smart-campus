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
    }

    try:
        if not request.user.is_authenticated:
            return default_context

        cache_key = f"student_context_data_{request.user.id}"
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
            'VAPID_PUBLIC_KEY': getattr(settings, 'VAPID_PUBLIC_KEY', ''),
        }
        
        from .utils import get_user_dashboard_type
        dtype = get_user_dashboard_type(request.user)
        if dtype is None:
            dtype = 'guest'
        if dtype == 'guest' and request.session.get('active_dashboard') in ['student', 'alumni']:
            request.session['active_dashboard'] = 'guest'

        mapping = {
            'teacher': 'users/teacher_dashboard.html',
            'student': 'users/student_dashboard.html',
            'alumni':  'users/student_dashboard.html',
            'guest':   'users/guest_page.html',
        }
        context['base_template'] = mapping.get(dtype, 'home_page.html')

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
                if profile.status == 'admitted':
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

            context.update({
                'is_approved_coaching': is_approved_coaching,
                'is_approved_library': is_approved_library,
                'is_approved_alumni': is_approved_alumni,
                'has_pending_coaching': has_pending_coaching,
                'has_pending_library': has_pending_library,
                'has_pending_alumni': has_pending_alumni,
            })

        try:
            cache.set(cache_key, context, 5)  # Cache for 5 seconds
        except Exception:
            pass

        return context
    except Exception:
        return default_context
