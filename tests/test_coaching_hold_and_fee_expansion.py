"""
Self-check for Coaching Students On Hold & Fee Expiry Date Expansion.
Verifies that:
1. Coaching student can be saved with status='on_hold' without having a library seat.
2. Hold start date and end date are properly calculated and preserved.
3. _recalc_fee_expiry_with_hold properly extends coaching_fee_expiry_date by the hold duration.
4. sync_overall_fee_expiry_date synchronizes fee_expiry_date with the extended coaching expiry.
5. Returning to status='admitted' clears hold dates properly.
"""
import os
import sys
from datetime import timedelta, date

# Setup Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'abcd_web')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'abcd_web.settings')

import django
django.setup()

from django.contrib.auth.models import User
from django.utils import timezone
from users.models import StudentProfile
from users.views import _recalc_fee_expiry_with_hold, calculate_hold_extension_days, _parse_duration


def test_duration_parser():
    assert _parse_duration("15 days") == 15, "15 days parse failed"
    assert _parse_duration("1 month") == 30, "1 month parse failed"
    assert _parse_duration("2 months") == 60, "2 months parse failed"
    assert _parse_duration("10") == 10, "plain number 10 parse failed"
    print("[SUCCESS] Duration parser tests passed!")


def test_coaching_hold_and_fee_expiry():
    test_username = "test_coaching_hold_student_999"
    User.objects.filter(username=test_username).delete()

    user = User.objects.create(username=test_username, email="test_coach@example.com")
    today = timezone.localdate()
    initial_expiry = today + timedelta(days=20)

    try:
        # 1. Create admitted coaching student
        student = StudentProfile.objects.create(
            user=user,
            full_name="Coaching Hold Tester",
            service_type="Coaching",
            batch="Grammar Batch 1",
            status="admitted",
            is_admitted=True,
            coaching_fee_expiry_date=initial_expiry,
            fee_expiry_date=initial_expiry
        )
        assert student.seat_id is None, "Student must have no seat"
        assert student.status == "admitted"

        # 2. Put on hold without seat for 15 days
        hold_days = 15
        start_date = today
        end_date = start_date + timedelta(days=hold_days - 1)

        student.status = "on_hold"
        student.hold_start_date = start_date
        student.hold_end_date = end_date
        student.save()

        # Reload from DB and verify invariant DID NOT revert to 'admitted'
        reloaded = StudentProfile.objects.get(pk=student.pk)
        assert reloaded.status == "on_hold", f"Expected 'on_hold', got {reloaded.status}"
        assert reloaded.hold_start_date == start_date
        assert reloaded.hold_end_date == end_date
        print("[SUCCESS] Invariant check: Coaching student remains on_hold without library seat!")

        # 3. Verify hold extension days calculation
        calculated_days = calculate_hold_extension_days(reloaded)
        assert calculated_days == hold_days, f"Expected {hold_days} hold days, got {calculated_days}"

        # 4. Recalculate fee expiry with hold
        _recalc_fee_expiry_with_hold(reloaded)
        reloaded.refresh_from_db()

        expected_expiry = initial_expiry + timedelta(days=hold_days)
        assert reloaded.coaching_fee_expiry_date == expected_expiry, (
            f"Expected coaching fee expiry {expected_expiry}, got {reloaded.coaching_fee_expiry_date}"
        )
        assert reloaded.fee_expiry_date == expected_expiry, (
            f"Expected overall fee expiry {expected_expiry}, got {reloaded.fee_expiry_date}"
        )
        print(f"[SUCCESS] Fee expiry date successfully extended by {hold_days} days to {expected_expiry}!")

        # 5. Move student back to admitted
        reloaded.status = "admitted"
        reloaded.hold_start_date = None
        reloaded.hold_end_date = None
        reloaded.save()

        final_check = StudentProfile.objects.get(pk=student.pk)
        assert final_check.status == "admitted"
        assert final_check.hold_start_date is None
        print("[SUCCESS] Successfully returned coaching student to admitted status!")

    finally:
        User.objects.filter(username=test_username).delete()


if __name__ == '__main__':
    test_duration_parser()
    test_coaching_hold_and_fee_expiry()
    print("[ALL TESTS PASSED SUCCESSFULLY!]")
