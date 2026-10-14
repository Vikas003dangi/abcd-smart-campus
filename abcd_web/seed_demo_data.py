import os
import sys
import shutil
import datetime
from PIL import Image

# Ensure Django environment is initialized
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'abcd_web.settings')

import django
django.setup()

from django.conf import settings
from django.contrib.auth.models import User
from django.utils import timezone
from users.models import (
    Seat, StudentProfile, TeacherProfile, StudentAchievement,
    SeatAssignment, SeatSpecialRequest, SeatHoldRequest, SeatSwitchRequest,
    SeatLeaveRequest, SeatHoldChangeRequest, CourseCategory, Course,
    StudyMaterial, CourseReview, CourseQuestion, CourseAnswer, CourseShare,
    StudentMaterialAccess, StudentCourseInteraction, LearningReminder,
    Payment, FeeTransaction, TeacherHiddenFeeTransaction,
    FeeTransactionAudit, FeeTransactionRevision, DismissedFeeAlert,
    VisitorIntent, PushSubscription, GuidanceRequest, ChatSession,
    DirectChatSession, Message, BlockedGuidance, RestrictedStudent,
    GroupChatSession, GroupMessage, TodoTask, Complaint, Notification,
    BroadcastMessage, BroadcastAttachment, BannerViewLog
)
from users.utils.receipt_generator import generate_fee_receipt_pdf
from users.email_service import send_html_email

print("=" * 60)
print("ABCD SMART CAMPUS — ULTRA-REALISTIC SEED SCRIPT")
print("=" * 60)

DEMO_PASSWORD = "Abcd#2026Campus"
TODAY = timezone.localdate()
NOW = timezone.now()

# -------------------------------------------------------------------
# 1. CLEANUP OLD DATA (PRESERVING VAKU & SANDY)
# -------------------------------------------------------------------
print("\n[Phase 1] Cleaning up old dummy & test records...")

# Preserve staff / superusers
preserved_usernames = ['Vaku', 'Sandy']
preserved_users = User.objects.filter(username__in=preserved_usernames)

# Delete all other users (cascades to their profiles, chats, etc.)
users_to_delete = User.objects.exclude(username__in=preserved_usernames)
deleted_count = users_to_delete.count()
users_to_delete.delete()
print(f" -> Removed {deleted_count} old test users.")

# Reset staff passwords to standard DEMO_PASSWORD
for u in preserved_users:
    u.set_password(DEMO_PASSWORD)
    u.is_active = True
    u.save()
    TeacherProfile.objects.get_or_create(user=u)
    print(f" -> Updated credentials for staff user: {u.username} (Password: {DEMO_PASSWORD})")

# Clear independent/audit tables
Payment.objects.all().delete()
FeeTransactionRevision.objects.all().delete()
FeeTransactionAudit.objects.all().delete()
TeacherHiddenFeeTransaction.objects.all().delete()
FeeTransaction.objects.all().delete()
DismissedFeeAlert.objects.all().delete()

SeatAssignment.objects.all().delete()
SeatSpecialRequest.objects.all().delete()
SeatHoldRequest.objects.all().delete()
SeatSwitchRequest.objects.all().delete()
SeatLeaveRequest.objects.all().delete()
SeatHoldChangeRequest.objects.all().delete()

Complaint.objects.all().delete()
CourseReview.objects.all().delete()
CourseAnswer.objects.all().delete()
CourseQuestion.objects.all().delete()
CourseShare.objects.all().delete()
StudentMaterialAccess.objects.all().delete()
StudentCourseInteraction.objects.all().delete()
LearningReminder.objects.all().delete()
StudyMaterial.objects.all().delete()
Course.objects.all().delete()
CourseCategory.objects.all().delete()

BroadcastAttachment.objects.all().delete()
BannerViewLog.objects.all().delete()
BroadcastMessage.objects.all().delete()
Notification.objects.all().delete()
VisitorIntent.objects.all().delete()
TodoTask.objects.all().delete()

# Reset all seats to clean available state
for seat in Seat.objects.all():
    seat.status = 'available'
    seat.hold_status = 'none'
    seat.hold_student = None
    seat.hold_start_date = None
    seat.hold_end_date = None
    seat.hold_request_date = None
    seat.hold_request_duration = None
    seat.is_locked = False
    seat.locked_shifts = ''
    seat.available_since = NOW
    # Strictly Ground Floor 40-53 are shift enabled
    if seat.floor == 'Ground Floor' and 40 <= int(seat.seat_number) <= 53:
        seat.is_shift_enabled = True
    else:
        seat.is_shift_enabled = False
    seat.save()

print(f" -> Reset {Seat.objects.count()} physical seats across Ground & 1st Floor to Available.")

# -------------------------------------------------------------------
# 2. PREPARE MEDIA ASSETS & FOLDERS
# -------------------------------------------------------------------
print("\n[Phase 2] Setting up media directories & copying real assets...")

media_dirs = [
    'student_photos', 'achievements', 'teacher_photos', 'course_thumbnails',
    'study_materials', 'guidy_temp', 'group_photos', 'complaints', 'broadcast_banners'
]
for md in media_dirs:
    os.makedirs(os.path.join(settings.MEDIA_ROOT, md), exist_ok=True)

faces_dir = r"b:\ABCD\mobile ss\some random faces to use for dummy - students and alumni"
other_data_dir = r"b:\ABCD\OTHER DATA ABCD"

def copy_face_asset(filename, target_subfolder, target_filename):
    src = os.path.join(faces_dir, filename)
    dst = os.path.join(settings.MEDIA_ROOT, target_subfolder, target_filename)
    if os.path.exists(src):
        # Convert webp to jpeg/png if needed or copy directly
        shutil.copyfile(src, dst)
        return os.path.join(target_subfolder, target_filename).replace('\\', '/')
    return None

