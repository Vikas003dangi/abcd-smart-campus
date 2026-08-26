import time
import sys
from django.core.management.base import BaseCommand
from django.core.management import call_command
from django.utils import timezone

class Command(BaseCommand):
    help = 'Runs local background automation scheduler (Broadcasts, Fee Reminders, Hold 3-Day Grace Period, To-Do Auto-Trash, Visitor Follow-ups).'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true', help='Run all background tasks once and exit.')
        parser.add_argument('--interval', type=int, default=60, help='Loop interval in seconds (default: 60s).')

    def handle(self, *args, **options):
        run_once = options['once']
        interval = options['interval']

        self.stdout.write(self.style.SUCCESS("=================================================="))
        self.stdout.write(self.style.SUCCESS(">>> ABCD Local Real-Time Background Scheduler Active"))
        self.stdout.write(self.style.SUCCESS("=================================================="))
        self.stdout.write(f"Interval: {interval}s | Run Once Mode: {run_once}")

        last_daily_run = None

        try:
            while True:
                now = timezone.localtime(timezone.now())
                today_date = now.date()
                self.stdout.write(f"\n[{now.strftime('%Y-%m-%d %H:%M:%S IST')}] Running high-frequency tasks...")

                # 1. High Frequency Tasks (Broadcasts, To-Do Auto-Trash, Learning Reminders)
                try:
                    call_command('run_scheduled_broadcasts')
                except Exception as e:
                    self.stderr.write(f"Error running broadcasts: {e}")

                try:
                    call_command('process_todo')
                except Exception as e:
                    self.stderr.write(f"Error processing to-do & learning reminders: {e}")

                # 2. Daily Tasks (Fee Reminders, Seat Hold Grace & Auto-Promotion, Visitor Expiry, Cleanup)
                if last_daily_run != today_date or run_once:
                    self.stdout.write(self.style.NOTICE(f"[{today_date}] Executing Daily Maintenance Tasks..."))

                    try:
                        self.stdout.write(" -> Checking Seat Hold Grace Periods & Auto-Promotions...")
                        call_command('process_seat_reminders')
                    except Exception as e:
                        self.stderr.write(f"Error processing seat reminders: {e}")

                    try:
                        self.stdout.write(" -> Dispatching Fee Expiry Reminders & Overdue Warnings...")
                        call_command('send_fee_reminders')
                    except Exception as e:
                        self.stderr.write(f"Error sending fee reminders: {e}")

                    try:
                        self.stdout.write(" -> Checking Visitor Intents & Seat Waitlists...")
                        call_command('process_visitor_reminders')
                    except Exception as e:
                        self.stderr.write(f"Error processing visitor reminders: {e}")

                    try:
                        self.stdout.write(" -> Checking Birthday Wishes for Students & Alumni...")
                        from users.utils import process_birthday_wishes
                        process_birthday_wishes()
                    except Exception as e:
                        self.stderr.write(f"Error processing birthday wishes: {e}")

                    try:
                        self.stdout.write(" -> Cleaning up read notifications...")
                        call_command('cleanup_notifications')
                    except Exception as e:
                        self.stderr.write(f"Error cleaning notifications: {e}")

                    try:
                        self.stdout.write(" -> Cleaning up resolved complaint images (5d+)...")
                        call_command('cleanup_complaint_images')
                    except Exception as e:
                        self.stderr.write(f"Error cleaning complaint images: {e}")

                    try:
                        self.stdout.write(" -> Cleaning up old broadcasts & media (20d+)...")
                        call_command('cleanup_broadcasts')
                    except Exception as e:
                        self.stderr.write(f"Error cleaning broadcasts: {e}")

                    try:
                        self.stdout.write(" -> Purging expired chat media (10d+)...")
                        from users.views import purge_expired_media
                        purge_expired_media()
                    except Exception as e:
                        self.stderr.write(f"Error purging expired chat media: {e}")

                    try:
                        self.stdout.write(" -> Purging expired deleted group chats (30d+)...")
                        from users.views import purge_expired_group_chats
                        purge_expired_group_chats()
                    except Exception as e:
                        self.stderr.write(f"Error purging expired group chats: {e}")


                    last_daily_run = today_date
                    self.stdout.write(self.style.SUCCESS("[Daily Maintenance Complete]"))

                if run_once:
                    self.stdout.write(self.style.SUCCESS("\n[Finished single-run execution]"))
                    break

                self.stdout.write(f"Waiting {interval} seconds for next tick... (Press Ctrl+C to stop)")
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("\n[Scheduler stopped by user (Ctrl+C). Exiting...]"))


