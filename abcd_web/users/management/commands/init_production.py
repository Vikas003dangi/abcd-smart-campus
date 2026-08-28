import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from users.models import Seat
from decouple import config

class Command(BaseCommand):
    help = 'Initialize production database with Vaku and Sandy superusers and initial seating configuration'

    def handle(self, *args, **options):
        # 1. Superuser 1: Vaku (Vikas Dangi)
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
            self.stdout.write(self.style.SUCCESS('Updated Superuser: Vaku (password synced)'))

        # 2. Superuser 2: Sandy (ABCD Coaching & Library)
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
            self.stdout.write(self.style.SUCCESS('Updated Superuser: Sandy (password synced)'))

        # 3. Cleanup: Remove any other accidental superusers/staff
        legit_emails = ['vd19055@gmail.com', 'abcd2013baq@gmail.com']
        rogue_staff = User.objects.filter(is_staff=True).exclude(email__in=legit_emails)
        if rogue_staff.exists():
            for u in rogue_staff:
                u.is_staff = False
                u.is_superuser = False
                u.save()
                self.stdout.write(self.style.WARNING(f'Removed accidental staff status from: {u.username} ({u.email})'))

        # 4. Initialize Seats (if none exist)
        total_seats = Seat.objects.count()
        if total_seats == 0:
            ground_seats = [str(i) for i in range(1, 54)]
            first_seats = [str(i) for i in range(1, 54)]
            
            for s in ground_seats:
                Seat.objects.get_or_create(seat_number=s, floor='Ground Floor', defaults={'status': 'available'})
            for s in first_seats:
                Seat.objects.get_or_create(seat_number=s, floor='1st Floor', defaults={'status': 'available'})
            
            self.stdout.write(self.style.SUCCESS('Initialized Ground Floor & 1st Floor Smart Library Seats.'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Seats already present ({total_seats} seats).'))