def copy_doc_asset(filename, target_subfolder, target_filename):
    src = os.path.join(other_data_dir, filename)
    dst = os.path.join(settings.MEDIA_ROOT, target_subfolder, target_filename)
    if os.path.exists(src):
        shutil.copyfile(src, dst)
        return os.path.join(target_subfolder, target_filename).replace('\\', '/')
    # fallback: create a valid small placeholder PDF if missing
    with open(dst, 'wb') as f:
        f.write(b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Count 1/Kids[3 0 R]>>endobj\n3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Resources<<>>>>endobj\nxref\n0 4\n0000000000 65535 f\n0000000010 00000 n\n0000000060 00000 n\n0000000117 00000 n\ntrailer<</Size 4/Root 1 0 R>>\nstartxref\n206\n%%EOF")
    return os.path.join(target_subfolder, target_filename).replace('\\', '/')

# Seed doc assets
flowchart_pdf = copy_doc_asset("SSC CGL Census 2011 Practice Quiz.pdf", "guidy_temp", "MPPSC_Paper2_Answer_Structure_Flowchart.pdf")
roadmap_pdf = copy_doc_asset("Google Play Store Listing Audit & Preparation Plan.pdf", "guidy_temp", "SSC_CGL_Revision_Roadmap_3Weeks.pdf")
bank_pdf = copy_doc_asset("N2541023780.pdf", "guidy_temp", "IBPS_PO_Banking_Awareness_Handbook.pdf")
timetable_img = copy_doc_asset("time table.jpg", "guidy_temp", "Daily_Routine_Library_Timetable.jpg")

mat_history_pdf = copy_doc_asset("SSC CGL Census 2011 Practice Quiz.pdf", "study_materials", "Indus_Valley_and_Vedic_Period_Comprehensive_Notes.pdf")
mat_english_pdf = copy_doc_asset("Google Play Store Listing Audit & Preparation Plan.pdf", "study_materials", "English_Grammar_Top_100_Rules_Sandeep_Sir.pdf")
mat_math_pdf = copy_doc_asset("N2541023780.pdf", "study_materials", "Vedic_Math_Speed_Calculation_Tricks.pdf")
mat_ethics_pdf = copy_doc_asset("SSC CGL Census 2011 Practice Quiz.pdf", "study_materials", "MPPSC_Ethics_Case_Studies_Model_Answers.pdf")

banner_img = copy_doc_asset("time table.jpg", "broadcast_banners", "diwali_library_announcement.jpg")

# -------------------------------------------------------------------
# 3. CREATE ALUMNI MENTORS (7 VERIFIED CANDIDATES)
# -------------------------------------------------------------------
print("\n[Phase 3] Creating Alumni Mentors & Hall of Fame profiles...")

alumni_configs = [
    {
        "username": "aayush_sharma",
        "first_name": "Aayush",
        "last_name": "Sharma",
        "email": "aayush.sharma.exam@gmail.com",
        "face": "art-hauntington-0wrxaxqip58-unsplash.webp",
        "gender": "Male",
        "dob": datetime.date(1997, 4, 18),
        "post": "Deputy Collector (Rank 14, MPPSC 2024)",
        "city": "Indore",
        "year": 2024,
        "short": "MPPSC 2024 (Rank 14)",
        "about": "Selected as Deputy Collector in MPPSC 2024. Spent 2.5 years dedicatedly preparing in ABCD Library.",
        "services": "library",
        "years": 2, "days": 120,
        "mobile": "9826145230", "whatsapp": "9826145230",
        "feedback": "ABCD's disciplined, quiet cubicles and 24/7 power backup provided the perfect sanctum for cracking State Civil Services.",
        "exp": "Consistent answer writing and discussions with senior mentors at ABCD played the key role in my interview & mains score.",
        "milestones": [{"title": "MPPSC Prelims 2023 Qualified", "year": "2023"}, {"title": "MPPSC Mains & Interview (Rank 14)", "year": "2024"}],
    },
    {
        "username": "pooja_verma",
        "first_name": "Pooja",
        "last_name": "Verma",
        "email": "pooja.verma.upsc@gmail.com",
        "face": "Random_female_face_1.jpeg",
        "gender": "Female",
        "dob": datetime.date(1999, 8, 22),
        "post": "Assistant Section Officer (CSS, New Delhi)",
        "city": "New Delhi",
        "year": 2023,
        "short": "SSC CGL ASO (CSS)",
        "about": "Secured Assistant Section Officer in Central Secretariat Service through SSC CGL 2023.",
        "services": "both",
        "years": 1, "days": 240,
        "mobile": "9755123984", "whatsapp": "9755123984",
        "feedback": "Sandeep Sir's English grammar lectures and the peaceful library hall transformed my speed and accuracy in Tier 2.",
        "exp": "Daily grammar practice tests and quantitative analysis sessions laid my solid foundation.",
        "milestones": [{"title": "SSC CGL Tier 1 (168 Marks)", "year": "2023"}, {"title": "Final Selection ASO in CSS", "year": "2023"}],
    },
    {
        "username": "gaurav_patidar",
        "first_name": "Gaurav",
        "last_name": "Patidar",
        "email": "gaurav.patidar.police@gmail.com",
        "face": "images (1).jpg",
        "gender": "Male",
        "dob": datetime.date(1998, 2, 10),
        "post": "Sub-Inspector of Police (MP Police, Rank 7)",
        "city": "Bhopal",
        "year": 2024,
        "short": "MP Police SI (Rank 7)",
        "about": "Sub-Inspector in Madhya Pradesh Police. Regular aspirant at ABCD coaching and library.",
        "services": "both",
        "years": 1, "days": 180,
        "mobile": "9926834120", "whatsapp": "9926834120",
        "feedback": "Physical practice combined with ABCD's rigorous mock test series made all the difference in SI recruitment.",
        "exp": "The faculty at ABCD continuously pushed me to excel beyond my comfort zone.",
        "milestones": [{"title": "Physical Proficiency Test 100/100", "year": "2023"}, {"title": "Final Merit Rank 7 MP Police", "year": "2024"}],
    },
    {
        "username": "divya_chouksey",
        "first_name": "Divya",
        "last_name": "Chouksey",
        "email": "sanjnachouksey001@gmail.com",
        "face": "fh-1.jpg",
        "gender": "Female",
        "dob": datetime.date(2000, 11, 5),
        "post": "Probationary Officer (Bank of Baroda)",
        "city": "Jabalpur",
        "year": 2024,
        "short": "IBPS PO 2024",
        "about": "Selected as Probationary Officer in Bank of Baroda. Studied at ABCD Library 1st Floor.",
        "services": "library",
        "years": 1, "days": 15,
        "mobile": "9425098711", "whatsapp": "9425098711",
        "feedback": "The uninterrupted high-speed internet and quiet reading environment allowed me to give 3 sectional tests daily.",
        "exp": "The library atmosphere kept me motivated through multiple preliminary and mains rounds.",
        "milestones": [{"title": "IBPS PO Prelims Cleared", "year": "2023"}, {"title": "Final Selection Bank of Baroda", "year": "2024"}],
    },
    {
        "username": "harsh_rathore",
        "first_name": "Harshvardhan",
        "last_name": "Rathore",
        "email": "harsh.rathore.mppsc@gmail.com",
        "face": "images (2).jpg",
        "gender": "Male",
        "dob": datetime.date(1996, 6, 14),
        "post": "Deputy Superintendent of Police (DSP, MPPSC)",
        "city": "Ujjain",
        "year": 2023,
        "short": "MPPSC DSP 2023",
        "about": "Serving as DSP in MP Police. Longtime student member of ABCD Library.",
        "services": "library",
        "years": 2, "days": 45,
        "mobile": "9893452109", "whatsapp": "9893452109",
        "feedback": "ABCD isn't just a library; it is a community of serious civil services aspirants pushing each other to the finish line.",
        "exp": "Peer answer review groups at ABCD helped refine my presentation and time management.",
        "milestones": [{"title": "MPPSC Mains 2022 Qualified", "year": "2022"}, {"title": "Selected as DSP in MPPSC 2023", "year": "2023"}],
    },
    {
        "username": "neha_tiwari",
        "first_name": "Neha",
        "last_name": "Tiwari",
        "email": "neha.tiwari.ssc@gmail.com",
        "face": "images (5).jpg",
        "gender": "Female",
        "dob": datetime.date(2001, 3, 30),
        "post": "Revenue Inspector (MP Land Records)",
        "city": "Vidisha",
        "year": 2024,
        "short": "Revenue Inspector",
        "about": "Revenue Inspector selected via MP Patwari / Group 2 Sub-Group 4 exam.",
        "services": "both",
        "years": 1, "days": 0,
        "mobile": "9685321456", "whatsapp": "9685321456",
        "feedback": "Regular guidance from faculty and structured subject notes made difficult topics easy to grasp.",
        "exp": "I spent 8 hours daily at ABCD during the final 3 months before examination.",
        "milestones": [{"title": "Rank 18 in Vidisha District", "year": "2024"}],
    },
    {
        "username": "kunal_malviya",
        "first_name": "Kunal",
        "last_name": "Malviya",
        "email": "kunal.malviya.rrb@gmail.com",
        "face": "images (4).jpg",
        "gender": "Male",
        "dob": datetime.date(1998, 9, 12),
        "post": "Station Master (West Central Railway)",
        "city": "Itarsi",
        "year": 2024,
        "short": "RRB NTPC Station Master",
        "about": "Station Master in Indian Railways. Prepared in ABCD Ground Floor Library.",
        "services": "library",
        "years": 1, "days": 90,
        "mobile": "9826701923", "whatsapp": "9826701923",
        "feedback": "Affordable fee structure with premium infrastructure — ABCD provided me the confidence to secure central government employment.",
        "exp": "The aptitude and reasoning shortcut methods taught here saved valuable exam time.",
        "milestones": [{"title": "RRB NTPC CBAT Aptitude Test Qualified", "year": "2023"}, {"title": "Joined as Station Master", "year": "2024"}],
    }
]

created_alumni = []
for c in alumni_configs:
    u = User.objects.create_user(
        username=c['username'],
        email=c['email'],
        first_name=c['first_name'],
        last_name=c['last_name'],
        password=DEMO_PASSWORD
    )
    
    photo_rel = copy_face_asset(c['face'], "achievements", f"{c['username']}.jpg")
    copy_face_asset(c['face'], "student_photos", f"{c['username']}.jpg")

    ach = StudentAchievement.objects.create(
        user=u,
        first_name=c['first_name'],
        last_name=c['last_name'],
        about_yourself=c['about'],
        current_post=c['post'],
        selection_year=c['year'],
        working_city=c['city'],
        short_achievement=c['short'],
        gender=c['gender'],
        dob=c['dob'],
        services_used=c['services'],
        duration_years=c['years'],
        duration_days=c['days'],
        mobile_number=c['mobile'],
        whatsapp_number=c['whatsapp'],
        email=c['email'],
        experience_feedback=c['exp'],
        other_achievements=c['milestones'],
        rating=5,
        abcd_feedback=c['feedback'],
        status='approved',
        approved_at=NOW - datetime.timedelta(days=60)
    )
    if photo_rel:
        ach.photo.name = photo_rel
        ach.save()

    # Also create an active StudentProfile so they can navigate seamlessly
    prof = StudentProfile.objects.create(
        user=u,
        full_name=f"{c['first_name']} {c['last_name']}",
        dob=c['dob'],
        sex=c['gender'],
        email=c['email'],
        mobile_number=c['mobile'],
        whatsapp_number=c['whatsapp'],
        service_type='Library' if c['services'] == 'library' else 'Both',
        status='admitted',
        is_admitted=True,
        admission_type='existing',
        fee_expiry_date=TODAY + datetime.timedelta(days=180),
        approved_at=NOW - datetime.timedelta(days=60)
    )
    if photo_rel:
        prof.photo.name = f"student_photos/{c['username']}.jpg"
        prof.save()

    created_alumni.append((u, ach, prof))
    print(f" -> Created Verified Alumni: {ach.full_name} ({ach.short_achievement})")

# -------------------------------------------------------------------
# 4. CREATE ENROLLED & APPLICANT STUDENTS (ALL SEAT STATUSES)
# -------------------------------------------------------------------
print("\n[Phase 4] Creating Students & Configuring Library Seat Allocations...")

# Get target seats
s12 = Seat.objects.get(floor='Ground Floor', seat_number='12')
s15 = Seat.objects.get(floor='Ground Floor', seat_number='15')
s20 = Seat.objects.get(floor='Ground Floor', seat_number='20')
s42 = Seat.objects.get(floor='Ground Floor', seat_number='42') # shift enabled
s44 = Seat.objects.get(floor='Ground Floor', seat_number='44') # shift enabled
s45 = Seat.objects.get(floor='Ground Floor', seat_number='45') # shift enabled
s46 = Seat.objects.get(floor='Ground Floor', seat_number='46') # shift enabled
s8  = Seat.objects.get(floor='Ground Floor', seat_number='8')
s5_1st = Seat.objects.get(floor='1st Floor', seat_number='5')

# 1. Rohan Mehta -> Full Day Occupied on Seat 12
u_rohan = User.objects.create_user(username="rohan_mehta", email="rohan.mehta.study@gmail.com", first_name="Rohan", last_name="Mehta", password=DEMO_PASSWORD)
copy_face_asset("images.jpg", "student_photos", "rohan_mehta.jpg")
prof_rohan = StudentProfile.objects.create(
    user=u_rohan, full_name="Rohan Mehta", dob=datetime.date(2002, 5, 14), sex="Male",
    email="rohan.mehta.study@gmail.com", mobile_number="9826012345", whatsapp_number="9826012345",
    service_type="Library", seat=s12, shift="full", status="admitted", is_admitted=True,
    admission_type="new", fee_expiry_date=TODAY + datetime.timedelta(days=32),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=32), approved_at=NOW - datetime.timedelta(days=40)
)
prof_rohan.photo.name = "student_photos/rohan_mehta.jpg"
prof_rohan.save()

