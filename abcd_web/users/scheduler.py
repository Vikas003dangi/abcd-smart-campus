"""
users/scheduler.py
==================
Embedded Background Scheduler Daemon for ABCD Smart Campus.

Runs 24/7 inside the web server process (Daphne / Django runserver) to ensure
all automated, scheduled, background, and cleanup tasks execute reliably without
requiring an external paid worker dyno.

Features:
- Thread-safe singleton execution (prevents duplicate threads across reloader forks).
- Auto-reconnects and clears stale database connections before/after ticks.
- High-frequency pipeline (ticks every 60s): Broadcasts, To-Do reminders, course reminders.
- Daily pipeline (ticks once per calendar day or date rollover): 5-tier fee reminders,
  4-stage seat hold lifecycle & auto-promotions, birthday wishes, visitor reminders,
  and storage/database cleanup.
- Exposes `run_scheduler_cycle()` for external cron triggers (/api/cron/maintenance/).
"""

import os
import sys
import time
import threading
import logging
from datetime import datetime, time as dtime, timedelta
from django.utils import timezone
from django.db import close_old_connections
from django.core.management import call_command

logger = logging.getLogger(__name__)

# Track thread state, execution timestamps, and adaptive sleep wake event
_scheduler_lock = threading.Lock()
_scheduler_started = False
_wake_event = threading.Event()
_last_heartbeat = None
_next_expected_due = None
last_scheduler_run = None
last_daily_run = None


def notify_scheduler_task_changed():
    """
    Wakes the sleeping background scheduler thread immediately in RAM (0ms).
    Called by model post_save / post_delete signals when a time-sensitive task
    (TodoTask, LearningReminder, BroadcastMessage) is created, modified, or deleted.
    """
    try:
        _wake_event.set()
    except Exception as e:
        logger.debug(f"[ABCD Scheduler] Wake event notification error: {e}")


def get_scheduler_status():
    """
    Returns the current in-memory status of the scheduler for /api/cron/maintenance/.
    Allows the external cron endpoint to act as a zero-DB watchdog.
    """
    global _last_heartbeat, _next_expected_due, _scheduler_started
    now = timezone.localtime(timezone.now())
    is_alive = False
    heartbeat_age = None

    if _last_heartbeat:
        heartbeat_age = (now - _last_heartbeat).total_seconds()
        # Thread considered healthy if it ticked within the last 16 minutes (960s)
        is_alive = heartbeat_age < 960

    return {
        "started": _scheduler_started,
        "is_alive": is_alive,
        "heartbeat_age_seconds": round(heartbeat_age, 1) if heartbeat_age is not None else None,
        "next_due_iso": _next_expected_due.isoformat() if _next_expected_due else None,
    }



