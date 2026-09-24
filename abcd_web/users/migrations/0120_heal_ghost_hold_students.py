"""
Data migration: Reset orphaned on_hold student profiles that have no physical seat
and no seat-level hold pointer to 'admitted'.

This is the permanent cleanup complement to the heal_orphaned_seat_holds management
command and the new StudentProfile.save() invariant guard.
"""
from django.db import migrations


def heal_ghost_hold_students(apps, schema_editor):
    StudentProfile = apps.get_model('users', 'StudentProfile')
    Seat = apps.get_model('users', 'Seat')
    SeatAssignment = apps.get_model('users', 'SeatAssignment')

    seat_level_hold_ids = set(
        Seat.objects.filter(hold_student__isnull=False).values_list('hold_student_id', flat=True)
    )
    assignment_hold_ids = set(
        SeatAssignment.objects.filter(
            is_active=True,
            hold_status='active',
            is_partial=False,
        ).values_list('student_id', flat=True)
    )

    healed = StudentProfile.objects.filter(
        status='on_hold',
        seat__isnull=True,
    ).exclude(
        id__in=seat_level_hold_ids,
    ).exclude(
        id__in=assignment_hold_ids,
    ).update(status='admitted')

    if healed:
        print(f"  [0120] Healed {healed} ghost on_hold student(s) → admitted")


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0119_heal_orphaned_seat_holds'),
    ]

    operations = [
        migrations.RunPython(heal_ghost_hold_students, migrations.RunPython.noop),
    ]
