# this file is located at abcd_web/users/templatetags/dict_extras.py

from django import template

register = template.Library()

@register.filter
def dict_lookup(dictionary, key):
    return dictionary.get(key)

@register.filter
def user_photo(user_or_obj, dashboard_type=None):
    if not user_or_obj:
        return "/static/data/user.png"
    if isinstance(user_or_obj, str):
        return user_or_obj
    if hasattr(user_or_obj, 'photo_url'):
        try:
            return user_or_obj.photo_url
        except Exception:
            pass
    if hasattr(user_or_obj, 'photo') and user_or_obj.photo:
        try:
            url = user_or_obj.photo.url
            if url:
                return url
        except Exception:
            pass
    user = getattr(user_or_obj, 'user', user_or_obj)
    from users.utils import get_profile_photo_url
    return get_profile_photo_url(user, dashboard_type=dashboard_type)

@register.simple_tag(takes_context=True)
def current_user_photo(context):
    request = context.get('request')
    user = context.get('user')
    if not user or not getattr(user, 'is_authenticated', False):
        return "/static/data/user.png"
    active_dash = None
    if request and hasattr(request, 'session'):
        active_dash = request.session.get('active_dashboard')
    from users.utils import get_profile_photo_url
    return get_profile_photo_url(user, dashboard_type=active_dash)

@register.filter
def user_display_name(user):
    from users.utils import get_user_display_name
    return get_user_display_name(user)

@register.filter
def format_message(content):
    import html
    import re
    from django.utils.safestring import mark_safe
    if not content:
        return ""
    escaped = html.escape(str(content))
    escaped = re.sub(r'&lt;br\s*/?&gt;', '<br>', escaped, flags=re.I)
    escaped = escaped.replace('\r\n', '<br>').replace('\r', '<br>').replace('\n', '<br>')
    escaped = re.sub(r'&lt;b&gt;', '<b>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;/b&gt;', '</b>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;strong&gt;', '<b>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;/strong&gt;', '</b>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;i&gt;', '<i>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;/i&gt;', '</i>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;em&gt;', '<i>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;/em&gt;', '</i>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;u&gt;', '<u>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;/u&gt;', '</u>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;s&gt;', '<s>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;/s&gt;', '</s>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;strike&gt;', '<s>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;/strike&gt;', '</s>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;del&gt;', '<s>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;/del&gt;', '</s>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;code&gt;', '<code>', escaped, flags=re.I)
    escaped = re.sub(r'&lt;/code&gt;', '</code>', escaped, flags=re.I)
    escaped = re.sub(
        r'&lt;span style=&quot;color:\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+|rgb\(\d+,\s*\d+,\s*\d+\));?&quot;&gt;',
        r'<span style="color:\1;">',
        escaped,
        flags=re.I
    )
    escaped = re.sub(r'&lt;/span&gt;', '</span>', escaped, flags=re.I)
    escaped = re.sub(
        r'&lt;font color=&quot;?\s*(#[0-9a-fA-F]{3,6}|[a-zA-Z]+|rgb\(\d+,\s*\d+,\s*\d+\))\s*&quot;?&gt;',
        r'<span style="color:\1;">',
        escaped,
        flags=re.I
    )
    escaped = re.sub(r'&lt;/font&gt;', '</span>', escaped, flags=re.I)

    # Convert any lingering <div> or <p> tags into <br> so raw tags are never shown
    escaped = re.sub(r'&lt;/(div|p)&gt;', '', escaped, flags=re.I)
    escaped = re.sub(r'&lt;(div|p)(\s+[^&]*)?&gt;', '<br>', escaped, flags=re.I)
    escaped = re.sub(r'(<br\s*/?>){3,}', '<br><br>', escaped, flags=re.I)
    return mark_safe(escaped)

@register.filter
def has_user_photo(user_or_obj):
    if not user_or_obj:
        return False
    
    # 0. Direct Profile / Achievement check
    if hasattr(user_or_obj, 'photo') and user_or_obj.photo:
        return True

    user = getattr(user_or_obj, 'user', user_or_obj)
    if not user:
        return False
    
    # 1. TeacherProfile check
    from users.models import TeacherProfile
    teacher_prof = TeacherProfile.objects.filter(user=user).first()
    if teacher_prof and teacher_prof.photo:
        return True
        
    # 2. Hardcoded Sandeep Sir/Asst photo check
    email_clean = (getattr(user, 'email', '') or '').strip().lower()
    if email_clean in ['abcd2013baq@gmail.com', 'vd19055@gmail.com']:
        return True
        
    # 3. StudentProfile / StudentAchievement photo check
    from users.models import StudentProfile, StudentAchievement
    profile = StudentProfile.objects.filter(user=user).first()
    if profile and profile.photo:
        return True
        
    achievement = StudentAchievement.objects.filter(user=user).first()
    if achievement and achievement.photo:
        return True
        
    # 4. Google OAuth picture check
    try:
        from social_django.models import UserSocialAuth
        social_user = UserSocialAuth.objects.filter(user=user, provider='google-oauth2').first()
        if social_user:
            pic_url = social_user.extra_data.get('picture') or social_user.extra_data.get('image')
            if pic_url:
                return True
    except Exception:
        pass
        
    return False


@register.filter
def possessive(name):
    """
    Applies English grammatical possessive rule:
    - Names ending in 's' or 'S' receive an apostrophe only (e.g. 'Vikas' -> "Vikas'")
    - All other names receive apostrophe-s (e.g. 'Suhani Singh' -> "Suhani Singh's")
    """
    if not name:
        return ""
    name_str = str(name).strip()
    if not name_str:
        return ""
    from django.utils.safestring import mark_safe
    from django.utils.html import escape
    escaped = escape(name_str)
    if name_str.endswith(('s', 'S')):
        return mark_safe(f"{escaped}'")
    return mark_safe(f"{escaped}'s")


@register.filter
def gender_avatar(obj_or_sex):
    """
    Resolves standard gender avatar URL:
    - Female -> default_avatar_female.png
    - Male -> default_avatar_male.png
    - Blank / Other -> default_avatar.png (neutral)
    """
    sex = ''
    if hasattr(obj_or_sex, 'sex'):
        sex = obj_or_sex.sex or ''
    elif hasattr(obj_or_sex, 'gender'):
        sex = obj_or_sex.gender or ''
    elif isinstance(obj_or_sex, str):
        sex = obj_or_sex

    s = str(sex).strip().lower()
    if s in ['female', 'f']:
        return '/static/data/default_avatar_female.png'
    elif s in ['male', 'm']:
        return '/static/data/default_avatar_male.png'
    return '/static/data/default_avatar.png'