def execute_high_frequency_tasks():
    """
    Runs tasks that need frequent polling (every 60s):
    1. Scheduled Broadcasts & Ads Banners
    2. To-Do Hub heartbeats & auto-trash timers
    3. Offline Course Learning Reminders
    4. 15-Day Trash Purging
    """
    results = {}
    close_old_connections()

    # 1. Broadcasts
    try:
        call_command('run_scheduled_broadcasts')
        results['broadcasts'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [run_scheduled_broadcasts]: {e}", exc_info=True)
        results['broadcasts'] = f"error: {str(e)}"

    # 2. To-Do Hub & Learning Reminders
    try:
        call_command('process_todo')
        results['todo_and_learning'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [process_todo]: {e}", exc_info=True)
        results['todo_and_learning'] = f"error: {str(e)}"

    close_old_connections()
    return results


def execute_daily_tasks():
    """
    Runs daily maintenance tasks (once per day or on date change):
    1. 4-Stage Seat Hold Lifecycle & Auto-Promotions
    2. 5-Tier Fee Reminders (Email & WhatsApp)
    3. Visitor Inquiries & Preferred Seat Availability Waitlist
    4. Student & Alumni Birthday Wishes
    5. Read Notifications Cleanup (5d / 30d)
    6. Resolved Complaint Images Cleanup (5d)
    7. Old Broadcasts & Media Cleanup (20d+)
    8. Chat Media Purge (10d+)
    9. Deleted Group Chats Purge (5d+)
    10. Expired Broadcasts & 30d Complaint Proofs Purge
    """
    results = {}
    close_old_connections()

    # 1. Seat Hold Grace Period & Auto-Promotions
    try:
        call_command('process_seat_reminders')
        results['seat_holds'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [process_seat_reminders]: {e}", exc_info=True)
        results['seat_holds'] = f"error: {str(e)}"

    # 2. 5-Tier Fee Reminders
    try:
        call_command('send_fee_reminders')
        results['fee_reminders'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [send_fee_reminders]: {e}", exc_info=True)
        results['fee_reminders'] = f"error: {str(e)}"

    # 3. Visitor Leads & Seat Waitlists
    try:
        call_command('process_visitor_reminders')
        results['visitor_reminders'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [process_visitor_reminders]: {e}", exc_info=True)
        results['visitor_reminders'] = f"error: {str(e)}"

    # 4. Birthday Wishes
    try:
        from users.utils import process_birthday_wishes
        wishes_sent = process_birthday_wishes()
        results['birthday_wishes'] = f"ok (sent: {wishes_sent})"
    except Exception as e:
        logger.error(f"Scheduler Error [process_birthday_wishes]: {e}", exc_info=True)
        results['birthday_wishes'] = f"error: {str(e)}"

    # 5. Read Notifications Cleanup
    try:
        call_command('cleanup_notifications')
        results['cleanup_notifications'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [cleanup_notifications]: {e}", exc_info=True)
        results['cleanup_notifications'] = f"error: {str(e)}"

    # 6. Complaint Images Cleanup
    try:
        call_command('cleanup_complaint_images')
        results['cleanup_complaints'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [cleanup_complaint_images]: {e}", exc_info=True)
        results['cleanup_complaints'] = f"error: {str(e)}"

    # 7. Old Broadcasts Cleanup
    try:
        call_command('cleanup_broadcasts')
        results['cleanup_broadcasts'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [cleanup_broadcasts]: {e}", exc_info=True)
        results['cleanup_broadcasts'] = f"error: {str(e)}"

    # 8. Expired Chat Media Purge
    try:
        from users.views import purge_expired_media
        purge_expired_media()
        results['purge_chat_media'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [purge_expired_media]: {e}", exc_info=True)
        results['purge_chat_media'] = f"error: {str(e)}"

    # 9. Deleted Group Chats Purge
    try:
        from users.views import purge_expired_group_chats
        purge_expired_group_chats()
        results['purge_group_chats'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [purge_expired_group_chats]: {e}", exc_info=True)
        results['purge_group_chats'] = f"error: {str(e)}"

    # 10. Expired Broadcasts & 30d Complaint Proofs Purge
    try:
        from users.views import purge_expired_broadcasts_and_complaint_media
        purge_expired_broadcasts_and_complaint_media()
        results['purge_expired_broadcasts'] = 'ok'
    except Exception as e:
        logger.error(f"Scheduler Error [purge_expired_broadcasts_and_complaint_media]: {e}", exc_info=True)
        results['purge_expired_broadcasts'] = f"error: {str(e)}"

    close_old_connections()
    return results


def run_scheduler_cycle(force_daily=False, mode='all'):
    """
    Executes a complete scheduler cycle. Used by both the embedded daemon thread
    and the external HTTP webhook endpoint (/api/cron/maintenance/).
    
    `mode` options:
    - 'high_frequency': runs only high-frequency tasks (broadcasts, todos).
    - 'daily': runs only daily maintenance tasks.
    - 'all': runs high-frequency, plus daily tasks if due (or forced).
    """
    global last_scheduler_run, last_daily_run

    now = timezone.localtime(timezone.now())
    today_date = now.date()
    cycle_report = {
        "timestamp": now.isoformat(),
        "mode": mode,
        "high_frequency": None,
        "daily": None
    }

    if mode in ['high_frequency', 'all']:
        cycle_report["high_frequency"] = execute_high_frequency_tasks()

    should_run_daily = (mode == 'daily') or force_daily or (last_daily_run != today_date)
    if should_run_daily and mode in ['daily', 'all']:
        cycle_report["daily"] = execute_daily_tasks()
        last_daily_run = today_date

    last_scheduler_run = now
    return cycle_report


def execute_urgent_reminder_checks():
    """
    Ultra-low latency checker (ticks every 5s):
    Checks and fires due TodoTask reminders/alarms, offline course learning reminders,
    and due scheduled broadcasts/banners with near-zero latency (within 5 seconds of due time)
    instead of waiting for the periodic 60s background loop.
    """
    close_old_connections()
    try:
        from users.utils import process_todo_notifications, process_offline_learning_reminders
        # 1. Todo Hub alarms and reminders (atomic claiming)
        process_todo_notifications()

        # 2. Course learning reminders (atomic claiming)
        process_offline_learning_reminders()

        # 3. Scheduled Broadcasts & Ads Banners (if any due, trigger immediately)
        from users.models import BroadcastMessage
        if BroadcastMessage.objects.filter(status="scheduled", send_at__lte=timezone.now(), is_draft=False).exists():
            call_command('run_scheduled_broadcasts')
    except Exception as e:
        logger.error(f"Scheduler Error [execute_urgent_reminder_checks]: {e}", exc_info=True)
    finally:
        close_old_connections()


def calculate_seconds_to_next_due_task(now=None, max_sleep_seconds=900):
    """
    Scans upcoming time-sensitive tasks in PostgreSQL:
    1. BroadcastMessage (status='scheduled', is_draft=False, send_at)
    2. LearningReminder (recurrence_type='once', is_sent=False; plus recurring reminders today)
    3. TodoTask (category='REMINDER', is_done=False, is_trash=False)
    4. Daily maintenance (04:00 AM)

    Returns the minimum delay in seconds (between 0 and max_sleep_seconds)
    until the earliest task is due.
    If any task is due now or overdue, returns 0.
    """
    if now is None:
        now = timezone.localtime(timezone.now())

    candidates = []

    # 1. Scheduled Broadcasts
    try:
        from users.models import BroadcastMessage
        if BroadcastMessage.objects.filter(status="scheduled", is_draft=False, send_at__lte=now).exists():
            return 0
        earliest_broadcast = BroadcastMessage.objects.filter(
            status="scheduled", is_draft=False, send_at__gt=now
        ).order_by('send_at').values_list('send_at', flat=True).first()
        if earliest_broadcast:
            b_local = timezone.localtime(earliest_broadcast) if timezone.is_aware(earliest_broadcast) else earliest_broadcast
            candidates.append(('broadcast', b_local))
    except Exception as e:
        logger.debug(f"[ABCD Scheduler] Error checking broadcasts for sleep calculation: {e}")

    # 2. Learning Reminders
    try:
        from users.models import LearningReminder
        if LearningReminder.objects.filter(recurrence_type='once', is_sent=False, reminder_time__lte=now).exists():
            return 0
        earliest_once = LearningReminder.objects.filter(
            recurrence_type='once', is_sent=False, reminder_time__gt=now
        ).order_by('reminder_time').values_list('reminder_time', flat=True).first()
        if earliest_once:
            l_local = timezone.localtime(earliest_once) if timezone.is_aware(earliest_once) else earliest_once
            candidates.append(('learning_once', l_local))

        # Recurring daily/weekly reminders
        recurring_times = LearningReminder.objects.exclude(recurrence_type='once').filter(
            reminder_time_daily__gt=now.time()
        ).values_list('reminder_time_daily', flat=True)
        for t_time in recurring_times:
            target_dt = now.replace(hour=t_time.hour, minute=t_time.minute, second=t_time.second, microsecond=0)
            candidates.append(('learning_recurring', target_dt))
    except Exception as e:
        logger.debug(f"[ABCD Scheduler] Error checking learning reminders for sleep calculation: {e}")

    # 3. Todo Tasks (Reminders & Alarms)
    try:
        from users.models import TodoTask
        from users.utils import parse_flexible_datetime
        todo_tasks = TodoTask.objects.filter(category='REMINDER', is_done=False, is_trash=False)
        for task in todo_tasks:
            meta = task.metadata if isinstance(task.metadata, dict) else {}
            if meta.get('alarm_status') == 'stopped':
                continue
            recurrence = meta.get('recurrence', 'once')
            if recurrence == 'once':
                fire_dt = task.delete_at
                if not fire_dt and meta.get('fire_at'):
                    fire_dt = parse_flexible_datetime(meta.get('fire_at'))
                if fire_dt and not task.initial_notified:
                    f_local = timezone.localtime(fire_dt) if timezone.is_aware(fire_dt) else fire_dt
                    if f_local <= now:
                        return 0  # Task is due now or overdue!
                    candidates.append(('todo_once', f_local))
            else:
                time_str = meta.get('time_str')
                if time_str:
                    try:
                        hrs, mins = map(int, time_str.split(':'))
                        target_dt = now.replace(hour=hrs, minute=mins, second=0, microsecond=0)
                        if target_dt <= now and (task.last_notified_at is None or timezone.localtime(task.last_notified_at).date() < now.date()):
                            return 0  # Recurring reminder due now!
                        if target_dt > now:
                            candidates.append(('todo_recurring', target_dt))
                    except Exception:
                        pass
            # Snooze / Retry check
            next_retry_str = meta.get('next_retry_at')
            if next_retry_str:
                r_dt = parse_flexible_datetime(next_retry_str)
                if r_dt:
                    if r_dt <= now:
                        return 0
                    candidates.append(('todo_snooze', r_dt))
    except Exception as e:
        logger.debug(f"[ABCD Scheduler] Error checking todo tasks for sleep calculation: {e}")

    # 4. Daily Maintenance Target (04:00 AM)
    target_4am = now.replace(hour=4, minute=0, second=0, microsecond=0)
    if now < target_4am:
        candidates.append(('daily_maintenance', target_4am))
    else:
        candidates.append(('daily_maintenance', target_4am + timedelta(days=1)))

    if candidates:
        future_candidates = [c for c in candidates if c[1] > now]
        if future_candidates:
            kind, earliest_dt = min(future_candidates, key=lambda x: x[1])
            diff = (earliest_dt - now).total_seconds()
            if diff <= 0:
                return 0
            return min(max(1, diff), max_sleep_seconds)

    return max_sleep_seconds


def _scheduler_loop():
    """
    Adaptive event-driven background worker loop for ABCD Smart Campus.
    - Wakes at exact target seconds for due tasks.
    - Sleeps in RAM (threading.Event) when idle, allowing Neon to auto-suspend to 0 CU.
    - Immediately wakes up when notify_scheduler_task_changed() is triggered.
    - Performs an immediate catch-up sweep on startup or container restart.
    """
    global _last_heartbeat, _next_expected_due, last_daily_run
    logger.info(">>> ABCD Adaptive Background Scheduler Active <<<")

    # Initial gentle sleep to allow Daphne / Django boot and startup migrations
    time.sleep(5)

    # 1. Startup catch-up sweep: immediately check for any tasks that became due while restarting
    try:
        close_old_connections()
        execute_urgent_reminder_checks()
        now = timezone.localtime(timezone.now())
        today_date = now.date()
        if last_daily_run != today_date and now.hour >= 4:
            run_scheduler_cycle(force_daily=False, mode='daily')
            last_daily_run = today_date
    except Exception as e:
        logger.error(f"[ABCD Scheduler] Error during startup catch-up sweep: {e}", exc_info=True)
    finally:
        close_old_connections()

    while True:
        try:
            _wake_event.clear()
            now = timezone.localtime(timezone.now())
            _last_heartbeat = now

            # 2. Execute any due reminders/alarms & broadcasts
            execute_urgent_reminder_checks()

            # 3. Daily maintenance if date rolled over past 04:00 AM
            today_date = now.date()
            if last_daily_run != today_date and now.hour >= 4:
                run_scheduler_cycle(force_daily=False, mode='daily')
                last_daily_run = today_date

            # 4. Calculate exact seconds until next scheduled task
            delay = calculate_seconds_to_next_due_task(now=now, max_sleep_seconds=900)
            if delay > 0:
                _next_expected_due = now + timedelta(seconds=delay)
            else:
                _next_expected_due = now

            close_old_connections()

            # If a task is due immediately (delay == 0), loop right away
            if delay <= 0:
                time.sleep(0.5)
                continue

            # 5. Sleep in RAM until target time or until woken by task change event
            # Consumes ZERO CPU, ZERO DB queries. Neon can auto-suspend after 5 min.
            woken_early = _wake_event.wait(timeout=delay)
            if woken_early:
                logger.info("[ABCD Scheduler] Woken early by task change signal. Recalculating due time.")

        except Exception as e:
            logger.error(f"[ABCD Scheduler] Unexpected error in scheduler loop: {e}", exc_info=True)
            close_old_connections()
            time.sleep(15)
        finally:
            close_old_connections()



def start_background_scheduler():
    """
    Safely starts the embedded background scheduler daemon thread.
    Guaranteed to run only once per process.
    Skips execution during CLI management commands (e.g. migrate, collectstatic, test).

    IMPORTANT FOR SERVERLESS POSTGRES (NEON):
    On production when using Neon PostgreSQL (or when DISABLE_EMBEDDED_SCHEDULER=true),
    we do NOT run an aggressive continuous polling thread inside the web container.
    Continuous polling keeps Neon compute awake 24/7 (burning 180 CU-hrs/month).
    Instead, background automation is triggered cleanly via external cron-job.org
    pinging /api/cron/maintenance/?key=... every 4 hours, allowing Neon to auto-suspend
    to 0 CU (Sleep) whenever no human is browsing the site.
    """
    global _scheduler_started

    with _scheduler_lock:
        if _scheduler_started:
            return

        # 1. Skip if running CLI management commands
        cli_commands_to_skip = {
            'makemigrations', 'migrate', 'collectstatic', 'test',
            'createcachetable', 'init_production', 'createsuperuser',
            'check', 'shell', 'dbshell', 'flush', 'showmigrations',
            'cleanup_system', 'run_local_scheduler'
        }
        for arg in sys.argv:
            if any(cmd in arg for cmd in cli_commands_to_skip):
                return

        # 2. In runserver, ensure we only run in the child worker process (RUN_MAIN == 'true')
        # Django's runserver auto-reloader spawns a parent watcher and child worker.
        is_runserver = any('runserver' in arg for arg in sys.argv)
        if is_runserver and os.environ.get('RUN_MAIN') != 'true':
            return

        # 3. Allow embedded scheduler by default unless explicitly disabled
        disable_embedded = os.environ.get('DISABLE_EMBEDDED_SCHEDULER', '').lower() in ['1', 'true', 'yes']
        if disable_embedded:
            logger.info("[ABCD] Embedded background scheduler loop explicitly disabled via DISABLE_EMBEDDED_SCHEDULER. Scheduled automation runs via external cron.")
            return

        # 4. Mark started and spawn background daemon thread (for local dev or non-serverless setups)
        _scheduler_started = True
        thread = threading.Thread(target=_scheduler_loop, name="ABCD-BackgroundScheduler", daemon=True)
        thread.start()
        logger.info("[ABCD] Background Scheduler daemon thread successfully spawned.")
