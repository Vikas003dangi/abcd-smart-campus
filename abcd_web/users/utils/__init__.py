# users/utils/__init__.py
#
# When this package was created, Python stopped resolving `from .utils import …`
# to the flat utils.py file and started treating utils/ as the package.
# We load the flat file via importlib (by path) and register it in sys.modules
# so every existing import in views.py and management commands continues to work.

import sys as _sys
import importlib.util as _ilu
import os as _os

_flat_name = "users._utils_flat"
if _flat_name not in _sys.modules:
    _spec = _ilu.spec_from_file_location(
        _flat_name,
        _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "utils.py"),
    )
    _mod = _ilu.module_from_spec(_spec)
    _sys.modules[_flat_name] = _mod
    _spec.loader.exec_module(_mod)

# Re-export every public name from the flat utils.py
from users._utils_flat import (  # type: ignore[import]  # noqa: F401
    parse_flexible_datetime,
    process_scheduled_broadcasts,
    sync_courses_from_youtube,
    get_playlist_videos_for_course,
    get_individual_videos_for_course,
    track_visitor_intent,
    sync_active_holds,
    process_visitor_reminders,
    process_seat_availability_reminders,
    process_expired_seat_holds,
    process_seat_hold_lifecycle,
    process_expired_holds,
    process_todo_notifications,
    purge_todo_trash,
    send_todo_notification,
    process_offline_learning_reminders,
    process_birthday_wishes,
    get_user_dashboard_type,
    get_reminder_subject,
    INTENT_DELAYS,
    get_profile_photo_url,
    get_user_display_name,
    get_user_notification_email,
)




