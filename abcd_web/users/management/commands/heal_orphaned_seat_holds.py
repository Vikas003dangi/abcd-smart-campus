from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from users.models import Seat, SeatAssignment, StudentProfile


class Command(BaseCommand):
    help = (
        "Finds and repairs orphaned seat holds and status mismatches "
        "where seats are marked on_hold or occupied without a student, "
        "AND students marked on_hold without a valid seat hold."
    )

    def handle(self, *args, **options):
        today = timezone.localdate()
        healed_seats = 0
        healed_students = 0

        self.stdout.write(self.style.NOTICE(
            f"Scanning library seats for orphaned holds & status mismatches (Today: {today})..."
        ))

        seats = Seat.objects.all().prefetch_related('assignments')

        for seat in seats:
            active_assigns = [a for a in seat.assignments.all() if a.is_active]
            active_holds = [a for a in active_assigns if a.hold_status == 'active']

            has_assignment_hold = len(active_holds) > 0
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

            changed = False
            reasons = []

            # Case 1: Seat marked on_hold / hold fields set but nobody is holding it
            if (
                seat.status == 'on_hold' or
                seat.hold_status == 'active' or
                seat.hold_student_id or
                seat.hold_end_date
            ) and not has_assignment_hold and not has_valid_hold_student:
                seat.status = 'available'
                seat.hold_status = 'none'
                seat.hold_student = None
                seat.hold_start_date = None
                seat.hold_end_date = None
                changed = True
                reasons.append("Orphaned hold (no active hold student or assignment)")

            # Case 2: Seat marked occupied but has no active occupants
            elif seat.status == 'occupied' and not active_assigns:
                seat.recalc_status(save=False)
                changed = True
                reasons.append("Orphaned occupied status (no active assignments)")

            if changed:
                seat.save()
                healed_seats += 1
                self.stdout.write(self.style.SUCCESS(
                    f" [HEALED SEAT] Floor: {seat.floor} | Seat: {seat.seat_number} "
                    f"| New Status: {seat.status} | Reason: {', '.join(reasons)}"
                ))

        if healed_seats == 0:
            self.stdout.write(self.style.SUCCESS("All seats are healthy and consistent."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully healed {healed_seats} seat(s)."))

        # -----------------------------------------------------------------------
        # PHASE 2: Fix students stuck in 'on_hold' without a valid seat hold
        # A student is only legitimately on_hold if:
        #   - they have a physical seat (seat__isnull=False), OR
        #   - a Seat.hold_student points at them
        # -----------------------------------------------------------------------
        self.stdout.write(self.style.NOTICE("\nScanning for ghost on_hold students..."))

        seat_level_hold_ids = set(
            Seat.objects.filter(hold_student__isnull=False).values_list('hold_student_id', flat=True)
        )
        assignment_hold_ids = set(
            SeatAssignment.objects.filter(
                is_active=True, hold_status='active', is_partial=False
            ).values_list('student_id', flat=True)
        )

        ghost_students = StudentProfile.objects.filter(
            status='on_hold',
            seat__isnull=True,
        ).exclude(
            models.Q(service_type__in=['Coaching', 'Both']) |
            models.Q(service_type__iexact='coaching') |
            models.Q(service_type__iexact='both') |
            models.Q(batch__isnull=False) |
            models.Q(hold_start_date__isnull=False)
        ).exclude(
            id__in=seat_level_hold_ids
        ).exclude(
            id__in=assignment_hold_ids
        )

        for student in ghost_students:
            old_status = student.status
            student.status = 'admitted'
            student.save(update_fields=['status'])
            healed_students += 1
            self.stdout.write(self.style.SUCCESS(
                f" [HEALED STUDENT] ID: {student.id} | Name: {student.full_name} "
                f"| Email: {student.user.email if student.user else 'N/A'} "
                f"| '{old_status}' → 'admitted'"
            ))

        if healed_students == 0:
            self.stdout.write(self.style.SUCCESS("No ghost on_hold students found."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Successfully healed {healed_students} ghost student(s)."))

        # -----------------------------------------------------------------------
        # PHASE 3: Ensure Google Play Reviewer coaching hold student is correctly
        # linked, active on hold, and assigned to Grammar Batch 1
        # -----------------------------------------------------------------------
        try:
            gpr = StudentProfile.objects.filter(
                models.Q(full_name__icontains='Google Play') | models.Q(id=56)
            ).first()

            if not gpr:
                u52 = User.objects.filter(models.Q(id=52) | models.Q(username__icontains='google')).first()
                if u52:
                    gpr = StudentProfile.objects.filter(user=u52).first()

            if gpr:
                u52 = User.objects.filter(models.Q(id=52) | models.Q(username__icontains='google')).first()
                if u52 and gpr.user_id != u52.id:
                    gpr.user = u52

                gpr.status = 'on_hold'
                if not gpr.batch:
                    gpr.batch = 'Grammar Batch 1'
                if not gpr.service_type:
                    gpr.service_type = 'Coaching'
                today = timezone.localdate()
                if not gpr.hold_start_date:
                    gpr.hold_start_date = today
                if not gpr.hold_end_date or gpr.hold_end_date < today:
                    gpr.hold_end_date = today + timedelta(days=29)

                gpr.save()
                self.stdout.write(self.style.SUCCESS(
                    f" [COACHING HOLD SYNC] ID={gpr.id} | user_id={gpr.user_id} | Name={gpr.full_name} | status={gpr.status} | batch={gpr.batch} | hold={gpr.hold_start_date} to {gpr.hold_end_date}"
                ))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"Error in Phase 3 coaching hold sync: {e}"))