SeatAssignment.objects.create(seat=s12, student=prof_rohan, shift_type="full", is_active=True, hold_status="none")
s12.status = 'occupied'
s12.save()
print(" -> [Seat 12 Ground] Configured FULL DAY OCCUPIED (Rohan Mehta)")

# 2. Ananya Gupta -> Full Day On Hold on Seat 15
u_ananya = User.objects.create_user(username="ananya_gupta", email="ananya.gupta.prep@gmail.com", first_name="Ananya", last_name="Gupta", password=DEMO_PASSWORD)
copy_face_asset("tumblr_pnpkvnwpWI1uo5d9jo3_1280.jpg", "student_photos", "ananya_gupta.jpg")
prof_ananya = StudentProfile.objects.create(
    user=u_ananya, full_name="Ananya Gupta", dob=datetime.date(2003, 1, 19), sex="Female",
    email="ananya.gupta.prep@gmail.com", mobile_number="9755432109", whatsapp_number="9755432109",
    service_type="Library", seat=s15, shift="full", status="on_hold", is_admitted=True,
    admission_type="new", hold_start_date=TODAY - datetime.timedelta(days=5),
    hold_end_date=TODAY + datetime.timedelta(days=25), fee_expiry_date=TODAY + datetime.timedelta(days=60),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=60), approved_at=NOW - datetime.timedelta(days=50)
)
prof_ananya.photo.name = "student_photos/ananya_gupta.jpg"
prof_ananya.save()

SeatAssignment.objects.create(
    seat=s15, student=prof_ananya, shift_type="full", is_active=True,
    hold_status="active", hold_start_date=TODAY - datetime.timedelta(days=5),
    hold_end_date=TODAY + datetime.timedelta(days=25)
)
s15.status = 'on_hold'
s15.hold_status = 'active'
s15.hold_student = prof_ananya
s15.hold_start_date = TODAY - datetime.timedelta(days=5)
s15.hold_end_date = TODAY + datetime.timedelta(days=25)
s15.save()
print(" -> [Seat 15 Ground] Configured FULL DAY ON HOLD (Ananya Gupta)")

# 3. Aditya Saxena -> Evening Occupied (Morning Free) on Shift Seat 42
u_aditya = User.objects.create_user(username="aditya_saxena", email="aditya.saxena.gov@gmail.com", first_name="Aditya", last_name="Saxena", password=DEMO_PASSWORD)
copy_face_asset("images (3).jpg", "student_photos", "aditya_saxena.jpg")
prof_aditya = StudentProfile.objects.create(
    user=u_aditya, full_name="Aditya Saxena", dob=datetime.date(2002, 10, 8), sex="Male",
    email="aditya.saxena.gov@gmail.com", mobile_number="9893112233", whatsapp_number="9893112233",
    service_type="Library", seat=s42, shift="evening", status="admitted", is_admitted=True,
    admission_type="new", fee_expiry_date=TODAY + datetime.timedelta(days=28),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=28), approved_at=NOW - datetime.timedelta(days=20)
)
prof_aditya.photo.name = "student_photos/aditya_saxena.jpg"
prof_aditya.save()

SeatAssignment.objects.create(seat=s42, student=prof_aditya, shift_type="evening", is_active=True, hold_status="none")
s42.status = 'occupied'
s42.save()
print(" -> [Seat 42 Ground] Configured EVENING OCCUPIED & MORNING FREE (Aditya Saxena)")

# 4. Siddharth Jain -> One Shift On Hold (Morning Hold, Evening Free) on Shift Seat 44
u_siddharth = User.objects.create_user(username="siddharth_jain", email="siddharth.jain.ca@gmail.com", first_name="Siddharth", last_name="Jain", password=DEMO_PASSWORD)
copy_face_asset("v3_0539094.jpg", "student_photos", "siddharth_jain.jpg")
prof_siddharth = StudentProfile.objects.create(
    user=u_siddharth, full_name="Siddharth Jain", dob=datetime.date(2001, 7, 25), sex="Male",
    email="siddharth.jain.ca@gmail.com", mobile_number="9424009988", whatsapp_number="9424009988",
    service_type="Library", seat=s44, shift="morning", status="on_hold", is_admitted=True,
    admission_type="new", hold_start_date=TODAY - datetime.timedelta(days=3),
    hold_end_date=TODAY + datetime.timedelta(days=18), fee_expiry_date=TODAY + datetime.timedelta(days=45),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=45), approved_at=NOW - datetime.timedelta(days=35)
)
prof_siddharth.photo.name = "student_photos/siddharth_jain.jpg"
prof_siddharth.save()

SeatAssignment.objects.create(
    seat=s44, student=prof_siddharth, shift_type="morning", is_active=True,
    hold_status="active", hold_start_date=TODAY - datetime.timedelta(days=3),
    hold_end_date=TODAY + datetime.timedelta(days=18)
)
s44.status = 'on_hold'
s44.hold_status = 'active'
s44.hold_student = prof_siddharth
s44.hold_start_date = TODAY - datetime.timedelta(days=3)
s44.hold_end_date = TODAY + datetime.timedelta(days=18)
s44.save()
print(" -> [Seat 44 Ground] Configured MORNING SHIFT ON HOLD & EVENING FREE (Siddharth Jain)")

