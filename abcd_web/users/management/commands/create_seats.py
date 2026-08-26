from django.core.management.base import BaseCommand
from users.models import Seat

# These are all the seat numbers from your hand-drawn layouts
GROUND_FLOOR_SEATS = [
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '10', 
    '11', '12', '13', '14', '15', '16', '17', '18', '19', '20', 
    '21', '22', '23', '24', '25', '26', '27', '28', '29', '30', 
    '31', '32', '33', '34', '35', '36', '37', '38', '39', '40', 
    '41', '42', '43', '44', '45', '46', '47', '48', '49', '50', 
    '51', '52', '53'
]

FIRST_FLOOR_SEATS = [
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '10',
    '11', '12', '13', '14', '15', '16', '17', '18', '19', '20',
    '21', '22', '23', '24', '25', '26', '27', '28', '29', '30',
    '31', '32', '33', '34', '35', '36', '37', '38', '39', '40',
    '41', '42', '43', '44', '45', '46', '47', '48', '49', '50',
    '51', '52', '53'
]


class Command(BaseCommand):
    help = 'Creates all library seats in the database based on the layouts.'

    def handle(self, *args, **options):
        ground_created_count = 0
        first_created_count = 0

        # Create Ground Floor seats
        for seat_num in GROUND_FLOOR_SEATS:
            seat, created = Seat.objects.get_or_create(
                seat_number=seat_num, 
                floor='Ground Floor'
            )
            if created:
                ground_created_count += 1

        # Create 1st Floor seats
        for seat_num in FIRST_FLOOR_SEATS:
            seat, created = Seat.objects.get_or_create(
                seat_number=seat_num, 
                floor='1st Floor'
            )
            if created:
                first_created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'Successfully created {ground_created_count} Ground Floor seats '
            f'and {first_created_count} 1st Floor seats.'
        ))
        self.stdout.write(self.style.WARNING(
            'If counts are 0, it means seats already existed (which is OK).'
        ))