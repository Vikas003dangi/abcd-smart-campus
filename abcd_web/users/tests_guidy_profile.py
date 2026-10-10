from django.test import TestCase
from django.contrib.auth import get_user_model
from django.urls import reverse
from users.models import StudentProfile, StudentAchievement

User = get_user_model()

class GuidyProfileInfoTests(TestCase):
    def setUp(self):
        # User A has id 1 (or whatever PK)
        self.user_a = User.objects.create_user(username='usera', first_name='Vikas', last_name='Dangi', password='password123')
        # User B
        self.user_b = User.objects.create_user(username='userb', first_name='Raj', last_name='Pandey', password='password123')

        # Give User B a student profile with a specific PK
        self.prof_b = StudentProfile.objects.create(
            user=self.user_b,
            full_name='Raj Pandey',
            service_type='Coaching',
            batch='Spoken English 1'
        )

        # Give User A a student profile
        self.prof_a = StudentProfile.objects.create(
            user=self.user_a,
            full_name='Vikas Dangi',
            service_type='Library'
        )

    def test_student_profile_looked_up_by_user_id_consistently(self):
        self.client.login(username='usera', password='password123')
        url = reverse('users:guidy_profile_info', kwargs={'entity_type': 'student', 'entity_id': self.user_a.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['name'], 'Vikas Dangi')
        self.assertEqual(data['role'], 'Library')

    def test_student_profile_other_user_not_colliding(self):
        self.client.login(username='usera', password='password123')
        url = reverse('users:guidy_profile_info', kwargs={'entity_type': 'student', 'entity_id': self.user_b.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['name'], 'Raj Pandey')
        self.assertEqual(data['role'], 'Coaching')
