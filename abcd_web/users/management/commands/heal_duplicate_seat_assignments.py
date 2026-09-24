"""
heal_duplicate_seat_assignments
================================
Detects and repairs the corruption where a student ends up with more than one
active SeatAssignment simultaneously (e.g. owner-on-hold on Seat A AND temp
tenant on Seat B).

Root-cause that was patched:  assign_full_day_temp and approve_partial_request
in seat_action_api did not check whether the chosen student already had an
active assignment on a different seat.

Run with:
    python manage.py heal_duplicate_seat_assignments
    python manage.py heal_duplicate_seat_assignments --dry-run
"""

from django.core.management.base import BaseCommand
from django.db.models import Count
from users.models import Seat, SeatAssignment


class Command(BaseCommand):
    help = "Detect and repair students who appear on more than one seat simultaneously."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report problems without making any changes.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        mode = "[DRY RUN] " if dry_run else ""
        fixed = 0
        problems = 0

        self.stdout.write(self.style.NOTICE(
            f"{mode}Scanning for students with multiple active SeatAssignments..."
        ))

        dupes = (
            SeatAssignment.objects
            .filter(is_active=True)
            .values("student", "student__full_name")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )

        for row in dupes:
            student_id = row["student"]
            name = row["student__full_name"]
            problems += 1

            assigns = (
                SeatAssignment.objects
                .filter(student_id=student_id, is_active=True)
                .select_related("seat", "student")
                .order_by("is_partial", "created_at")
            )

            self.stdout.write(self.style.WARNING(
                f"\n  PROBLEM: {name} has {assigns.count()} active assignments:"
            ))
            for a in assigns:
                role = "temp" if a.is_partial else "owner"
                self.stdout.write(
                    f"    [{role}] Seat {a.seat.seat_number} ({a.seat.floor}) "
                    f"shift={a.shift_type} hold={a.hold_status} created={a.created_at.date()}"
                )

            if dry_run:
                continue

            assigns_list = list(assigns)
            owner_assigns = [a for a in assigns_list if not a.is_partial]
            keeper = owner_assigns[0] if owner_assigns else assigns_list[0]

            for a in assigns_list:
                if a.pk == keeper.pk:
                    continue
                self.stdout.write(self.style.SUCCESS(
                    f"    -> Deactivating stale assignment on Seat {a.seat.seat_number} ({a.seat.floor})"
                ))
                a.is_active = False
                a.save(update_fields=["is_active"])
                a.seat.recalc_status(save=True)

            keeper.student.seat = keeper.seat
            keeper.student.shift = keeper.shift_type
            keeper.student.status = "on_hold" if keeper.hold_status == "active" else "admitted"
            keeper.student.save(update_fields=["seat", "shift", "status"])
            fixed += 1
            self.stdout.write(self.style.SUCCESS(
                f"    -> Kept: Seat {keeper.seat.seat_number} ({keeper.seat.floor}) | Profile updated."
            ))

        self.stdout.write(self.style.NOTICE(
            f"\n{mode}Checking for stale Seat.hold_student pointers..."
        ))
        stale_hold_seats = 0
        for seat in Seat.objects.filter(hold_student__isnull=False).select_related("hold_student"):
            sp = seat.hold_student
            has_active_hold = SeatAssignment.objects.filter(
                seat=seat, student=sp, is_active=True, hold_status="active"
            ).exists()
            if not has_active_hold:
                stale_hold_seats += 1
                self.stdout.write(self.style.WARNING(
                    f"  STALE: Seat {seat.seat_number} ({seat.floor}) "
                    f"hold_student={sp.full_name} but no active hold assignment."
                ))
                if not dry_run:
                    seat.hold_student = None
                    seat.hold_start_date = None
                    seat.hold_end_date = None
                    seat.hold_status = "none"
                    seat.recalc_status(save=False)
                    seat.save()
                    self.stdout.write(self.style.SUCCESS(
                        f"    -> Cleared stale hold pointer on Seat {seat.seat_number}."
                    ))

        self.stdout.write("")
        if dry_run:
            self.stdout.write(self.style.WARNING(
                f"DRY RUN: {problems} multi-seat student(s) found, "
                f"{stale_hold_seats} stale hold pointer(s). Run without --dry-run to fix."
            ))
        else:
            if problems == 0 and stale_hold_seats == 0:
                self.stdout.write(self.style.SUCCESS("All seat assignments are healthy."))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"Fixed {fixed} multi-seat student(s), {stale_hold_seats} stale pointer(s) cleared."
                ))
