# this file is located at abcd_web/users/templatetags/dict_extras.py

from django import template

register = template.Library()

@register.filter
def dict_lookup(dictionary, key):
    return dictionary.get(key)

@register.filter
def user_photo(user_or_obj):
    if not user_or_obj:
        return "/static/data/user.png"
    if hasattr(user_or_obj, 'photo') and user_or_obj.photo:
        try:
            url = user_or_obj.photo.url
            if url:
                return url
        except Exception:
            pass
    user = getattr(user_or_obj, 'user', user_or_obj)
    from users.utils import get_profile_photo_url
    return get_profile_photo_url(user)

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