from django.core.management.base import BaseCommand
from users.utils import process_todo_notifications, purge_todo_trash, process_offline_learning_reminders

class Command(BaseCommand):
    help = 'Processes heartbeat notifications, offline learning reminders, and auto-deletion.'

    def handle(self, *args, **options):
        self.stdout.write("Starting To-Do Hub heartbeat process...")
        process_todo_notifications()
        
        self.stdout.write("Processing offline learning reminders...")
        process_offline_learning_reminders()

        self.stdout.write("Purging old trash (15+ days)...")
        purged = purge_todo_trash()
        
        self.stdout.write(self.style.SUCCESS(f"To-Do Hub processing complete. Purged {purged} items."))

