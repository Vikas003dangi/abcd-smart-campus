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
