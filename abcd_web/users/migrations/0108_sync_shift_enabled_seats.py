from django.db import migrations

def set_shift_enabled_seats(apps, schema_editor):
    Seat = apps.get_model('users', 'Seat')
    # Seats 40 to 53 on Ground Floor are strictly shift-enabled
    shift_seat_numbers = [str(i) for i in range(40, 54)]
    
    Seat.objects.filter(floor='Ground Floor', seat_number__in=shift_seat_numbers).update(is_shift_enabled=True)
    Seat.objects.filter(floor='Ground Floor').exclude(seat_number__in=shift_seat_numbers).update(is_shift_enabled=False)
    Seat.objects.filter(floor='1st Floor').update(is_shift_enabled=False)

def revert_shift_enabled_seats(apps, schema_editor):
    pass

class Migration(migrations.Migration):

    dependencies = [
        ('users', '0107_groupchatsession_deleted_at_and_more'),
    ]

    operations = [
        migrations.RunPython(set_shift_enabled_seats, revert_shift_enabled_seats),
    ]