# 5. Manish Chouhan (Morning Occupied) & Priya Soni (Evening On Hold) on Shift Seat 45
u_manish = User.objects.create_user(username="manish_chouhan", email="manish.chouhan.engg@gmail.com", first_name="Manish", last_name="Chouhan", password=DEMO_PASSWORD)
copy_face_asset("images (6).jpg", "student_photos", "manish_chouhan.jpg")
prof_manish = StudentProfile.objects.create(
    user=u_manish, full_name="Manish Chouhan", dob=datetime.date(2002, 12, 1), sex="Male",
    email="manish.chouhan.engg@gmail.com", mobile_number="9685123450", whatsapp_number="9685123450",
    service_type="Library", seat=s45, shift="morning", status="admitted", is_admitted=True,
    admission_type="new", fee_expiry_date=TODAY + datetime.timedelta(days=22),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=22), approved_at=NOW - datetime.timedelta(days=15)
)
prof_manish.photo.name = "student_photos/manish_chouhan.jpg"
prof_manish.save()
SeatAssignment.objects.create(seat=s45, student=prof_manish, shift_type="morning", is_active=True, hold_status="none")

u_priya = User.objects.create_user(username="priya_soni", email="priya.soni.aspirant@gmail.com", first_name="Priya", last_name="Soni", password=DEMO_PASSWORD)
copy_face_asset("images (7).jpg", "student_photos", "priya_soni.jpg")
prof_priya = StudentProfile.objects.create(
    user=u_priya, full_name="Priya Soni", dob=datetime.date(2003, 4, 11), sex="Female",
    email="priya.soni.aspirant@gmail.com", mobile_number="9111456789", whatsapp_number="9111456789",
    service_type="Library", seat=s45, shift="evening", status="on_hold", is_admitted=True,
    admission_type="new", hold_start_date=TODAY - datetime.timedelta(days=2),
    hold_end_date=TODAY + datetime.timedelta(days=22), fee_expiry_date=TODAY + datetime.timedelta(days=50),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=50), approved_at=NOW - datetime.timedelta(days=25)
)
prof_priya.photo.name = "student_photos/priya_soni.jpg"
prof_priya.save()
SeatAssignment.objects.create(
    seat=s45, student=prof_priya, shift_type="evening", is_active=True,
    hold_status="active", hold_start_date=TODAY - datetime.timedelta(days=2),
    hold_end_date=TODAY + datetime.timedelta(days=22)
)
s45.status = 'occupied'
s45.save()
print(" -> [Seat 45 Ground] Configured MORNING OCCUPIED + EVENING ON HOLD (Manish & Priya)")

# 6. Devansh Bhargava -> Temporary Allotted (Tenant) on Seat 20 (Original occupant on leave)
u_orig_leave = User.objects.create_user(username="rahul_tiwari", email="rahul.tiwari.leave@gmail.com", first_name="Rahul", last_name="Tiwari", password=DEMO_PASSWORD)
prof_orig_leave = StudentProfile.objects.create(
    user=u_orig_leave, full_name="Rahul Tiwari", dob=datetime.date(2001, 2, 17), sex="Male",
    email="rahul.tiwari.leave@gmail.com", mobile_number="9826998877", whatsapp_number="9826998877",
    service_type="Library", seat=s20, shift="full", status="on_hold", is_admitted=True,
    admission_type="existing", hold_start_date=TODAY - datetime.timedelta(days=4),
    hold_end_date=TODAY + datetime.timedelta(days=16), fee_expiry_date=TODAY + datetime.timedelta(days=40),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=40), approved_at=NOW - datetime.timedelta(days=60)
)
SeatAssignment.objects.create(
    seat=s20, student=prof_orig_leave, shift_type="full", is_active=True,
    hold_status="active", hold_start_date=TODAY - datetime.timedelta(days=4),
    hold_end_date=TODAY + datetime.timedelta(days=16), allow_hold_override=True
)

u_devansh = User.objects.create_user(username="devansh_bhargava", email="devanshbharatghoomo@gmail.com", first_name="Devansh", last_name="Bhargava", password=DEMO_PASSWORD)
copy_face_asset("images (1).jpg", "student_photos", "devansh_bhargava.jpg")
prof_devansh = StudentProfile.objects.create(
    user=u_devansh, full_name="Devansh Bhargava", dob=datetime.date(2002, 9, 14), sex="Male",
    email="devanshbharatghoomo@gmail.com", mobile_number="9981234567", whatsapp_number="9981234567",
    service_type="Library", seat=s20, shift="full", status="admitted", is_admitted=True,
    admission_type="new", fee_expiry_date=TODAY + datetime.timedelta(days=16),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=16), approved_at=NOW - datetime.timedelta(days=3)
)
prof_devansh.photo.name = "student_photos/devansh_bhargava.jpg"
prof_devansh.save()

# Temporary Tenant assignment
SeatAssignment.objects.create(
    seat=s20, student=prof_devansh, shift_type="full", is_active=True,
    hold_status="none", is_partial=True
)
s20.status = 'on_hold'
s20.hold_status = 'active'
s20.hold_student = prof_orig_leave
s20.hold_start_date = TODAY - datetime.timedelta(days=4)
s20.hold_end_date = TODAY + datetime.timedelta(days=16)
s20.save()
print(" -> [Seat 20 Ground] Configured TEMPORARY TENANT ALLOTTED (Devansh on Rahul's Held Seat)")

# 7. Ritika Deshmukh -> Shift Temporary Allotted on Seat 46 Morning
u_vikram = User.objects.create_user(username="vikram_singh", email="vikram.singh.ev@gmail.com", first_name="Vikram", last_name="Singh", password=DEMO_PASSWORD)
prof_vikram = StudentProfile.objects.create(
    user=u_vikram, full_name="Vikram Singh", dob=datetime.date(2001, 8, 20), sex="Male",
    email="vikram.singh.ev@gmail.com", mobile_number="9826334455", whatsapp_number="9826334455",
    service_type="Library", seat=s46, shift="evening", status="admitted", is_admitted=True,
    admission_type="new", fee_expiry_date=TODAY + datetime.timedelta(days=30),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=30), approved_at=NOW - datetime.timedelta(days=10)
)
SeatAssignment.objects.create(seat=s46, student=prof_vikram, shift_type="evening", is_active=True, hold_status="none")

u_ritika = User.objects.create_user(username="ritika_deshmukh", email="ritika.deshmukh.exam@gmail.com", first_name="Ritika", last_name="Deshmukh", password=DEMO_PASSWORD)
copy_face_asset("Random_female_face_1.jpeg", "student_photos", "ritika_deshmukh.jpg")
prof_ritika = StudentProfile.objects.create(
    user=u_ritika, full_name="Ritika Deshmukh", dob=datetime.date(2003, 6, 18), sex="Female",
    email="ritika.deshmukh.exam@gmail.com", mobile_number="9755887766", whatsapp_number="9755887766",
    service_type="Library", seat=s46, shift="morning", status="admitted", is_admitted=True,
    admission_type="new", fee_expiry_date=TODAY + datetime.timedelta(days=15),
    library_fee_expiry_date=TODAY + datetime.timedelta(days=15), approved_at=NOW - datetime.timedelta(days=4)
)
prof_ritika.photo.name = "student_photos/ritika_deshmukh.jpg"
prof_ritika.save()
SeatAssignment.objects.create(seat=s46, student=prof_ritika, shift_type="morning", is_active=True, hold_status="none", is_partial=True)
s46.status = 'occupied'
s46.save()
print(" -> [Seat 46 Ground] Configured SHIFT TEMPORARY ALLOTTED (Ritika on Morning Shift)")

# 8. Kartik Mishra -> Pending Seat on Seat 8
u_kartik = User.objects.create_user(username="kartik_mishra", email="kartik.mishra.upsc@gmail.com", first_name="Kartik", last_name="Mishra", password=DEMO_PASSWORD)
copy_face_asset("images (2).jpg", "student_photos", "kartik_mishra.jpg")
prof_kartik = StudentProfile.objects.create(
    user=u_kartik, full_name="Kartik Mishra", dob=datetime.date(2002, 11, 29), sex="Male",
    email="kartik.mishra.upsc@gmail.com", mobile_number="9893998811", whatsapp_number="9893998811",
    service_type="Library", seat=s8, shift="full", status="pending", is_admitted=False,
    admission_type="new"
)
prof_kartik.photo.name = "student_photos/kartik_mishra.jpg"
prof_kartik.save()
SeatAssignment.objects.create(seat=s8, student=prof_kartik, shift_type="full", is_active=False, hold_status="none")
s8.status = 'pending'
s8.save()
print(" -> [Seat 8 Ground] Configured PENDING SEAT REQUEST (Kartik Mishra)")

