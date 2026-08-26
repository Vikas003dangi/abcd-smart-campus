from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.db import transaction, connection
from users.models import (
    StudentProfile, StudentAchievement, SeatAssignment, SeatSpecialRequest, SeatHoldRequest, 
    Seat, Complaint, Payment, Notification, PushSubscription, 
    BroadcastMessage, VisitorIntent, Course, StudyMaterial, CourseCategory, TodoTask,
    Message, GroupMessage, ChatSession, DirectChatSession, GroupChatSession, GuidanceRequest,
    BlockedGuidance, RestrictedStudent
)

class Command(BaseCommand):
    help = 'Wipes all system data (Students, Assignments, Courses, Sessions, Todos) but KEEPS Superusers.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--noinput',
            action='store_true',
            help='Do not prompt for confirmation',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("WARNING: This will DELETE ALL DATA except Superusers."))

        if not options['noinput']:
            confirm = input("Are you sure you want to proceed? (yes/no): ")
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.ERROR("Operation cancelled."))
                return

        # Atomic transaction ensures if one thing fails, nothing gets deleted (safety)
        with transaction.atomic():
            self.stdout.write("Starting cleanup...")

            # 1. Clear Seat Data (Child records first)
            SeatAssignment.objects.all().delete()
            SeatSpecialRequest.objects.all().delete()
            SeatHoldRequest.objects.all().delete()
            self.stdout.write("Seat Assignments & Requests deleted.")

            # 2. Reset Seats (Do not delete physical seats, just empty them)
            Seat.objects.all().update(
                status='available', 
                hold_status='none',
                hold_student=None,
                hold_start_date=None,
                hold_end_date=None,
                hold_request_date=None,
                hold_request_duration=None,
                available_since=None
            )
            self.stdout.write("All Seats reset to 'Available'.")

            # 3. Clear Guidy Chat Data (Deep Clean Loop to trigger disk signals)
            self.stdout.write("Deleting Guidy chat messages individually to trigger file signals...")
            for msg in Message.objects.all():
                msg.delete()
            for gmsg in GroupMessage.objects.all():
                gmsg.delete()
            self.stdout.write("Guidy messages and physical files deleted.")

            # Bulk delete metadata
            ChatSession.objects.all().delete()
            DirectChatSession.objects.all().delete()
            GroupChatSession.objects.all().delete()
            GuidanceRequest.objects.all().delete()
            BlockedGuidance.objects.all().delete()
            RestrictedStudent.objects.all().delete()
            self.stdout.write("Guidy sessions, direct chats, groups, and metadata deleted.")

            # 4. Clear Student Data
            Complaint.objects.all().delete()
            Payment.objects.all().delete()
            Notification.objects.all().delete()
            PushSubscription.objects.all().delete()
            BroadcastMessage.objects.all().delete()
            VisitorIntent.objects.all().delete()
            TodoTask.objects.all().delete()
            self.stdout.write("Complaints, Payments, Notifications, Visitor Intents, Todo tasks deleted.")

            # 5. Clear Course Data
            StudyMaterial.objects.all().delete()
            Course.objects.all().delete()
            CourseCategory.objects.all().delete()
            self.stdout.write("Courses and Materials deleted.")

            # 6. Delete Students (Profiles and Achievements)
            StudentAchievement.objects.all().delete()
            StudentProfile.objects.all().delete()
            self.stdout.write("Student Profiles and Achievements deleted.")

            # 7. Delete User Accounts (EXCEPT Superusers)
            count = User.objects.filter(is_superuser=False).delete()[0]
            self.stdout.write(f"{count} Non-Superuser accounts deleted.")

            # 8. Clear all Session data (forces log out)
            Session.objects.all().delete()
            self.stdout.write("All active sessions cleared.")

            # 9. Reset Auto-Increment Sequences in SQLite
            tables_to_reset = [
                'users_studentprofile', 'users_studentachievement',
                'users_seatassignment', 'users_seatspecialrequest', 'users_seatholdrequest',
                'users_complaint', 'users_payment', 'users_notification',
                'users_pushsubscription', 'users_broadcastmessage', 'users_visitorintent',
                'users_course', 'users_studymaterial', 'users_coursecategory',
                'django_session', 'users_todotask',
                'users_message', 'users_groupmessage', 'users_chatsession',
                'users_directchatsession', 'users_groupchatsession', 'users_guidancerequest',
                'users_blockedguidance', 'users_restrictedstudent'
            ]
            with connection.cursor() as cursor:
                for table in tables_to_reset:
                    cursor.execute(f"DELETE FROM sqlite_sequence WHERE name = '{table}';")
            self.stdout.write("Database auto-increment sequences reset to 0.")

        self.stdout.write(self.style.SUCCESS("\nCLEANUP COMPLETE! System is ready for fresh start."))