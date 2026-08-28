import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from decouple import config

class Command(BaseCommand):
    help = 'Clean and initialize production database to a brand new state with Vaku and Sandy superusers'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE('=== Starting Production Database Reset & Initialization ==='))

        legit_emails = ['vd19055@gmail.com', 'abcd2013baq@gmail.com']

        # 1. Clean up all non-admin users and their credentials
        deleted_users, _ = User.objects.exclude(email__in=legit_emails).exclude(username__in=['Vaku', 'Sandy']).delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {deleted_users} old/test user accounts.'))

        # 2. Clean all transactional & test history tables
        try:
            from users.models import (
                Notification, Complaint, StudentProfile, StudentAchievement,
                CourseQuestion, CourseAnswer, CourseReview, CourseShare,
                StudentMaterialAccess, StudentCourseInteraction, LearningReminder,
                PerformanceRecord, StudentScore, Payment, FeeTransaction,
                DismissedFeeAlert, VisitorIntent, BannerViewLog, PushSubscription,
                SeatAssignment, SeatSpecialRequest, SeatHoldRequest, SeatSwitchRequest,
                GuidanceRequest, ChatSession, DirectChatSession, Message,
                BlockedGuidance, RestrictedStudent, GroupChatSession, GroupMessage,
                TodoTask, GuidyBlock, Seat, TeacherProfile
            )

            Notification.objects.all().delete()
            Complaint.objects.all().delete()
            StudentProfile.objects.all().delete()
            StudentAchievement.objects.all().delete()
            
            CourseQuestion.objects.all().delete()
            CourseAnswer.objects.all().delete()
            CourseReview.objects.all().delete()
            CourseShare.objects.all().delete()
            StudentMaterialAccess.objects.all().delete()
            StudentCourseInteraction.objects.all().delete()
            LearningReminder.objects.all().delete()

            PerformanceRecord.objects.all().delete()
            StudentScore.objects.all().delete()
            Payment.objects.all().delete()
            FeeTransaction.objects.all().delete()
            DismissedFeeAlert.objects.all().delete()

            VisitorIntent.objects.all().delete()
            BannerViewLog.objects.all().delete()
            PushSubscription.objects.all().delete()

            SeatAssignment.objects.all().delete()
            SeatSpecialRequest.objects.all().delete()
            SeatHoldRequest.objects.all().delete()
            SeatSwitchRequest.objects.all().delete()

            GuidanceRequest.objects.all().delete()
            ChatSession.objects.all().delete()
            DirectChatSession.objects.all().delete()
            Message.objects.all().delete()
            BlockedGuidance.objects.all().delete()
            RestrictedStudent.objects.all().delete()
            GroupChatSession.objects.all().delete()
            GroupMessage.objects.all().delete()
            TodoTask.objects.all().delete()
            GuidyBlock.objects.all().delete()

            self.stdout.write(self.style.SUCCESS('Successfully cleaned all test notifications, admissions, complaints, chats, and requests.'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Warning during table purge: {e}'))

        # 3. Clean social auth entries for non-admin accounts
        try:
            from social_django.models import UserSocialAuth
            UserSocialAuth.objects.exclude(user__email__in=legit_emails).delete()
            self.stdout.write(self.style.SUCCESS('Purged non-admin Social Auth records.'))
        except Exception:
            pass

        # 4. Superuser 1: Vaku (Vikas Dangi)
        vaku_pass = config('VAKU_PASSWORD', default='VIK003@dan')
        vaku_user = User.objects.filter(email__iexact='vd19055@gmail.com').first()
        if not vaku_user:
            vaku_user = User.objects.filter(username__iexact='Vaku').first()

        if not vaku_user:
            vaku_user = User.objects.create_superuser(
                username='Vaku',
                email='vd19055@gmail.com',
                password=vaku_pass,
                first_name='Vikas',
                last_name='Dangi'
            )
            self.stdout.write(self.style.SUCCESS('Created Superuser: Vaku (vd19055@gmail.com)'))
        else:
            vaku_user.username = 'Vaku'
            vaku_user.email = 'vd19055@gmail.com'
            vaku_user.is_superuser = True
            vaku_user.is_staff = True
            vaku_user.first_name = 'Vikas'
            vaku_user.last_name = 'Dangi'
            vaku_user.set_password(vaku_pass)
            vaku_user.save()
            self.stdout.write(self.style.SUCCESS('Updated Superuser: Vaku (password & credentials synced)'))

        # 5. Superuser 2: Sandy (ABCD Coaching & Library)
        sandy_pass = config('SANDY_PASSWORD', default='Sandeepanandajimaharaj')
        sandy_user = User.objects.filter(email__iexact='abcd2013baq@gmail.com').first()
        if not sandy_user:
            sandy_user = User.objects.filter(username__iexact='Sandy').first()

        if not sandy_user:
            sandy_user = User.objects.create_superuser(
                username='Sandy',
                email='abcd2013baq@gmail.com',
                password=sandy_pass,
                first_name='ABCD',
                last_name='Coaching & Library'
            )
            self.stdout.write(self.style.SUCCESS('Created Superuser: Sandy (abcd2013baq@gmail.com)'))
        else:
            sandy_user.username = 'Sandy'
            sandy_user.email = 'abcd2013baq@gmail.com'
            sandy_user.is_superuser = True
            sandy_user.is_staff = True
            sandy_user.first_name = 'ABCD'
            sandy_user.last_name = 'Coaching & Library'
            sandy_user.set_password(sandy_pass)
            sandy_user.save()
            self.stdout.write(self.style.SUCCESS('Updated Superuser: Sandy (password & credentials synced)'))

        # 6. Ensure TeacherProfiles are set up for both superusers
        try:
            from users.models import TeacherProfile
            sandy_tp, _ = TeacherProfile.objects.get_or_create(user=sandy_user)
            sandy_tp.display_name = 'Sandeep Sir'
            sandy_tp.role_title = 'Teacher'
            sandy_tp.detail1 = 'Founder & Head Faculty'
            sandy_tp.detail2 = 'English Grammar & Spoken Teacher'
            sandy_tp.detail3 = 'Library Owner'
            sandy_tp.about = 'Sandeep Sir is known for his clear explanations, disciplined teaching style and friendly nature. Since 2013, hundreds of students from Basoda and nearby areas have improved their grammar, written English and confidence with his guidance.'
            sandy_tp.save()

            vaku_tp, _ = TeacherProfile.objects.get_or_create(user=vaku_user)
            vaku_tp.display_name = 'ABCD Asst.'
            vaku_tp.role_title = 'Vikas Dangi'
            vaku_tp.detail1 = 'Software Engg.'
            vaku_tp.detail2 = 'Tech Support / helpline of ABCD'
            vaku_tp.detail3 = 'Support Helpline'
            vaku_tp.about = 'Technical support and helpline assistant for ABCD. Contact for software, platform, or account issues.'
            vaku_tp.save()
            self.stdout.write(self.style.SUCCESS('Teacher profiles verified for Sandy & Vaku.'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Teacher profile init error: {e}'))

        # 7. Initialize/Reset all Library Seats to clean 'available' state
        try:
            from users.models import Seat
            # Reset existing seats to available
            Seat.objects.all().update(status='available')

            total_seats = Seat.objects.count()
            if total_seats == 0:
                ground_seats = [str(i) for i in range(1, 54)]
                first_seats = [str(i) for i in range(1, 54)]
                
                for s in ground_seats:
                    Seat.objects.get_or_create(seat_number=s, floor='Ground Floor', defaults={'status': 'available'})
                for s in first_seats:
                    Seat.objects.get_or_create(seat_number=s, floor='1st Floor', defaults={'status': 'available'})
                
                self.stdout.write(self.style.SUCCESS('Created and initialized all Ground Floor & 1st Floor Seats.'))
            else:
                self.stdout.write(self.style.SUCCESS(f'All {total_seats} seats have been reset to Available.'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Seat reset error: {e}'))

        self.stdout.write(self.style.SUCCESS('=== Production Database Clean Reset Complete! Site is fresh & ready. ==='))
