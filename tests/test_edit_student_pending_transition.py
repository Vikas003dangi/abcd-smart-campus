import os
import sys

# Setup Django environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'abcd_web')))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'abcd_web.settings')

import django
django.setup()

from django.test import RequestFactory
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.messages.storage.fallback import FallbackStorage
from users.models import StudentProfile, Seat, SeatAssignment
from users.views import edit_student_view, teacher_dashboard_view
from django.db import transaction
from unittest.mock import patch
import django.shortcuts


@patch('users.email_service.send_html_email')
@patch('users.views.send_html_email')
@patch('users.notifications.send_admission_approval_notifications')
def run_checks(mock_notif, mock_views_email, mock_email_service):
    factory = RequestFactory()
    captured_context = {}
    original_render = django.shortcuts.render

    def fake_render(request, template, context=None, *args, **kwargs):
        if context:
            captured_context.update(context)
        return original_render(request, template, context, *args, **kwargs)

    with patch('users.views.render', side_effect=fake_render), transaction.atomic():
        # Setup teacher staff user
        teacher_user, _ = User.objects.get_or_create(username='test_teacher_staff', defaults={'is_staff': True})
        teacher_user.is_staff = True
        teacher_user.save()

        # -------------------------------------------------------------------------
        # Case 1: Coaching student (NO SEAT) transitioning from admitted to pending
        # -------------------------------------------------------------------------
        coaching_user, _ = User.objects.get_or_create(username='coaching_test_student', defaults={'email': 'coach@test.com'})
        coaching_student, _ = StudentProfile.objects.get_or_create(
            user=coaching_user,
            defaults={
                'full_name': 'Coaching Test Student',
                'service_type': 'Coaching',
                'batch': 'Grammar Batch 1',
                'status': 'admitted',
                'is_admitted': True,
                'mobile_number': '9876543210',
                'whatsapp_number': '9876543210',
                'sex': 'Male',
                'admission_type': 'new',
            }
        )
        coaching_student.seat = None
        coaching_student.status = 'admitted'
        coaching_student.is_admitted = True
        coaching_student.batch = 'Grammar Batch 1'
        coaching_student.save()

        # Send POST request to edit_student_view changing status to pending
        post_data = {
            'full_name': 'Coaching Test Student',
            'sex': 'Male',
            'status': 'pending',
            'service_type': 'Coaching',
            'batch': 'Grammar Batch 1',
            'mobile_number': '9876543210',
            'whatsapp_number': '9876543210',
            'email': 'coach@test.com',
        }
        req = factory.post(f'/edit-student/{coaching_student.id}/', post_data)
        req.user = teacher_user
        setattr(req, 'session', {})
        setattr(req, '_messages', FallbackStorage(req))

        response = edit_student_view(req, student_id=coaching_student.id)
        assert response.status_code == 302, f"Expected 302 redirect, got {response.status_code}"

        coaching_student.refresh_from_db()
        assert coaching_student.status == 'pending', f"Expected status 'pending', got {coaching_student.status}"
        assert coaching_student.is_admitted is False, f"Expected is_admitted False, got {coaching_student.is_admitted}"
        assert coaching_student.is_manual_pending is False, f"Expected is_manual_pending False, got {coaching_student.is_manual_pending}"
        assert coaching_student.batch == 'Grammar Batch 1', f"Expected batch preserved, got {coaching_student.batch}"
        assert coaching_student.seat is None, "Expected seat to remain None"

        # -------------------------------------------------------------------------
        # Case 2: Library student (WITH SEAT) transitioning from on_hold to pending
        # -------------------------------------------------------------------------
        library_user, _ = User.objects.get_or_create(username='library_test_student', defaults={'email': 'lib@test.com'})
        seat, _ = Seat.objects.get_or_create(
            seat_number='99',
            floor='First Floor',
            defaults={'status': 'available', 'is_shift_enabled': False}
        )
        lib_student, _ = StudentProfile.objects.get_or_create(
            user=library_user,
            defaults={
                'full_name': 'Library Test Student',
                'service_type': 'Library',
                'status': 'on_hold',
                'is_admitted': True,
                'mobile_number': '9876543211',
                'whatsapp_number': '9876543211',
                'sex': 'Female',
                'admission_type': 'new',
                'seat': seat,
                'shift': 'full'
            }
        )
        lib_student.status = 'on_hold'
        lib_student.seat = seat
        lib_student.is_admitted = True
        lib_student.save()

        # Create active hold assignment
        assignment, _ = SeatAssignment.objects.get_or_create(
            student=lib_student,
            seat=seat,
            defaults={'is_active': True, 'hold_status': 'active', 'shift_type': 'full'}
        )
        assignment.is_active = True
        assignment.hold_status = 'active'
        assignment.save()

        seat.hold_student = lib_student
        seat.status = 'on_hold'
        seat.save()

        # Send POST request to change status to pending
        post_data_lib = {
            'full_name': 'Library Test Student',
            'sex': 'Female',
            'status': 'pending',
            'service_type': 'Library',
            'batch': '',
            'mobile_number': '9876543211',
            'whatsapp_number': '9876543211',
            'email': 'lib@test.com',
        }
        req_lib = factory.post(f'/edit-student/{lib_student.id}/', post_data_lib)
        req_lib.user = teacher_user
        setattr(req_lib, 'session', {})
        setattr(req_lib, '_messages', FallbackStorage(req_lib))

        resp_lib = edit_student_view(req_lib, student_id=lib_student.id)
        assert resp_lib.status_code == 302, f"Expected 302 redirect, got {resp_lib.status_code}"

        lib_student.refresh_from_db()
        assert lib_student.status == 'pending', f"Expected status 'pending', got {lib_student.status}"
        assert lib_student.is_admitted is False, f"Expected is_admitted False, got {lib_student.is_admitted}"
        assert lib_student.is_manual_pending is False, f"Expected is_manual_pending False, got {lib_student.is_manual_pending}"
        assert lib_student.seat_id == seat.id, "Expected seat request to be preserved on student profile"

        # Check assignment state
        active_assigns = SeatAssignment.objects.filter(student=lib_student, is_active=True).count()
        assert active_assigns == 0, f"Expected 0 active assignments, got {active_assigns}"

        inactive_assign = SeatAssignment.objects.filter(student=lib_student, seat=seat, is_active=False).first()
        assert inactive_assign is not None, "Expected inactive assignment to exist for seat request"

        seat.refresh_from_db()
        assert seat.hold_student is None, "Expected seat.hold_student to be cleared"

        # -------------------------------------------------------------------------
        # Case 3: Verify teacher_dashboard context and counts
        # -------------------------------------------------------------------------
        req_dash = factory.get('/dashboard/')
        req_dash.user = teacher_user
        setattr(req_dash, 'session', {})
        setattr(req_dash, '_messages', FallbackStorage(req_dash))

        resp_dash = teacher_dashboard_view(req_dash)
        assert resp_dash.status_code == 200, f"Expected 200, got {resp_dash.status_code}"
        ctx = captured_context

        # Check pending requests lists
        pending_ids = [s.id for s in ctx['pending_students']]
        assert coaching_student.id in pending_ids, "Coaching pending student should be in pending_students"
        assert lib_student.id in pending_ids, "Library pending student should be in pending_students"

        # Coaching requests
        coaching_req_ids = [s.id for s in ctx['pending_new_coaching_students']]
        assert coaching_student.id in coaching_req_ids, "Coaching student should be in pending_new_coaching_students"

        # Library requests
        library_req_ids = [s.id for s in ctx['pending_new_library_students']]
        assert lib_student.id in library_req_ids, "Library student should be in pending_new_library_students"

        # Check that neither student is in the admitted/enrolled lists
        admitted_ids = [s.id for s in ctx['admitted_students']]
        assert coaching_student.id not in admitted_ids, "Pending student must NOT be in admitted_students"
        assert lib_student.id not in admitted_ids, "Pending student must NOT be in admitted_students"

        all_coaching_batch_student_ids = [s.id for batch_list in ctx['coaching_students_by_batch'].values() for s in batch_list]
        assert coaching_student.id not in all_coaching_batch_student_ids, "Pending student must NOT be in coaching batches"

        all_library_floor_student_ids = [s.id for floor_list in ctx['library_students_by_floor'].values() for s in floor_list]
        assert lib_student.id not in all_library_floor_student_ids, "Pending student must NOT be in library floors"

        # Rollback so DB is completely clean
        transaction.set_rollback(True)

    print("[SUCCESS] All checks for student pending transition passed without error!")


if __name__ == '__main__':
    run_checks()