# 9. Sneha Patel -> Both Coaching & Library (1st Floor Seat 5), Coaching Active, Library Overdue
u_sneha = User.objects.create_user(username="sneha_patel", email="sneha.patel.ssc@gmail.com", first_name="Sneha", last_name="Patel", password=DEMO_PASSWORD)
copy_face_asset("fh-1.jpg", "student_photos", "sneha_patel.jpg")
prof_sneha = StudentProfile.objects.create(
    user=u_sneha, full_name="Sneha Patel", dob=datetime.date(2002, 3, 15), sex="Female",
    email="sneha.patel.ssc@gmail.com", mobile_number="9425887711", whatsapp_number="9425887711",
    service_type="Both", batch="Grammar Batch 1", seat=s5_1st, shift="full", status="admitted",
    is_admitted=True, admission_type="new",
    coaching_fee_expiry_date=TODAY + datetime.timedelta(days=25),
    library_fee_expiry_date=TODAY - datetime.timedelta(days=3), # Overdue 3 days!
    fee_expiry_date=TODAY - datetime.timedelta(days=3),
    approved_at=NOW - datetime.timedelta(days=45)
)
prof_sneha.photo.name = "student_photos/sneha_patel.jpg"
prof_sneha.save()
SeatAssignment.objects.create(seat=s5_1st, student=prof_sneha, shift_type="full", is_active=True, hold_status="none")
s5_1st.status = 'occupied'
s5_1st.save()
print(" -> [Seat 5 1st Floor] Configured DUAL SERVICE (Sneha Patel - Coaching Active, Lib Overdue 3 Days)")

# 10. Amit Trivedi -> Coaching Only Student
u_amit = User.objects.create_user(username="amit_trivedi", email="amit.trivedi.bank@gmail.com", first_name="Amit", last_name="Trivedi", password=DEMO_PASSWORD)
copy_face_asset("images (4).jpg", "student_photos", "amit_trivedi.jpg")
prof_amit = StudentProfile.objects.create(
    user=u_amit, full_name="Amit Trivedi", dob=datetime.date(2001, 10, 4), sex="Male",
    email="amit.trivedi.bank@gmail.com", mobile_number="9827001122", whatsapp_number="9827001122",
    service_type="Coaching", batch="Spoken English 1", status="admitted", is_admitted=True,
    admission_type="new", coaching_fee_expiry_date=TODAY + datetime.timedelta(days=5),
    fee_expiry_date=TODAY + datetime.timedelta(days=5), approved_at=NOW - datetime.timedelta(days=25)
)
prof_amit.photo.name = "student_photos/amit_trivedi.jpg"
prof_amit.save()
print(" -> Configured COACHING ONLY STUDENT (Amit Trivedi - Expiry in 5 Days)")

# -------------------------------------------------------------------
# 5. CREATE STATUTORY FEES & INVOICES
# -------------------------------------------------------------------
print("\n[Phase 5] Generating Fee Records & Statutory Invoices...")

teacher_user = User.objects.filter(username="Sandy").first() or preserved_users.first()

