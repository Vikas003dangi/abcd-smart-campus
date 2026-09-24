from django.db import migrations
from django.utils import timezone


def heal_orphaned_seat_holds(apps, schema_editor):
    Seat = apps.get_model('users', 'Seat')
    SeatAssignment = apps.get_model('users', 'SeatAssignment')
    today = timezone.localdate()

    for seat in Seat.objects.all():
        active_assigns = list(SeatAssignment.objects.filter(seat=seat, is_active=True))
        has_assignment_hold = any(a.hold_status == 'active' for a in active_assigns)

        has_valid_hold_student = False
        if seat.hold_student:
            student = seat.hold_student
            active_elsewhere = (
                SeatAssignment.objects.filter(student=student, is_active=True).exclude(seat=seat).exists() or
                (student.seat_id and student.seat_id != seat.id)
            )
            if (
                not active_elsewhere and
                student.seat_id == seat.id and
                student.status == 'on_hold' and
                seat.hold_end_date and
                seat.hold_end_date >= today
            ):
                has_valid_hold_student = True

        # Orphaned hold state
        if (seat.status == 'on_hold' or seat.hold_status == 'active' or seat.hold_student_id or seat.hold_end_date) and not has_assignment_hold and not has_valid_hold_student:
            seat.status = 'available'
            seat.hold_status = 'none'
            seat.hold_student = None
            seat.hold_start_date = None
            seat.hold_end_date = None
            seat.save(update_fields=['status', 'hold_status', 'hold_student', 'hold_start_date', 'hold_end_date'])

        # Orphaned occupied state with no active occupants
        elif seat.status == 'occupied' and not active_assigns:
            seat.status = 'available'
            seat.save(update_fields=['status'])


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0118_seatholdchangerequest'),
    ]

    operations = [
        migrations.RunPython(heal_orphaned_seat_holds, migrations.RunPython.noop),
    ]
