from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import Seat, SeatAssignment


class Command(BaseCommand):
    help = "Finds and repairs orphaned seat holds and status mismatches where seats are marked on_hold or occupied without a student."

    def handle(self, *args, **options):
        today = timezone.localdate()
        healed_count = 0

        self.stdout.write(self.style.NOTICE(f"Scanning library seats for orphaned holds & status mismatches (Today: {today})..."))

        seats = Seat.objects.all().prefetch_related('assignments')

        for seat in seats:
            active_assigns = [a for a in seat.assignments.all() if a.is_active]
            active_holds = [a for a in active_assigns if a.hold_status == 'active']

            has_assignment_hold = len(active_holds) > 0
            has_valid_hold_student = bool(
                seat.hold_student and 
                seat.hold_student.status == 'on_hold' and 
                seat.hold_end_date and 
                seat.hold_end_date >= today
            )

            # If hold_student has an active assignment on another seat, this hold is orphaned/duplicate
            if seat.hold_student and SeatAssignment.objects.filter(student=seat.hold_student, is_active=True).exclude(seat=seat).exists():
                has_valid_hold_student = False

            changed = False
            reasons = []

            # Case 1: Seat marked on_hold or hold_status active, but nobody is holding it
            if (seat.status == 'on_hold' or seat.hold_status == 'active' or seat.hold_end_date) and not has_assignment_hold and not has_valid_hold_student:
                seat.status = 'available'
                seat.hold_status = 'none'
                seat.hold_student = None
                seat.hold_start_date = None
                seat.hold_end_date = None
                changed = True
                reasons.append("Orphaned hold (no active hold student or assignment)")

            # Case 2: Seat marked occupied, but has no active occupants
            elif seat.status == 'occupied' and not active_assigns:
                seat.recalc_status(save=False)
                changed = True
                reasons.append("Orphaned occupied status (no active assignments)")

            if changed:
                seat.save()
                healed_count += 1
                self.stdout.write(self.style.SUCCESS(
                    f" [HEALED] Floor: {seat.floor} | Seat: {seat.seat_number} | New Status: {seat.status} | Reason: {', '.join(reasons)}"
                ))

        if healed_count == 0:
            self.stdout.write(self.style.SUCCESS("All seats are healthy and consistent."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully healed {healed_count} seat(s)."))
