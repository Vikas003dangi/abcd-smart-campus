from django.test import SimpleTestCase, TestCase
from django.template import Template, Context
from django.contrib.auth.models import User
from users.templatetags.dict_extras import possessive, gender_avatar
from users.models import StudentProfile, StudentAchievement


class DictExtrasAvatarAndPossessiveTests(SimpleTestCase):
    def test_possessive_filter_regular_names(self):
        self.assertEqual(possessive("Suhani Singh"), "Suhani Singh's")
        self.assertEqual(possessive("Aman"), "Aman's")
        self.assertEqual(possessive("Riya"), "Riya's")

    def test_possessive_filter_ends_with_s(self):
        self.assertEqual(possessive("Vikas"), "Vikas'")
        self.assertEqual(possessive("Thomas"), "Thomas'")
        self.assertEqual(possessive("JAMES"), "JAMES'")
        self.assertEqual(possessive("James"), "James'")

    def test_possessive_filter_empty_or_none(self):
        self.assertEqual(possessive(""), "")
        self.assertEqual(possessive(None), "")
        self.assertEqual(possessive("   "), "")

    def test_gender_avatar_filter_strings(self):
        self.assertEqual(gender_avatar("Female"), "/static/data/default_avatar_female.png")
        self.assertEqual(gender_avatar("female"), "/static/data/default_avatar_female.png")
        self.assertEqual(gender_avatar("F"), "/static/data/default_avatar_female.png")
        self.assertEqual(gender_avatar("Male"), "/static/data/default_avatar_male.png")
        self.assertEqual(gender_avatar("male"), "/static/data/default_avatar_male.png")
        self.assertEqual(gender_avatar("M"), "/static/data/default_avatar_male.png")
        self.assertEqual(gender_avatar("Other"), "/static/data/default_avatar.png")
        self.assertEqual(gender_avatar(""), "/static/data/default_avatar.png")
        self.assertEqual(gender_avatar(None), "/static/data/default_avatar.png")

    def test_gender_avatar_filter_objects(self):
        class ObjWithSex:
            def __init__(self, sex):
                self.sex = sex

        class ObjWithGender:
            def __init__(self, gender):
                self.gender = gender

        self.assertEqual(gender_avatar(ObjWithSex("Female")), "/static/data/default_avatar_female.png")
        self.assertEqual(gender_avatar(ObjWithSex("Male")), "/static/data/default_avatar_male.png")
        self.assertEqual(gender_avatar(ObjWithSex(None)), "/static/data/default_avatar.png")
        self.assertEqual(gender_avatar(ObjWithGender("Female")), "/static/data/default_avatar_female.png")
        self.assertEqual(gender_avatar(ObjWithGender("Male")), "/static/data/default_avatar_male.png")
        self.assertEqual(gender_avatar(ObjWithGender("Other")), "/static/data/default_avatar.png")


class FeeCalendarHeaderTemplateTests(TestCase):
    def test_fee_calendar_header_renders_avatar_and_possessive(self):
        template_str = """
        {% load dict_extras %}
        <div class="header">
            <div class="header-title-row">
                <img src="{{ student.photo_url }}" alt="{{ student.full_name }}" class="header-avatar" onerror="this.onerror=null; this.src='{{ student|gender_avatar }}';">
                <h1>{{ student.full_name|possessive }} Fee Calendar</h1>
            </div>
        </div>
        """
        template = Template(template_str)

        # Mock student object
        class MockStudent:
            full_name = "Vikas"
            sex = "Male"
            photo_url = "/static/data/default_avatar_male.png"

        rendered = template.render(Context({'student': MockStudent()}))
        self.assertIn('class="header"', rendered)
        self.assertIn('class="header-avatar"', rendered)
        self.assertIn("Vikas' Fee Calendar", rendered)
        self.assertIn("default_avatar_male.png", rendered)

        # Test female student
        class MockFemaleStudent:
            full_name = "Suhani Singh"
            sex = "Female"
            photo_url = "/static/data/default_avatar_female.png"

        rendered_female = template.render(Context({'student': MockFemaleStudent()}))
        self.assertIn("Suhani Singh's Fee Calendar", rendered_female)
        self.assertIn("default_avatar_female.png", rendered_female)


class FeeCalendarRealViewHeaderTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username='teacher_fee_tester',
            password='TestPassword123!',
            is_staff=True
        )
        self.student_user = User.objects.create_user(
            username='student_fee_tester',
            password='TestPassword123!'
        )
        self.student = StudentProfile.objects.create(
            user=self.student_user,
            full_name='Suhani Singh',
            sex='Female',
            mobile_number='9876543210'
        )

    def test_fee_calendar_real_view_renders_avatar_onerror_and_possessive_title(self):
        self.client.login(username='teacher_fee_tester', password='TestPassword123!')
        url = f'/teacher/student/{self.student.id}/fees/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')

        # Assert avatar img with class="header-avatar"
        self.assertIn('class="header-avatar"', content)
        # Assert onerror fallback to gender avatar
        self.assertIn("onerror=\"this.onerror=null; this.src='/static/data/default_avatar_female.png';\"", content)
        # Assert possessive title
        self.assertIn("Suhani Singh's Fee Calendar", content)
        # Assert .header class remains intact for tour and click listeners
        self.assertIn('class="header"', content)
        self.assertIn('class="header-title-row"', content)


class AvatarEndpointsAndFallbacksTests(TestCase):
    def setUp(self):
        self.teacher_user = User.objects.create_user(
            username='teacher_avatar_tester',
            password='TestPassword123!',
            is_staff=True
        )
        self.male_user = User.objects.create_user(
            username='male_student_tester',
            password='TestPassword123!'
        )
        self.male_student = StudentProfile.objects.create(
            user=self.male_user,
            full_name='Rohan Sharma',
            sex='Male',
            service_type='Library',
            mobile_number='9876543211',
            status='admitted',
            is_admitted=True
        )
        self.female_user = User.objects.create_user(
            username='female_student_tester',
            password='TestPassword123!'
        )
        self.female_student = StudentProfile.objects.create(
            user=self.female_user,
            full_name='Pooja Verma',
            sex='Female',
            service_type='Coaching',
            mobile_number='9876543212',
            status='admitted',
            is_admitted=True
        )

    def test_student_profile_photo_url_fallbacks(self):
        # Male student without photo
        self.assertEqual(self.male_student.photo_url, '/static/data/default_avatar_male.png')
        # Female student without photo
        self.assertEqual(self.female_student.photo_url, '/static/data/default_avatar_female.png')
        # Student with empty/None sex
        self.male_student.sex = ''
        self.male_student.save()
        self.assertEqual(self.male_student.photo_url, '/static/data/default_avatar.png')

    def test_student_achievement_photo_url_fallbacks(self):
        import datetime
        ach_m = StudentAchievement.objects.create(
            user=self.male_user,
            first_name='Rohan',
            last_name='Sharma',
            gender='Male',
            dob=datetime.date(2000, 1, 1),
            selection_year=2024,
            status='approved'
        )
        self.assertEqual(ach_m.photo_url, '/static/data/default_avatar_male.png')

        ach_f = StudentAchievement.objects.create(
            user=self.female_user,
            first_name='Pooja',
            last_name='Verma',
            gender='Female',
            dob=datetime.date(2002, 5, 10),
            selection_year=2024,
            status='approved'
        )
        self.assertEqual(ach_f.photo_url, '/static/data/default_avatar_female.png')

    def test_teacher_notifications_api_returns_valid_avatar_and_sex(self):
        from users.models import Notification
        Notification.objects.create(
            user=self.teacher_user,
            title="Test notification for Pooja",
            message="Test notification for Pooja",
            meta={'student_id': self.female_student.id}
        )
        self.client.login(username='teacher_avatar_tester', password='TestPassword123!')
        res = self.client.get('/api/notifications/')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        notifs = data.get('notifications', [])
        self.assertTrue(len(notifs) >= 1)
        found = False
        for n in notifs:
            s_obj = n.get('student_obj')
            if s_obj and s_obj.get('full_name') == 'Pooja Verma':
                found = True
                self.assertEqual(s_obj.get('photo_url'), '/static/data/default_avatar_female.png')
                self.assertEqual(s_obj.get('sex'), 'Female')
        self.assertTrue(found)

    def test_todo_search_students_returns_valid_avatar_and_sex(self):
        self.client.login(username='teacher_avatar_tester', password='TestPassword123!')
        res = self.client.get('/todo/search-students/?q=all')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        students = data.get('students', [])
        self.assertTrue(len(students) >= 2)
        for s in students:
            self.assertTrue(s.get('photo_url'), f"Empty photo_url for {s}")
            self.assertNotEqual(s.get('photo_url'), 'None')
            self.assertIn('sex', s)

    def test_teacher_get_users_for_manual_api_returns_valid_avatar_and_sex(self):
        self.client.login(username='teacher_avatar_tester', password='TestPassword123!')
        res = self.client.get('/api/teacher/get-users-for-manual/?context=library')
        self.assertEqual(res.status_code, 200)
        data = res.json()
        users = data.get('users', [])
        for u in users:
            self.assertTrue(u.get('photo_url'), f"Empty photo_url for {u}")
            self.assertNotEqual(u.get('photo_url'), 'None')
            self.assertIn('sex', u)

