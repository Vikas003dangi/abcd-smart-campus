import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from users.models import Seat
from decouple import config

class Command(BaseCommand):
    help = 'Initialize production database with Vaku and Sandy superusers and initial seating configuration'

    def handle(self, *args, **options):
        # 1. Superuser 1: Vaku (Vikas Dangi)
        vaku_user = User.objects.filter(username__iexact='Vaku').first() or User.objects.filter(email__iexact='vd19055@gmail.com').first()
        vaku_pass = config('VAKU_PASSWORD', default='Vaku@2026Admin!')
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
            vaku_user.is_superuser = True
            vaku_user.is_staff = True
            vaku_user.first_name = 'Vikas'
            vaku_user.last_name = 'Dangi'
            vaku_user.save()
            self.stdout.write(self.style.SUCCESS('Updated Superuser: Vaku'))

        # 2. Superuser 2: Sandy (ABCD Coaching & Library)
        sandy_user = User.objects.filter(username__iexact='Sandy').first() or User.objects.filter(email__iexact='abcd2013baq@gmail.com').first()
        sandy_pass = config('SANDY_PASSWORD', default='Sandy@2026Admin!')
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
            sandy_user.is_superuser = True
            sandy_user.is_staff = True
            sandy_user.first_name = 'ABCD'
            sandy_user.last_name = 'Coaching & Library'
            sandy_user.save()
            self.stdout.write(self.style.SUCCESS('Updated Superuser: Sandy'))

        # 3. Initialize Seats (if none exist)
        total_seats = Seat.objects.count()
        if total_seats == 0:
            seats_to_create = []
            for i in range(1, 101):
                seats_to_create.append(Seat(
                    seat_number=f"S-{i:02d}",
                    status='available',
                    shift_type='full_day'
                ))
            Seat.objects.bulk_create(seats_to_create)
            self.stdout.write(self.style.SUCCESS('Initialized 100 Smart Library Seats (S-01 to S-100).'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Seats already present ({total_seats} seats).'))