def add_fee_payment(student, service, amount, months_list, expiry_date):
    rcpt = FeeTransaction.generate_receipt_number()
    month_name = months_list[0] if months_list else TODAY.strftime("%B")
    
    trans = FeeTransaction.objects.create(
        student=student,
        teacher=teacher_user,
        service=service,
        receipt_number=rcpt,
        payment_date=TODAY - datetime.timedelta(days=2),
        expiry_date=expiry_date,
        service_snapshot=f"{service.title()} Service (Regular Desk Allotment)",
        months_snapshot=[{"month": m, "amount": amount // len(months_list), "status": "Paid"} for m in months_list],
        total_amount=amount,
        email_sent=True,
        whatsapp_sent=True,
        student_name_snapshot=student.full_name,
        roll_number_snapshot=f"ABCD-{student.id:04d}",
        mobile_snapshot=student.mobile_number,
        course_snapshot=f"{student.service_type} Service"
    )

    for m in months_list:
        Payment.objects.create(
            student=student,
            service=service,
            month=m,
            year=TODAY.year,
            amount=amount // len(months_list),
            date_paid=TODAY - datetime.timedelta(days=2),
            fee_transaction=trans
        )
    return trans

t1 = add_fee_payment(prof_rohan, "library", 1500, [TODAY.strftime("%B")], TODAY + datetime.timedelta(days=32))
t2 = add_fee_payment(prof_ananya, "library", 3000, [TODAY.strftime("%B"), (TODAY + datetime.timedelta(days=32)).strftime("%B")], TODAY + datetime.timedelta(days=60))
t3 = add_fee_payment(prof_sneha, "coaching", 2500, [TODAY.strftime("%B")], TODAY + datetime.timedelta(days=25))
t4 = add_fee_payment(prof_amit, "coaching", 2000, [(TODAY - datetime.timedelta(days=25)).strftime("%B")], TODAY + datetime.timedelta(days=5))
print(f" -> Generated official fee receipts: {t1.receipt_number}, {t2.receipt_number}, {t3.receipt_number}, {t4.receipt_number}")

# -------------------------------------------------------------------
# 6. CREATE REALISTIC COURSES & STUDY MATERIALS
# -------------------------------------------------------------------
print("\n[Phase 6] Creating Realistic Courses, Curated Materials & Reviews...")

cat_civil = CourseCategory.objects.create(name="Civil Services (MPPSC & UPSC)", slug="civil-services", order=1, is_active=True)
cat_lang  = CourseCategory.objects.create(name="English Language & Communication", slug="english-communication", order=2, is_active=True)
cat_bank  = CourseCategory.objects.create(name="Banking, SSC & Railways Aptitude", slug="banking-ssc", order=3, is_active=True)
cat_gs    = CourseCategory.objects.create(name="General Studies & Science Tech", slug="general-studies", order=4, is_active=True)

courses_def = [
    {
        "cat": cat_civil,
        "title": "MPPSC General Studies Paper 1: Ancient & Medieval Indian History",
        "desc": "Comprehensive syllabus coverage of Ancient Indian civilisations, Mauryan & Gupta dynasties, Medieval regional sultanates, and Madhya Pradesh cultural landmarks with previous 10 years question analysis.",
        "video": "https://www.youtube.com/watch?v=PESBR2XSGuE",
        "doc": mat_history_pdf,
        "doc_title": "Indus Valley & Vedic Period Comprehensive Analysis Notes (PDF)",
        "reviews": [
            (prof_rohan, 5, "Remarkable depth of coverage. The chronology charts for Dynasties made answer writing so much easier."),
            (prof_sneha, 5, "Concise and strictly aligned to the latest MPPSC syllabus pattern.")
        ],
        "qa": ("Are regional kingdoms of MP like Chandela and Paramara covered in Unit 1?", "Yes Rohan, Unit 1 includes comprehensive video analysis and PDF notes on Chandela, Paramara, and Kalachuri dynasties.")
    },
    {
        "cat": cat_lang,
        "title": "English Grammar Mastery & Spoken Fluency (by Sandeep Sir)",
        "desc": "Master competitive English grammar rules, preposition usage, clause analysis, and confident spoken conversation skills designed specifically for Hindi-medium competitive exam aspirants.",
        "video": "https://www.youtube.com/watch?v=ajyB8JR0kfQ",
        "doc": mat_english_pdf,
        "doc_title": "Top 100 Common Errors in Competitive English (Handwritten Notes)",
        "reviews": [
            (prof_amit, 5, "Sandeep Sir's explanation of prepositions (by, till, until) solved my persistent confusion in SSC exams!"),
            (prof_devansh, 5, "The classroom spoken activities boost speaking confidence tremendously.")
        ],
        "qa": ("Will this course also cover descriptive letter writing for SSC Tier 2?", "Yes Amit, the final module includes format templates and high-scoring sample letters for descriptive tiers.")
    },
    {
        "cat": cat_bank,
        "title": "Quantitative Aptitude & Speed Mathematics for Banking & SSC",
        "desc": "Learn high-speed calculation shortcuts, Vedic math techniques, advanced ratio-proportion formulas, and DI interpretation strategies to solve 35 questions under 20 minutes.",
        "video": "https://www.youtube.com/watch?v=dDHEd_EXiaI",
        "doc": mat_math_pdf,
        "doc_title": "200 Fast Math Formulas & Shortcut Trick Sheets",
        "reviews": [
            (prof_aditya, 5, "My arithmetic speed improved by almost 40% after practicing the percentage shortcut tricks.")
        ],
        "qa": ("Can we apply these speed tricks in Mains level complex Caselet DI?", "Yes Aditya, speed math forms the arithmetic foundation for cracking high-level Caselet tables.")
    },
    {
        "cat": cat_civil,
        "title": "Ethics, Integrity & Administrative Aptitude (MPPSC Paper IV)",
        "desc": "A dedicated masterclass covering moral thinkers, attitude & emotional intelligence, anti-corruption frameworks, and real-life administrative case studies with standard model answers.",
        "video": "https://www.youtube.com/watch?v=K0H13vImmOE",
        "doc": mat_ethics_pdf,
        "doc_title": "Top 25 Administrative Ethics Case Studies with Model Answers",
        "reviews": [
            (prof_rohan, 5, "The framework provided for tackling dilemma-based case studies is practical and exam-tested.")
        ],
        "qa": ("How many thinkers are covered in the video series?", "All 18 philosophers and social reformers prescribed in the updated MPPSC syllabus are covered with dedicated case questions.")
    },
    {
        "cat": cat_gs,
        "title": "General Science, Environmental Ecology & Space Technology",
        "desc": "Targeted conceptual lectures covering physics in daily life, human anatomy, bio-diversity conservation, climate summits, and Indian space missions (ISRO Chandrayaan & Gaganyaan).",
        "video": "https://www.youtube.com/watch?v=PESBR2XSGuE",
        "doc": mat_history_pdf,
        "doc_title": "ISRO & Defence Space Missions Quick Review 2024-2026",
        "reviews": [
            (prof_sneha, 4, "Extremely relevant for Paper 3 Science and Tech units.")
        ],
        "qa": ("Are recent ISRO cryogenic launches included in the notes?", "Yes, all missions up to the current session are thoroughly updated in the reference PDF.")
    }
]

created_courses = []
for cdata in courses_def:
    crs = Course.objects.create(
        category=cdata['cat'],
        title=cdata['title'],
        description=cdata['desc'],
        video_url=cdata['video'],
        is_active=True,
        created_by=teacher_user,
        target_public=True,
        target_coaching=True,
        target_library=True,
        target_alumni=True
    )
    # Add material
    StudyMaterial.objects.create(
        course=crs,
        title=cdata['doc_title'],
        material_type='document',
        file=cdata['doc'],
        uploaded_by=teacher_user
    )
    # Add reviews
    for rev_stud, stars, comm in cdata['reviews']:
        CourseReview.objects.create(
            course=crs,
            student=rev_stud,
            rating=stars,
            comment=comm
        )
    # Add Q&A
    q_text, a_text = cdata['qa']
    cq = CourseQuestion.objects.create(
        course=crs,
        student=prof_rohan,
        question=q_text
    )
    CourseAnswer.objects.create(
        question=cq,
        user=teacher_user,
        answer_text=a_text,
        is_teacher_answer=True
    )
    created_courses.append(crs)
    print(f" -> Created Course: {crs.title}")

# -------------------------------------------------------------------
# 7. TO-DO HUB (TASK BREAKDOWNS, REMINDERS, STICKY NOTES, TRASH)
# -------------------------------------------------------------------
print("\n[Phase 7] Populating To-Do Hub Tasks for Rohan Mehta & Sneha Patel...")

# Rohan's Productivity Desk
TodoTask.objects.create(
    user=u_rohan,
    category="BREAKDOWN",
    metadata={
        "title": "MPPSC 2026 Prelims 60-Day Master Sprint",
        "total_hours": 120.0,
        "reservePoolMs": 14400000,
        "deadline": (TODAY + datetime.timedelta(days=60)).strftime("%Y-%m-%d"),
        "subtasks": [
            {"name": "MP History, Culture & Tribal Heritage (Unit 1 & 10)", "hours": 30.0, "remaining_hours": 8.0, "is_done": False},
            {"name": "Geography of MP & Major River Projects (Unit 3)", "hours": 25.0, "remaining_hours": 5.0, "is_done": False},
            {"name": "Constitutional Framework & State Polity (Unit 5)", "hours": 20.0, "remaining_hours": 0.0, "is_done": True},
            {"name": "ICT, Robotics, AI & Cyber Security (Unit 9)", "hours": 20.0, "remaining_hours": 12.0, "is_done": False},
            {"name": "Current National & MP Affairs (Last 8 Months)", "hours": 15.0, "remaining_hours": 10.0, "is_done": False},
            {"name": "Full Length Mock Tests (FLT 1 to 5)", "hours": 10.0, "remaining_hours": 4.0, "is_done": False}
        ]
    },
    auto_delete=False,
    is_pinned=True
)

TodoTask.objects.create(
    user=u_rohan,
    category="TODO",
    metadata={"task_name": "Revise Unit 10 MP Tribal Leaders & Freedom Fighters", "description": "Make bullet summary for quick morning recall", "color": "#7b61ff", "order": 1},
    is_pinned=True
)
TodoTask.objects.create(
    user=u_rohan,
    category="TODO",
    metadata={"task_name": "Solve 50 Quant questions on Speed, Time & Distance", "description": "Focus on train passing platform & relative speed formulas", "color": "#38bdf8", "order": 2}
)
TodoTask.objects.create(
    user=u_rohan,
    category="TODO",
    metadata={"task_name": "Collect Speed Post Dispatch Receipt for Roll No", "description": "Inquire with front desk coordinator at ABCD entrance", "color": "#34d399", "order": 3}
)
TodoTask.objects.create(
    user=u_rohan,
    category="TODO",
    metadata={"task_name": "Read The Hindu editorial & record vocabulary", "description": "International Relations & Trade section", "color": "#f59e0b", "order": 4},
    is_done=True
)

TodoTask.objects.create(
    user=u_rohan,
    category="REMINDER",
    metadata={"title": "Evening GS Mock Test Discussion", "recurrence": "daily", "time_str": "18:30", "alarm_enabled": True, "alarm_status": "active", "email_notify": True}
)
TodoTask.objects.create(
    user=u_rohan,
    category="REMINDER",
    metadata={"title": "Library Morning Shift Sign-in", "recurrence": "daily", "time_str": "07:55", "alarm_enabled": True, "alarm_status": "active", "email_notify": False}
)

TodoTask.objects.create(
    user=u_rohan,
    category="NOTE",
    metadata={
        "title": "Fundamental Rights Articles (Part III)",
        "content": "• Articles 14-18: Right to Equality\n• Articles 19-22: Right to Freedom\n• Articles 23-24: Right against Exploitation\n• Articles 25-28: Freedom of Religion\n• Articles 29-30: Cultural & Educational Rights\n• Article 32: Constitutional Remedies (Heart & Soul)",
        "note_color": "#fef08a",
        "rotation": -2
    }
)
TodoTask.objects.create(
    user=u_rohan,
    category="NOTE",
    metadata={
        "title": "Key Mineral Belts in MP",
        "content": "• Diamond: Panna & Chhatarpur Hinota mine\n• Copper: Malanjkhand belt (Balaghat)\n• Manganese: Bharveli mine (Balaghat)\n• Coal: Singrauli & Pench-Kanhan Valley\n• Limestone: Katni & Satna cement corridors",
        "note_color": "#fed7aa",
        "rotation": 2
    }
)
TodoTask.objects.create(
    user=u_rohan,
    category="NOTE",
    metadata={
        "title": "Reading Hall Ethics & Rules",
        "content": "1. Mobile phones strictly on silent/vibration.\n2. Keep water bottles in lower floor rack.\n3. Return reference newspapers by 1:00 PM.\n4. Lock study cubicle drawers before leaving.",
        "note_color": "#bbf7d0",
        "rotation": -1
    }
)

# Trashed task in Rohan's desk
TodoTask.objects.create(
    user=u_rohan,
    category="TODO",
    metadata={"task_name": "Old SSC Test Paper 2022 printout", "description": "Discarded after online test series integration", "color": "#cbd5e1"},
    is_trash=True,
    trashed_at=NOW - datetime.timedelta(days=2)
)
print(" -> Created full To-Do suite for Rohan Mehta (Breakdown, Sticky Notes, Todos, Alarms, Trash).")

# -------------------------------------------------------------------
# 8. GUIDY CHATS & MENTORSHIP CONVERSATIONS
# -------------------------------------------------------------------
print("\n[Phase 8] Initializing Guidy 1-on-1 Chats, Rich Attachments & Study Groups...")

u_aayush = created_alumni[0][0]
u_pooja  = created_alumni[1][0]
u_gaurav = created_alumni[2][0]
u_divya  = created_alumni[3][0]

# Chat 1: Rohan Mehta <--> Aayush Sharma (Deputy Collector)
req1 = GuidanceRequest.objects.create(
    student=u_rohan,
    alumni=created_alumni[0][1], # Aayush
    status='accepted',
    message="Respected Aayush Bhaiya, I am preparing for MPPSC 2026 from ABCD Library. Requesting your guidance on Paper 2 Mains answer writing."
)
session1 = ChatSession.objects.create(
    request=req1,
    user_one=u_rohan,
    user_two=u_aayush,
    is_active=True
)

m1 = Message.objects.create(session=session1, sender=u_rohan, content="Pranam Aayush Bhaiya! I am practicing 11-marker answers for Polity & Governance in ABCD reading hall. How should I structure answers to secure 8+ marks?", message_type='text')
m2 = Message.objects.create(session=session1, sender=u_aayush, content="Hello Rohan! Great to see your dedication. Always begin with a concise 2-line constitutional article or Supreme Court doctrine. Then divide the body into 3 clear dimensions: Institutional Framework, Ground Challenges, and Way Forward.", message_type='text')
m3 = Message.objects.create(session=session1, sender=u_rohan, content="Understood bhaiya! Do flowcharts and diagrams fetch extra marks in MPPSC Mains?", message_type='text')

m4 = Message.objects.create(
    session=session1, sender=u_aayush,
    content="Yes absolutely! Flowcharts save valuable words and make your copy stand out. I am attaching my personal 3-page structural flowchart that I used during my preparation at ABCD.",
    message_type='document',
    file=flowchart_pdf,
    file_name="MPPSC_Paper2_Answer_Structure_Flowchart.pdf"
)
m5 = Message.objects.create(session=session1, sender=u_rohan, content="Thank you so much Bhaiya! This flowchart clears my doubts completely. I will practice 2 questions following this exact format today.", message_type='text')
m6 = Message.objects.create(session=session1, sender=u_aayush, content="Best of luck Rohan! Keep the momentum going. Discipline in the ABCD library cubicle is half the battle won.", message_type='text')

# Chat 2: Ananya Gupta <--> Pooja Verma (ASO)
req2 = GuidanceRequest.objects.create(
    student=u_ananya,
    alumni=created_alumni[1][1],
    status='accepted',
    message="Hello Pooja Ma'am, need advice on maintaining SSC CGL study continuity during college exam break."
)
session2 = ChatSession.objects.create(request=req2, user_one=u_ananya, user_two=u_pooja, is_active=True)
Message.objects.create(session=session2, sender=u_ananya, content="Hello Pooja Di, I had to put my library seat on hold for 20 days due to college exams. I'm anxious about losing my SSC CGL rhythm. Any advice?", message_type='text')
Message.objects.create(session=session2, sender=u_pooja, content="Hi Ananya! Don't worry at all. During semester exams, dedicate just 90 minutes daily strictly to English Vocab and 1 Quant sectional quiz. Here is a 3-week micro roadmap.", message_type='text')
Message.objects.create(session=session2, sender=u_pooja, content="Follow this revision routine so Tier 2 concepts remain fresh in your mind.", message_type='document', file=roadmap_pdf, file_name="SSC_CGL_Revision_Roadmap_3Weeks.pdf")
Message.objects.create(session=session2, sender=u_ananya, content="This roadmap is so well-structured Di! It takes off all the anxiety. Thank you!", message_type='text')

# Chat 3: Aditya Saxena <--> Gaurav Patidar (Sub-Inspector)
req3 = GuidanceRequest.objects.create(
    student=u_aditya,
    alumni=created_alumni[2][1],
    status='accepted',
    message="Gaurav Sir, seeking guidance on balancing daily 800m running practice with library shift study hours."
)
session3 = ChatSession.objects.create(request=req3, user_one=u_aditya, user_two=u_gaurav, is_active=True)
Message.objects.create(session=session3, sender=u_aditya, content="Jai Hind Gaurav Sir! How did you manage physical fitness endurance along with long evening library study hours?", message_type='text')
Message.objects.create(session=session3, sender=u_gaurav, content="Jai Hind Aditya! Finish your physical running training early morning by 7:00 AM, take a refreshing shower and protein breakfast, and then use your evening shift in ABCD Library with full energy.", message_type='text')

# Study Group 1: MPPSC 2026 Target Champions
group1 = GroupChatSession.objects.create(
    name="ABCD MPPSC 2026 Target Champions",
    description="Official peer guidance, daily question prompts and answer review forum for MPPSC aspirants at ABCD Smart Campus.",
    created_by=u_aayush,
    is_active=True
)
group1.members.add(u_aayush, created_alumni[4][0], u_rohan, u_kartik, u_sneha)

GroupMessage.objects.create(group=group1, sender=u_aayush, content="Welcome champions to the ABCD MPPSC 2026 peer group! Daily answer writing prompts will be uploaded here every morning.", message_type='text')
GroupMessage.objects.create(group=group1, sender=u_rohan, content="Thank you Aayush Sir! Ready for today's topic on MP Local Governance.", message_type='text')
GroupMessage.objects.create(group=group1, sender=u_sneha, content="Submitted today's 5-marker response on the faculty evaluation desk.", message_type='text')
GroupMessage.objects.create(group=group1, sender=created_alumni[4][0], content="Keep your 5-markers under 50 words with crisp point-wise presentation.", message_type='text')

# Study Group 2: ABCD Library Reading Room Community
group2 = GroupChatSession.objects.create(
    name="ABCD Library Reading Room Community",
    description="Aspirants community for daily study goals, motivation, book exchanges and campus announcements.",
    created_by=teacher_user,
    is_active=True
)
for u_item, _, _ in created_alumni:
    group2.members.add(u_item)
group2.members.add(u_rohan, u_ananya, u_aditya, u_siddharth, u_manish, u_priya, u_devansh, u_ritika, u_kartik, u_sneha, u_amit)

GroupMessage.objects.create(group=group2, sender=teacher_user, content="Notice: Sunday All-MP Open Mock Test will start at 10:00 AM sharp in Ground Floor & 1st Floor reading halls.", message_type='text')
GroupMessage.objects.create(group=group2, sender=u_rohan, content="Will offline OMR sheets be provided on desks?", message_type='text')
GroupMessage.objects.create(group=group2, sender=teacher_user, content="Yes, official printed OMR sheets and question booklets will be provided.", message_type='text')

print(" -> Created Guidy 1-on-1 mentor sessions, roadmaps, PDF attachments, and 2 active study groups.")

# -------------------------------------------------------------------
# 9. COMPLAINTS & GRIEVANCE REDRESSAL (PUBLIC & STUDENT)
# -------------------------------------------------------------------
print("\n[Phase 9] Filing Grievance Records (Public Resolved & Live Statuses)...")

# 1. Resolved with 5 stars -> Appears on /resolved-complaints/
c1 = Complaint.objects.create(
    student=prof_rohan,
    role='student',
    subject='wifi',
    message="5GHz Wi-Fi signal in Ground Floor reading bay near Seat 12 experienced occasional packet loss during live HD lectures.",
    status='resolved',
    rating=5,
    feedback="Technical team installed an additional dual-band Wi-Fi mesh repeater near the bay within 2 hours. Signal strength is now 100% full!",
    resolved_at=NOW - datetime.timedelta(days=2)
)

# 2. Resolved with 5 stars -> Appears on /resolved-complaints/
c2 = Complaint.objects.create(
    student=prof_sneha,
    role='student',
    subject='water',
    message="Water cooler unit on 1st Floor required fresh RO filtration cartridge replacement and temperature calibration.",
    status='resolved',
    rating=5,
    feedback="New multi-stage RO UV purification kit installed immediately. Clean chilled water readily available.",
    resolved_at=NOW - datetime.timedelta(days=4)
)

# 3. Resolved with 4 stars -> Appears on /resolved-complaints/
c3 = Complaint.objects.create(
    student=prof_aditya,
    role='student',
    subject='cleaning',
    message="Dust accumulation on acoustic cubicle partitions on Ground Floor shift section.",
    status='resolved',
    rating=4,
    feedback="Housekeeping team performed thorough vacuum sanitization of all cubicles and chairs.",
    resolved_at=NOW - datetime.timedelta(days=7)
)

# 4. Resolved with 5 stars -> Appears on /resolved-complaints/
c4 = Complaint.objects.create(
    student=prof_ananya,
    role='student',
    subject='lost_found',
    message="Misplaced my blue Parker pen and spiral current affairs notes on Desk 15 yesterday evening.",
    status='resolved',
    rating=5,
    feedback="Librarian safely logged the notebook into the front office lost & found locker. Collected intact with thanks!",
    resolved_at=NOW - datetime.timedelta(days=3)
)

# 5. In-Progress Complaint
c5 = Complaint.objects.create(
    student=prof_siddharth,
    role='student',
    subject='noise',
    message="Corridor door closer tension requires minor hydraulic adjustment to prevent slamming during peak entry hours.",
    status='in_progress'
)

# 6. New Complaint
c6 = Complaint.objects.create(
    student=prof_manish,
    role='student',
    subject='washroom',
    message="Requesting replenishment of automatic liquid soap dispensers in Ground Floor washroom.",
    status='new'
)
print(" -> Registered 6 realistic complaints (4 Public Resolved with 5-star ratings, 1 In-Progress, 1 New).")

# -------------------------------------------------------------------
# 10. IN-APP BROADCASTS & NOTIFICATIONS
# -------------------------------------------------------------------
print("\n[Phase 10] Dispatching In-App Broadcasts & Personalized Notifications...")

b1 = BroadcastMessage.objects.create(
    sender=teacher_user,
    subject="Diwali Library Timings & Special All-Night Study Hall Access",
    message="Dear ABCDians, During the upcoming festive week, Ground Floor & 1st Floor library reading halls will remain open from 7:00 AM to 11:00 PM with uninterrupted power backup and high-speed Wi-Fi.",
    target_group="everyone",
    message_type="in_app",
    banner_image=banner_img,
    status="sent",
    send_at=NOW
)

b2 = BroadcastMessage.objects.create(
    sender=teacher_user,
    subject="Mega MPPSC & UPSC Prelims All-MP Open Mock Test (Offline & Online)",
    message="All admitted students and alumni mentors are invited to participate in the All-MP Open Mock Test this Sunday at 10:00 AM. Free OMR evaluation and video analysis will be published on the Course Hub.",
    target_group="everyone",
    message_type="in_app",
    status="sent",
    send_at=NOW
)

# In-app notifications for Rohan Mehta
Notification.objects.create(user=u_rohan, title="Task Reminder", message="Evening GS Mock Test Discussion starts at 06:30 PM.", category="todo", link="/todo/")
Notification.objects.create(user=u_rohan, title="New Study Material", message="Indus Valley & Vedic Period Notes added to MPPSC GS Paper 1.", category="course", link=f"/courses/{created_courses[0].id}/")
Notification.objects.create(user=u_rohan, title="Guidy Mentorship", message="Aayush Sharma (Deputy Collector) sent you an answer structure flowchart.", category="guidy", link="/guidy/")
Notification.objects.create(user=u_rohan, title="Fee Receipt Recorded", message=f"Official Receipt {t1.receipt_number} for ₹1,500 has been issued.", category="fee", link="/student/fees/")
Notification.objects.create(user=u_rohan, title="Seat Reservation Active", message="Ground Floor Seat 12 reservation is confirmed.", category="library", link="/my-seat/")

# In-app notifications for Sneha Patel
Notification.objects.create(user=u_sneha, title="Fee Overdue Alert", message="Your Library Fee expired 3 days ago. Please renew to keep Seat 5 reserved.", category="fee", link="/student/fees/")
Notification.objects.create(user=u_sneha, title="Course Enrolled", message="You have full access to English Grammar Mastery by Sandeep Sir.", category="course", link=f"/courses/{created_courses[1].id}/")

# In-app notifications for Alumni (Aayush Sharma)
Notification.objects.create(user=u_aayush, title="Guidance Request", message="Rohan Mehta sent you a mentorship question on MPPSC Paper 2.", category="guidy", link="/guidy/")
Notification.objects.create(user=u_aayush, title="Hall of Fame Verified", message="Your Deputy Collector achievement has been verified and featured.", category="general", link="/hall-of-fame/")

print(" -> Dispatched In-App Broadcasts and context-aware notifications.")

# -------------------------------------------------------------------
# 11. LIVE NOTIFICATIONS (EMAIL TO vd19055@gmail.com & WHATSAPP TO 7974154551)
# -------------------------------------------------------------------
print("\n[Phase 11] Dispatching Live Emails & WhatsApp notifications to user...")

# 1. Send live email to vd19055@gmail.com
try:
    email_res = send_html_email(
        subject="Official Fee Receipt — ABCD Smart Campus (Receipt No: " + str(t1.receipt_number) + ")",
        recipient_list=["vd19055@gmail.com"],
        template_name="emails/student_fee_receipt.html",
        context={
            "student": prof_rohan,
            "transaction": t1,
            "total_amount": 1500,
            "receipt_number": t1.receipt_number,
            "date_paid": TODAY.strftime("%d %B %Y"),
            "expiry_date": (TODAY + datetime.timedelta(days=32)).strftime("%d %B %Y"),
            "site_url": getattr(settings, 'SITE_URL', 'https://abcdcampus.in'),
            "year": TODAY.year
        }
    )
    print(" -> Live Email sent to vd19055@gmail.com:", "SUCCESS" if email_res else "ATTEMPTED (Check logs)")
except Exception as e:
    print(" -> Live Email exception:", e)

# 2. Send live WhatsApp messages to 7974154551
try:
    import urllib.request, json
    wa_token = getattr(settings, 'WHATSAPP_API_TOKEN', '')
    wa_phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '')
    if wa_token and wa_phone_id:
        wa_url = f"https://graph.facebook.com/v19.0/{wa_phone_id}/messages"
        headers = {
            'Authorization': f'Bearer {wa_token}',
            'Content-Type': 'application/json'
        }
        # Official Meta Template hold warning
        wa_payload_template = {
            "messaging_product": "whatsapp",
            "to": "917974154551",
            "type": "template",
            "template": {
                "name": "hold_warning_3day_student",
                "language": {"code": "en_US"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            {"type": "text", "text": "Rohan Mehta"},
                            {"type": "text", "text": "Ground Floor Library Seat 12 (Full Day)"},
                            {"type": "text", "text": "9827662450"}
                        ]
                    }
                ]
            }
        }
        req = urllib.request.Request(wa_url, data=json.dumps(wa_payload_template).encode('utf-8'), headers=headers)
        try:
            with urllib.request.urlopen(req) as resp:
                print(" -> Live WhatsApp Template sent to 917974154551: SUCCESS")
        except urllib.error.HTTPError as err:
            print(f" -> WhatsApp Template notice ({err.code}): {err.read().decode()[:150]}")

        # Live Freeform fee payment confirmation (within 24h conversation window)
        wa_msg = (
            f"🧾 *ABCD SMART CAMPUS — PAYMENT CONFIRMATION*\n\n"
            f"Dear *Rohan Mehta*,\n"
            f"Your fee payment of *₹1,500* has been recorded successfully at ABCD Coaching & Library.\n\n"
            f"• *Receipt No:* {t1.receipt_number}\n"
            f"• *Seat:* Ground Floor, Seat 12 (Full Day)\n"
            f"• *Valid Until:* {(TODAY + datetime.timedelta(days=32)).strftime('%d %B %Y')}\n\n"
            f"Best regards,\n*Accounts Team | ABCD Smart Campus*"
        )
        wa_payload_text = {
            "messaging_product": "whatsapp",
            "to": "917974154551",
            "type": "text",
            "text": {"body": wa_msg}
        }
        req2 = urllib.request.Request(wa_url, data=json.dumps(wa_payload_text).encode('utf-8'), headers=headers)
        try:
            with urllib.request.urlopen(req2) as resp:
                print(" -> Live WhatsApp Payment message sent to 917974154551: SUCCESS")
        except urllib.error.HTTPError as err:
            print(f" -> WhatsApp Freeform notice ({err.code}): {err.read().decode()[:150]}")
except Exception as e:
    print(" -> WhatsApp dispatch exception:", e)

print("\n" + "=" * 60)
print("SEEDING COMPLETED SUCCESSFULLY!")
print("=" * 60)
