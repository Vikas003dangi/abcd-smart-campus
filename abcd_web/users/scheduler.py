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
from datetime import datetime
from django.utils import timezone
from django.db import close_old_connections
from django.core.management import call_command

logger = logging.getLogger(__name__)

# Track thread state and execution timestamps
_scheduler_lock = threading.Lock()
_scheduler_started = False
last_scheduler_run = None
last_daily_run = None


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


def _scheduler_loop():
    """
    Background worker loop that runs continuously.
    Ticks every 60 seconds.
    """
    logger.info(">>> ABCD Embedded 24/7 Background Scheduler Active <<<")
    # Initial sleep of 10s to let Daphne / Django boot cleanly and complete startup migrations
    time.sleep(10)

    while True:
        try:
            run_scheduler_cycle(force_daily=False, mode='all')
        except Exception as e:
            logger.error(f"Unexpected error in background scheduler loop: {e}", exc_info=True)
        finally:
            close_old_connections()

        # Sleep for 60 seconds
        time.sleep(60)


def start_background_scheduler():
    """
    Safely starts the embedded background scheduler daemon thread.
    Guaranteed to run only once per process.
    Skips execution during CLI management commands (e.g. migrate, collectstatic, test).
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

        # 3. Mark started and spawn background daemon thread
        _scheduler_started = True
        thread = threading.Thread(target=_scheduler_loop, name="ABCD-BackgroundScheduler", daemon=True)
        thread.start()
        logger.info("[ABCD] Background Scheduler daemon thread successfully spawned.")
