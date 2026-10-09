from datetime import date, timedelta
from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from users.models import Seat, StudentProfile, SeatAssignment
from users.utils.floor_export import get_floor_export_data


class PendingSeatStatusTestCase(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(username='pending_student', password='password123', first_name='Pending')
        self.seat_g38 = Seat.objects.create(seat_number='G-38', floor='Ground Floor', status='available')
        self.seat_g39 = Seat.objects.create(seat_number='G-39', floor='Ground Floor', status='available')
        
        # Pending student profile requesting G-38
        self.profile = StudentProfile.objects.create(
            user=self.user,
            full_name='Pending Student',
            status='pending',
            is_admitted=False,
            seat=self.seat_g38,
            service_type='Library',
            shift='full'
        )

    def test_your_seat_status_view_pending_context(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('users:your_seat_status'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_admission_pending'])
        self.assertFalse(response.context['has_occupied_seat'])
        content = response.content.decode('utf-8')
        self.assertIn('Requested Seat:', content)
        self.assertIn('Pending Approval', content)
        self.assertIn('Seat Request Under Review', content)
        # Action buttons like put seat on hold should NOT be present
        self.assertNotIn('Put the seat on Hold', content)

    def test_get_seat_status_api_pending_student(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('users:api_get_seat_status') + '?floor=Ground Floor')
        self.assertEqual(response.status_code, 200)
        import json
        data = json.loads(response.content.decode('utf-8'))
        seats = {s['seat_number']: s for s in data['seats']}
        g38_info = seats.get('G-38')
        self.assertIsNotNone(g38_info)
        self.assertTrue(g38_info.get('is_my_requested_seat'))
        self.assertNotEqual(g38_info.get('status'), 'occupied')

    def test_action_apis_blocked_for_pending_student(self):
        self.client.force_login(self.user)

        # 1. Hold API
        resp_hold = self.client.post(reverse('users:api_request_seat_hold'), {
            'start_date': str(date.today() + timedelta(days=5)),
            'duration': '30 days'
        })
        self.assertEqual(resp_hold.status_code, 403)

        # 2. Switch API
        resp_switch = self.client.post(reverse('users:api_request_seat_switch'), {
            'target_seat': 'G-39',
            'target_floor': 'Ground Floor',
            'target_shift': 'full'
        })
        self.assertEqual(resp_switch.status_code, 403)

        # 3. Leave API
        resp_leave = self.client.post(reverse('users:api_request_seat_leave'))
        self.assertEqual(resp_leave.status_code, 403)

    def test_floor_export_counts_pending_and_locked_as_available(self):
        # Clear existing seats for a clean test
        Seat.objects.all().delete()
        # Create 53 seats: 3 occupied, 1 pending, 49 available
        occupied_user_1 = User.objects.create_user(username='occ1', password='pw')
        prof_occ1 = StudentProfile.objects.create(user=occupied_user_1, full_name='Occ 1', status='admitted', is_admitted=True)
        occupied_user_2 = User.objects.create_user(username='occ2', password='pw')
        prof_occ2 = StudentProfile.objects.create(user=occupied_user_2, full_name='Occ 2', status='admitted', is_admitted=True)
        occupied_user_3 = User.objects.create_user(username='occ3', password='pw')
        prof_occ3 = StudentProfile.objects.create(user=occupied_user_3, full_name='Occ 3', status='admitted', is_admitted=True)

        for i in range(1, 54):
            seat_num = f'G-{i}'
            if i <= 3:
                s = Seat.objects.create(seat_number=seat_num, floor='Ground Floor', status='occupied')
                prof = [prof_occ1, prof_occ2, prof_occ3][i - 1]
                prof.seat = s
                prof.save()
                SeatAssignment.objects.create(seat=s, student=prof, is_active=True, shift_type='full')
            elif i == 4:
                # 1 pending seat
                s = Seat.objects.create(seat_number=seat_num, floor='Ground Floor', status='pending')
            else:
                s = Seat.objects.create(seat_number=seat_num, floor='Ground Floor', status='available')

        export_data = get_floor_export_data('Ground Floor')
        counts = export_data['counts']
        self.assertEqual(counts['total'], 53)
        self.assertEqual(counts['occupied'], 3)
        self.assertEqual(counts['pending'], 1)
        self.assertEqual(counts['available'], 50)
