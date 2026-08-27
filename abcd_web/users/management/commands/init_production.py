import os
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from users.models import Seat
from decouple import config

class Command(BaseCommand):
    help = 'Initialize production database with superusers and initial seating configuration'

    def handle(self, *args, **options):
        # 1. Initialize Superusers
        admin_username = config('ADMIN_USERNAME', default='admin')
        admin_email = config('ADMIN_EMAIL', default='admin@abcd2013.online')
        admin_password = config('ADMIN_PASSWORD', default='Abcd@2026Admin!')

        teacher_username = config('TEACHER_USERNAME', default='teacher')
        teacher_email = config('TEACHER_EMAIL', default='teacher@abcd2013.online')
        teacher_password = config('TEACHER_PASSWORD', default='Teacher@2026!')

        # Create primary admin superuser if not exists
        if not User.objects.filter(username=admin_username).exists():
            admin_user = User.objects.create_superuser(
                username=admin_username,
                email=admin_email,
                password=admin_password
            )
            self.stdout.write(self.style.SUCCESS(f'Created Superuser: {admin_username}'))
        else:
            self.stdout.write(self.style.WARNING(f'Superuser {admin_username} already exists.'))

        # Create secondary teacher superuser/staff if not exists
        if not User.objects.filter(username=teacher_username).exists():
            teacher_user = User.objects.create_superuser(
                username=teacher_username,
                email=teacher_email,
                password=teacher_password
            )
            self.stdout.write(self.style.SUCCESS(f'Created Teacher Superuser: {teacher_username}'))
        else:
            self.stdout.write(self.style.WARNING(f'Teacher user {teacher_username} already exists.'))

        # 2. Initialize Seats (if none exist)
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
            self.stdout.write(self.style.SUCCESS(f'Initialized 100 Smart Library Seats (S-01 to S-100).'))
        else:
            self.stdout.write(self.style.SUCCESS(f'Seats already present ({total_seats} seats).'))
