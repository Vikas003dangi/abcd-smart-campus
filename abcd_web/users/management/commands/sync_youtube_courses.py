from django.core.management.base import BaseCommand
from users.utils import sync_courses_from_youtube


class Command(BaseCommand):
    help = "Sync YouTube playlists into Course table"

    def handle(self, *args, **kwargs):
        self.stdout.write("🔄 Syncing YouTube courses...")
        sync_courses_from_youtube()
        self.stdout.write(self.style.SUCCESS("✅ Courses synced successfully."))
