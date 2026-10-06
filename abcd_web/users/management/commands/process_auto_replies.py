"""
users/management/commands/process_auto_replies.py
=================================================
Evaluates pending smart auto-replies in Guidy and posts responses whose due timer
has elapsed without manual owner reply.
"""

from django.core.management.base import BaseCommand
from users.auto_reply import process_due_auto_replies


class Command(BaseCommand):
    help = "Evaluates and sends due smart auto-replies for Guidy direct messaging."

    def handle(self, *args, **options):
        sent_count = process_due_auto_replies()
        self.stdout.write(
            self.style.SUCCESS(f"Successfully evaluated auto-replies. Sent: {sent_count}")
        )
