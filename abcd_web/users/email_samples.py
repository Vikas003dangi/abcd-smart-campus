# users/email_samples.py
"""
Sample data catalog and gallery generator for all 27 ABCD Smart Campus email templates.
Used for delivery testing, template validation, and visual regression inspection.
"""

from datetime import datetime
from django.conf import settings
from django.template.loader import render_to_string


class DummyUser:
    email = "vd1905@gmail.com"


class DummySeat:
    seat_number = "42"
    floor = "1"

    def get_floor_display(self):
        return "1st Floor (Quiet Study Zone)"


class DummyStudent:
    full_name = "Vikas Dangi"
    first_name = "Vikas"
    mobile_number = "9876543210"
    service_type = "Library (Reserved Seat) + Coaching"
    user = DummyUser()

    def get_service_type_display(self):
        return "Library (Reserved Seat #42) + Coaching"


class DummyCourse:
    title = "UPSC GS Foundation & Current Affairs 2026"


def get_illustration_name(template: str, subject: str) -> str:
    """Matches the exact illustration selection logic in email_service.py."""
    t = (template or "").lower()
    s = (subject or "").lower()
    if any(k in t or k in s for k in ['birthday']):
        return 'birthday.png'
    if any(k in t or k in s for k in ['grace']):
        return 'hold_grace.png'
    if any(k in t or k in s for k in ['learning']):
        return 'learning_reminder.png'
    if any(k in t or k in s for k in ['due', 'reminder']) and any(k in t or k in s for k in ['fee', 'payment']):
        return 'fee_due.png'
    if any(k in t or k in s for k in ['fee', 'receipt', 'payment', 'paid']):
        return 'payment.png'
    if any(k in t or k in s for k in ['complaint']):
        return 'complaint.png'
    if any(k in t or k in s for k in ['course', 'coaching', 'material']):
        return 'course.png'
    if any(k in t or k in s for k in ['achievement']):
        return 'achievement.png'
    if any(k in t or k in s for k in ['guidy', 'guidance']):
        return 'guidance.png'
    if any(k in t or k in s for k in ['expired', 'expire']):
        return 'time_expired.png'
    if any(k in t or k in s for k in ['broadcast', 'announcement']):
        return 'announcement.png'
    if any(k in t or k in s for k in ['otp', 'security', 'verify']):
        return 'security.png'
    if any(k in t or k in s for k in ['approval', 'approved', 'admitted', 'alumni']):
        return 'approval.png'
    if any(k in t or k in s for k in ['seat', 'hold', 'allotment']):
        return 'seat.png'
    if any(k in t or k in s for k in ['reminder', 'todo', 'visitor']):
        return 'reminder.png'
    return 'welcome.png'


def get_all_sample_emails(site_url: str = None) -> list:
    """Returns the full catalog of all 27 email templates with realistic mock contexts."""
    if not site_url:
        site_url = getattr(settings, 'SITE_URL', 'https://abcdcampus.in').rstrip('/')

    student = DummyStudent()
    seat = DummySeat()
    course = DummyCourse()

    catalog = [
        # --- ADMISSIONS ---
        {
            'id': 'admission_approved',
            'name': 'Admission Approved',
            'category': 'Admissions',
            'subject': 'Welcome to ABCD! Your Admission is Approved',
            'template': 'emails/admission_approved.html',
            'preview_text': 'Congratulations! Your admission at ABCD Coaching & Library has been successfully approved.',
            'context': {
                'student': student,
                'seat': seat,
                'preview_text': 'Congratulations! Your admission at ABCD Coaching & Library has been successfully approved.',
                'dashboard_url': f'{site_url}/dashboard/',
                'site_url': site_url,
            }
        },
        {
            'id': 'welcome_email',
            'name': 'Welcome Account Confirmation',
            'category': 'Admissions',
            'subject': 'Welcome to ABCD Coaching & Library!',
            'template': 'emails/welcome_email.html',
            'preview_text': 'Welcome to ABCD Coaching & Library! Your account is active and ready to use.',
            'context': {
                'username': 'Vikas Dangi',
                'login_url': f'{site_url}/login/',
                'preview_text': 'Welcome to ABCD Coaching & Library! Your account is active and ready to use.',
                'site_url': site_url,
            }
        },
        {
            'id': 'admin_coaching_request',
            'name': 'New Coaching Application (Staff Alert)',
            'category': 'Admissions',
            'subject': 'New Coaching Admission Submission: Vikas Dangi',
            'template': 'emails/admin_coaching_request.html',
            'preview_text': 'A student has submitted a new coaching admission form for review and approval.',
            'context': {
                'student': student,
                'batch': 'UPSC GS Foundation Morning Batch (8:00 AM - 12:00 PM)',
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'A student has submitted a new coaching admission form for review and approval.',
                'site_url': site_url,
            }
        },
        {
            'id': 'admin_library_request',
            'name': 'New Library Seat Application (Staff Alert)',
            'category': 'Admissions',
            'subject': 'New Library Admission Request: Vikas Dangi',
            'template': 'emails/admin_library_request.html',
            'preview_text': 'New library seat reservation request received for Seat #42.',
            'context': {
                'student': student,
                'seat': seat,
                'shift': 'Full Day (6:00 AM - 10:00 PM)',
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'New library seat reservation request received for Seat #42.',
                'site_url': site_url,
            }
        },

        # --- FEES & BILLING ---
        {
            'id': 'student_fee_receipt',
            'name': 'Fee Payment Receipt (Student)',
            'category': 'Fees & Billing',
            'subject': 'Fee Receipt: ABCD Campus #REC-2026-1042',
            'template': 'emails/student_fee_receipt.html',
            'preview_text': 'Your fee payment for Library Reserved Seat 42 has been received successfully. Your receipt is inside.',
            'context': {
                'student_name': 'Vikas Dangi',
                'service_details': 'Library Reserved Seat #42 (October 2026)',
                'student_dash_path': '/dashboard/',
                'preview_text': 'Your fee payment for Library Reserved Seat 42 has been received successfully. Your receipt is inside.',
                'site_url': site_url,
            }
        },
        {
            'id': 'teacher_fee_receipt_alert',
            'name': 'Fee Collection Alert (Staff Alert)',
            'category': 'Fees & Billing',
            'subject': 'Fee Collected: Vikas Dangi - INR 1,500',
            'template': 'emails/teacher_fee_receipt_alert.html',
            'preview_text': 'A new student fee payment of INR 1,500 has been recorded for Vikas Dangi.',
            'context': {
                'student_name': 'Vikas Dangi',
                'service_details': 'Library Reserved Seat #42 - Amount: INR 1,500',
                'teacher_dash_path': '/dashboard/',
                'preview_text': 'A new student fee payment of INR 1,500 has been recorded for Vikas Dangi.',
                'site_url': site_url,
            }
        },
        {
            'id': 'fee_notification',
            'name': 'Fee Due Reminder',
            'category': 'Fees & Billing',
            'subject': 'Urgent: Pending Fee Reminder - October 2026',
            'template': 'emails/fee_notification.html',
            'preview_text': 'Friendly reminder: your fee for October 2026 (Library Seat #42) is due in 3 days.',
            'context': {
                'title': 'Fee Payment Due Reminder',
                'student': student,
                'teacher_name': 'Sandeep Sir',
                'months_text': 'October 2026',
                'year': '2026-2027',
                'date': '05 Oct 2026',
                'service_details': 'Library Reserved Seat #42 + Self Study Zone',
                'total_amount': 'INR 1,500',
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'Friendly reminder: your fee for October 2026 (Library Seat #42) is due in 3 days.',
                'site_url': site_url,
            }
        },

        # --- SEATS & LIBRARY ---
        {
            'id': 'seat_update',
            'name': 'Seat / Shift Switch Approved',
            'category': 'Seats & Library',
            'subject': 'Your Seat / Shift Switch Request is Approved',
            'template': 'emails/seat_update.html',
            'preview_text': 'Your seat / shift switch request has been approved. Your updated details are inside.',
            'context': {
                'title': 'Seat / Shift Switch Approved',
                'student': student,
                'seat': seat,
                'shift': 'Morning Shift (6:00 AM - 12:00 PM)',
                'hold_period': 'N/A',
                'custom_text': 'Your request to transfer to Seat #42 (Morning Shift) has been approved and is effective immediately.',
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'Your seat / shift switch request has been approved. Your updated details are inside.',
                'site_url': site_url,
            }
        },
        {
            'id': 'admin_seat_hold_request',
            'name': 'Seat Hold Request (Staff Alert)',
            'category': 'Seats & Library',
            'subject': 'New Seat Hold Request: Vikas Dangi (Seat 42)',
            'template': 'emails/admin_seat_hold_request.html',
            'preview_text': 'Vikas Dangi has submitted a 15-day seat hold request on Seat #42.',
            'context': {
                'student': student,
                'seat': seat,
                'duration': '15 Days',
                'start_date': '05 Oct 2026',
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'Vikas Dangi has submitted a 15-day seat hold request on Seat #42.',
                'site_url': site_url,
            }
        },
        {
            'id': 'admin_temp_seat_request',
            'name': 'Temporary Seat Request (Staff Alert)',
            'category': 'Seats & Library',
            'subject': 'Temporary Seat Request: Vikas Dangi',
            'template': 'emails/admin_temp_seat_request.html',
            'preview_text': 'Temporary seat allocation requested for Seat #42 for Vikas Dangi.',
            'context': {
                'student': student,
                'seat_number': '42',
                'floor': '1st Floor',
                'shift': 'Full Day (6:00 AM - 10:00 PM)',
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'Temporary seat allocation requested for Seat #42 for Vikas Dangi.',
                'site_url': site_url,
            }
        },
        {
            'id': 'hold_grace_warning',
            'name': 'Seat Hold Grace Warning (Student)',
            'category': 'Seats & Library',
            'subject': 'URGENT: Your Seat Hold Ends Today - 3 Days Grace Period',
            'template': 'emails/hold_grace_warning.html',
            'preview_text': 'URGENT: Your seat hold on Seat 42 ends today. 3-day grace period has started.',
            'context': {
                'title': 'Seat Hold Ending Today',
                'student': student,
                'seat_details': 'Seat 42 (1st Floor Quiet Zone)',
                'hold_end_date': '03 Oct 2026',
                'teacher_phone': '9876543210',
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'URGENT: Your seat hold on Seat 42 ends today. 3-day grace period has started.',
                'site_url': site_url,
            }
        },
        {
            'id': 'hold_grace_teacher',
            'name': 'Seat Hold Grace Notice (Staff Alert)',
            'category': 'Seats & Library',
            'subject': 'Hold Notice: Vikas Dangi Seat Hold Grace Period',
            'template': 'emails/hold_grace_teacher.html',
            'preview_text': 'Vikas Dangi has entered the 3-day hold grace period for Seat 42.',
            'context': {
                'title': 'Student Entered Seat Hold Grace Period',
                'student': student,
                'seat_details': 'Seat 42 (1st Floor Quiet Zone)',
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'Vikas Dangi has entered the 3-day hold grace period for Seat 42.',
                'site_url': site_url,
            }
        },
        {
            'id': 'seat_hold_expired_student',
            'name': 'Seat Hold Expired (Student Notice)',
            'category': 'Seats & Library',
            'subject': 'Your Seat Hold Has Expired: Seat #42',
            'template': 'emails/seat_hold_expired_student.html',
            'preview_text': 'Your hold grace period on Seat #42 has ended. Seat is released.',
            'context': {
                'student': student,
                'seat': seat,
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'Your hold grace period on Seat #42 has ended. Seat is released.',
                'site_url': site_url,
            }
        },
        {
            'id': 'seat_hold_expired_teacher',
            'name': 'Seat Hold Expired (Staff Action Alert)',
            'category': 'Seats & Library',
            'subject': 'Seat Hold Expired - Action Required: Vikas Dangi',
            'template': 'emails/seat_hold_expired_teacher.html',
            'preview_text': 'Hold expired for Vikas Dangi on Seat #42. Ready for reassignment.',
            'context': {
                'student': student,
                'seat': seat,
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'Hold expired for Vikas Dangi on Seat #42. Ready for reassignment.',
                'site_url': site_url,
            }
        },

        # --- SECURITY & AUTH ---
        {
            'id': 'otp_register',
            'name': 'Registration Verification OTP',
            'category': 'Security & Auth',
            'subject': 'Verify your email for ABCD registration',
            'template': 'emails/otp_register.html',
            'preview_text': 'Your ABCD registration verification code is 482910. Valid for 10 minutes.',
            'context': {
                'username': 'Vikas Dangi',
                'otp': '482910',
                'login_url': f'{site_url}/register/',
                'preview_text': 'Your ABCD registration verification code is 482910. Valid for 10 minutes.',
                'site_url': site_url,
            }
        },
        {
            'id': 'otp_security',
            'name': 'Password Reset OTP',
            'category': 'Security & Auth',
            'subject': 'Your ABCD password reset OTP',
            'template': 'emails/otp_security.html',
            'preview_text': 'Your password reset verification code is 839201. Valid for 10 minutes.',
            'context': {
                'username': 'Vikas Dangi',
                'otp': '839201',
                'login_url': f'{site_url}/login/',
                'preview_text': 'Your password reset verification code is 839201. Valid for 10 minutes.',
                'site_url': site_url,
            }
        },

        # --- ANNOUNCEMENTS ---
        {
            'id': 'broadcast_email',
            'name': 'Campus Broadcast Announcement',
            'category': 'Announcements',
            'subject': 'Important Announcement: Extended Library Timings & Test Series',
            'template': 'emails/broadcast_email.html',
            'preview_text': 'Library reading hours extended until 11:00 PM starting Monday. Mock test schedule inside.',
            'context': {
                'subject': 'Important Announcement: Extended Library Timings & Test Series',
                'message': 'Dear Students,\n\nWe are pleased to announce that library reading hours are extended until 11:00 PM starting Monday for the upcoming competitive exams. Full-length mock test papers are now uploaded to your dashboard.\n\nKeep pushing forward!\nTeam ABCD',
                'teacher_name': 'Sandeep Sir (Director)',
                'banner_image_url': '',
                'attachment_links': [{'name': 'October_Mock_Schedule.pdf', 'url': f'{site_url}/static/docs/schedule.pdf'}],
                'action_buttons': [{'label': 'View Test Schedule', 'url': f'{site_url}/dashboard/'}],
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'Library reading hours extended until 11:00 PM starting Monday. Mock test schedule inside.',
                'site_url': site_url,
            }
        },

        # --- CELEBRATORY ---
        {
            'id': 'birthday_wish_email',
            'name': 'Student Birthday Wish',
            'category': 'Celebratory',
            'subject': 'Happy Birthday from Team ABCD, Vikas Dangi!',
            'template': 'emails/birthday_wish_email.html',
            'preview_text': 'Happy Birthday, Vikas Dangi! Warmest wishes from the entire ABCD family!',
            'context': {
                'student': student,
                'dashboard_url': f'{site_url}/dashboard/',
                'preview_text': 'Happy Birthday, Vikas Dangi! Warmest wishes from the entire ABCD family!',
                'site_url': site_url,
            }
        },

        # --- ACADEMIC ---
        {
            'id': 'course_update',
            'name': 'Course Content / Material Update',
            'category': 'Academic',
            'subject': 'New Course Material Published: UPSC GS Foundation',
            'template': 'emails/course_update.html',
            'preview_text': 'New study notes and reference materials are now uploaded to your course portal.',
            'context': {
                'title': 'New Course Material Published',
                'course_name': 'UPSC GS Foundation 2026',
                'message': 'Comprehensive study notes and practice questions for Modern Indian History (Module 4) are now available on your portal.',
                'action_url': f'{site_url}/dashboard/',
                'preview_text': 'New study notes and reference materials are now uploaded to your course portal.',
                'site_url': site_url,
            }
        },
        {
            'id': 'learning_reminder_email',
            'name': 'Daily Study Reminder',
            'category': 'Academic',
            'subject': 'Study Reminder: UPSC GS Foundation 2026',
            'template': 'emails/learning_reminder_email.html',
            'preview_text': 'Stay consistent with your daily study goals for UPSC GS Foundation 2026.',
            'context': {
                'title': 'Daily Study Reminder',
                'course': course,
                'course_url': f'{site_url}/dashboard/',
                'preview_text': 'Stay consistent with your daily study goals for UPSC GS Foundation 2026.',
                'site_url': site_url,
            }
        },

        # --- GRIEVANCES ---
        {
            'id': 'admin_complaint_raised',
            'name': 'New Complaint Raised (Staff Alert)',
            'category': 'Grievances',
            'subject': 'New Student Complaint: AC Cooling in Quiet Study Hall',
            'template': 'emails/admin_complaint_raised.html',
            'preview_text': 'New grievance submitted by Vikas Dangi regarding AC Cooling.',
            'context': {
                'sender_name': 'Vikas Dangi',
                'role': 'Student',
                'complaint_code': 'CMP-8291',
                'complaint_subject': 'AC Cooling in 1st Floor Quiet Hall',
                'raised_at': datetime.now(),
                'message': 'The AC unit on the north wall is running colder than usual. Request adjusting thermostat to 24C.',
                'action_url': f'{site_url}/dashboard/',
                'preview_text': 'New grievance submitted by Vikas Dangi regarding AC Cooling.',
                'site_url': site_url,
            }
        },
        {
            'id': 'complaint_status_update',
            'name': 'Complaint Status Updated (Student)',
            'category': 'Grievances',
            'subject': 'Complaint Status Updated: CMP-8291',
            'template': 'emails/complaint_status_update.html',
            'preview_text': 'Your complaint CMP-8291 has been marked as Resolved.',
            'context': {
                'student_name': 'Vikas Dangi',
                'complaint_code': 'CMP-8291',
                'complaint_subject': 'AC Cooling in 1st Floor Quiet Hall',
                'status_text': 'Resolved - Thermostat calibrated to 24C and deflectors installed',
                'action_url': f'{site_url}/dashboard/',
                'preview_text': 'Your complaint CMP-8291 has been marked as Resolved.',
                'site_url': site_url,
            }
        },

        # --- ALUMNI & MENTORSHIP ---
        {
            'id': 'alumni_approval',
            'name': 'Alumni Profile Approved',
            'category': 'Alumni & Mentorship',
            'subject': 'Congratulations! Your ABCD Alumni Profile is Approved',
            'template': 'emails/alumni_approval.html',
            'preview_text': 'Your ABCD Alumni Hall of Fame profile is now active on the campus portal.',
            'context': {
                'student_name': 'Vikas Dangi',
                'action_url': f'{site_url}/dashboard/',
                'preview_text': 'Your ABCD Alumni Hall of Fame profile is now active on the campus portal.',
                'site_url': site_url,
            }
        },
        {
            'id': 'admin_achievement_request',
            'name': 'New Achievement Request (Staff Alert)',
            'category': 'Alumni & Mentorship',
            'subject': 'New Alumni Achievement Request: Vikas Dangi',
            'template': 'emails/admin_achievement_request.html',
            'preview_text': 'Vikas Dangi has submitted a new achievement request for review.',
            'context': {
                'student_name': 'Vikas Dangi',
                'achievement_summary': 'Cleared UPSC Civil Services Examination 2025 with AIR 42. Verified from Roll No. 0823910.',
                'action_url': f'{site_url}/dashboard/',
                'preview_text': 'Vikas Dangi has submitted a new achievement request for review.',
                'site_url': site_url,
            }
        },
        {
            'id': 'guidy_request',
            'name': 'Guidy Mentorship Request',
            'category': 'Alumni & Mentorship',
            'subject': 'New Guidance Request on Guidy: Vikas Dangi',
            'template': 'emails/guidy_request.html',
            'preview_text': 'Vikas Dangi has sent you a new mentorship question on Guidy.',
            'context': {
                'student_name': 'Vikas Dangi',
                'request_message': 'Hello Sir, I would love some guidance regarding answer writing strategy for GS Paper 2 and time management for working aspirants.',
                'action_url': f'{site_url}/dashboard/',
                'preview_text': 'Vikas Dangi has sent you a new mentorship question on Guidy.',
                'site_url': site_url,
            }
        },

        # --- TO-DO HUB ---
        {
            'id': 'todo_reminder',
            'name': 'To-Do Task / Alarm Due Alert',
            'category': 'To-Do Hub',
            'subject': 'Alarm: Complete Mock Test 3 Analysis',
            'template': 'emails/todo_reminder.html',
            'preview_text': 'Reminder: Complete Mock Test 3 Analysis is due now.',
            'context': {
                'user_name': 'Vikas Dangi',
                'title': 'Complete Mock Test 3 Analysis',
                'note': 'Review incorrect questions in Modern History and revise notes before evening study session.',
                'recurrence': 'None (One-time)',
                'todo_url': f'{site_url}/dashboard/',
                'preview_text': 'Reminder: Complete Mock Test 3 Analysis is due now.',
                'site_url': site_url,
            }
        },

        # --- VISITOR CONVERSION ---
        {
            'id': 'visitor_reminder',
            'name': 'Prospective Visitor Follow-Up',
            'category': 'Visitor Conversion',
            'subject': 'Complete Your Enrollment at ABCD Coaching & Library',
            'template': 'emails/visitor_reminder.html',
            'preview_text': 'Your reserved seat is waiting for you at ABCD Coaching & Library.',
            'context': {
                'seat': seat,
                'action_text': 'Complete Your Library Enrollment',
                'action_url': f'{site_url}/register/',
                'preview_text': 'Your reserved seat is waiting for you at ABCD Coaching & Library.',
                'site_url': site_url,
            }
        },
    ]
    return catalog


def render_all_sample_emails(site_url: str = None) -> list:
    """Renders all 27 templates with CDN assets and returns metadata and HTML content."""
    catalog = get_all_sample_emails(site_url)
    cdn_base = "https://cdn.jsdelivr.net/gh/Vikas003dangi/abcd-smart-campus@main/abcd_web/static"

    rendered_items = []
    for item in catalog:
        ctx = dict(item['context'])
        ill_name = get_illustration_name(item['template'], item['subject'])
        ctx['clean_subject'] = item['subject']
        ctx['subject'] = item['subject']
        ctx['logo_url'] = f"{cdn_base}/data/light-logo.png"
        ctx['illustration_url'] = f"{cdn_base}/data/email_illustrations/{ill_name}"
        ctx['preview_text'] = item['preview_text']

        html = render_to_string(item['template'], ctx)
        rendered_items.append({
            'id': item['id'],
            'name': item['name'],
            'category': item['category'],
            'subject': item['subject'],
            'template': item['template'],
            'preview_text': item['preview_text'],
            'illustration': ill_name,
            'html': html,
        })
    return rendered_items


def export_email_preview_gallery(output_path: str = 'B:/ABCD/email_preview_gallery.html', site_url: str = None, recipient: str = 'vd1905@gmail.com') -> str:
    """Exports a self-contained interactive showcase gallery for inspecting all 27 email templates."""
    import json
    from pathlib import Path

    rendered_items = render_all_sample_emails(site_url)
    json_data = json.dumps(rendered_items)

    html_page = f"""<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-900 text-slate-100">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ABCD Smart Campus - Email Showcase & Diagnostic Gallery (27 Templates)</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
  <style>
    body {{ font-family: 'Plus Jakarta Sans', sans-serif; }}
    code, pre {{ font-family: 'JetBrains Mono', monospace; }}
    ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
    ::-webkit-scrollbar-track {{ background: #0f172a; }}
    ::-webkit-scrollbar-thumb {{ background: #334155; border-radius: 3px; }}
    ::-webkit-scrollbar-thumb:hover {{ background: #475569; }}
  </style>
</head>
<body class="h-full flex flex-col overflow-hidden">

  <!-- Top Navigation Header -->
  <header class="bg-slate-950 border-b border-slate-800 px-6 py-3.5 flex items-center justify-between shrink-0 shadow-lg z-20">
    <div class="flex items-center gap-3.5">
      <div class="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-500 via-purple-500 to-pink-500 flex items-center justify-center font-bold text-white shadow-md shadow-indigo-500/20">
        ✉
      </div>
      <div>
        <h1 class="text-base font-bold text-white tracking-tight flex items-center gap-2">
          ABCD Smart Campus
          <span class="px-2 py-0.5 text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-full">27 System Email Templates</span>
        </h1>
        <p class="text-xs text-slate-400">Interactive Email Visualizer & Delivery Inspector for <span class="text-indigo-300 font-mono font-medium">{recipient}</span></p>
      </div>
    </div>

    <!-- Center Viewport Switcher -->
    <div class="flex items-center bg-slate-900 border border-slate-800 rounded-lg p-1 text-xs">
      <button id="btn-desktop" onclick="setView('desktop')" class="px-3 py-1.5 rounded-md font-medium text-white bg-indigo-600 transition flex items-center gap-1.5 shadow-sm">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect width="20" height="14" x="2" y="3" rx="2"/><line x1="8" x2="16" y1="21" y2="21"/><line x1="12" x2="12" y1="17" y2="21"/></svg>
        Desktop (580px)
      </button>
      <button id="btn-mobile" onclick="setView('mobile')" class="px-3 py-1.5 rounded-md font-medium text-slate-400 hover:text-white transition flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/></svg>
        Mobile (375px)
      </button>
      <button id="btn-full" onclick="setView('full')" class="px-3 py-1.5 rounded-md font-medium text-slate-400 hover:text-white transition flex items-center gap-1.5">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" x2="14" y1="3" y2="10"/><line x1="3" x2="10" y1="21" y2="14"/></svg>
        Full Width
      </button>
    </div>

    <!-- Right Controls -->
    <div class="flex items-center gap-3">
      <button onclick="openInNewTab()" class="px-3.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-lg border border-slate-700 transition flex items-center gap-1.5 shadow-sm">
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" x2="21" y1="14" y2="3"/></svg>
        Popout in New Tab
      </button>
    </div>
  </header>

  <!-- Workspace Container -->
  <div class="flex-1 flex overflow-hidden">

    <!-- Left Sidebar: Template Directory -->
    <aside class="w-80 bg-slate-950 border-r border-slate-800 flex flex-col shrink-0 overflow-hidden">
      
      <!-- Search & Category Filters -->
      <div class="p-3.5 border-b border-slate-800 space-y-2.5 bg-slate-950/80 backdrop-blur">
        <div class="relative">
          <input type="text" id="search-input" oninput="filterTemplates()" placeholder="Search templates, subjects, or keys..." 
                 class="w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition">
          <svg class="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"/><line x1="21" x2="16.65" y1="21" y2="16.65"/></svg>
        </div>
        
        <div class="flex items-center gap-1.5 overflow-x-auto pb-1 text-[11px]">
          <button onclick="setCategory('ALL')" class="cat-btn px-2.5 py-1 rounded bg-indigo-600 text-white font-medium whitespace-nowrap" data-cat="ALL">All (27)</button>
          <button onclick="setCategory('Admissions')" class="cat-btn px-2 py-1 rounded bg-slate-900 text-slate-400 hover:text-slate-200 font-medium whitespace-nowrap" data-cat="Admissions">Admissions</button>
          <button onclick="setCategory('Fees & Billing')" class="cat-btn px-2 py-1 rounded bg-slate-900 text-slate-400 hover:text-slate-200 font-medium whitespace-nowrap" data-cat="Fees & Billing">Fees</button>
          <button onclick="setCategory('Seats & Library')" class="cat-btn px-2 py-1 rounded bg-slate-900 text-slate-400 hover:text-slate-200 font-medium whitespace-nowrap" data-cat="Seats & Library">Seats</button>
          <button onclick="setCategory('Security & Auth')" class="cat-btn px-2 py-1 rounded bg-slate-900 text-slate-400 hover:text-slate-200 font-medium whitespace-nowrap" data-cat="Security & Auth">Auth</button>
        </div>
      </div>

      <!-- Template List -->
      <div id="template-list" class="flex-1 overflow-y-auto p-2 space-y-1">
        <!-- Rendered by JS -->
      </div>

      <!-- Footer Info -->
      <div class="p-3 border-t border-slate-800/80 bg-slate-950 text-[11px] text-slate-500 flex justify-between items-center">
        <span>Verified Django 5.2.6 Engine</span>
        <span class="text-emerald-400 font-semibold flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span> 27/27 Ready
        </span>
      </div>
    </aside>

    <!-- Right Main Stage: Header & Live Preview -->
    <main class="flex-1 flex flex-col bg-slate-900 overflow-hidden">
      
      <!-- Email Header Details -->
      <div class="bg-slate-950/60 border-b border-slate-800/80 px-6 py-3 shrink-0 flex flex-col gap-2">
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-2.5 min-w-0">
            <span id="detail-category" class="px-2.5 py-0.5 text-[11px] font-bold uppercase tracking-wider bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-md shrink-0">Category</span>
            <h2 id="detail-name" class="text-sm font-bold text-white truncate">Template Name</h2>
          </div>
          <div class="text-xs text-slate-400 shrink-0 font-mono">
            Template: <span id="detail-template" class="text-slate-300">emails/...</span>
          </div>
        </div>

        <!-- Subject & Recipient -->
        <div class="grid grid-cols-1 md:grid-cols-12 gap-3 text-xs pt-1 border-t border-slate-800/40">
          <div class="md:col-span-8 flex items-baseline gap-2 min-w-0">
            <span class="text-slate-500 font-semibold shrink-0">Subject:</span>
            <span id="detail-subject" class="font-medium text-slate-200 truncate select-all">Subject Line</span>
          </div>
          <div class="md:col-span-4 flex items-baseline gap-2 min-w-0">
            <span class="text-slate-500 font-semibold shrink-0">Recipient:</span>
            <span class="font-mono text-indigo-300 truncate select-all">{recipient}</span>
          </div>
        </div>

        <!-- Preheader Preview -->
        <div class="flex items-center gap-2 text-[11px] bg-slate-900/90 border border-slate-800/80 rounded-md px-3 py-1.5 text-slate-400 min-w-0">
          <span class="text-amber-400 font-bold uppercase tracking-wider text-[10px] shrink-0">📱 Inbox Preview Snippet:</span>
          <span id="detail-preheader" class="italic text-slate-300 truncate select-all">Preview snippet</span>
        </div>
      </div>

      <!-- Live Preview Area -->
      <div id="preview-stage" class="flex-1 bg-slate-900/60 overflow-y-auto flex items-start justify-center p-6">
        <div id="frame-container" class="w-[580px] bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-700/60 transition-all duration-300">
          <iframe id="email-iframe" class="w-full h-[760px] border-0 bg-white block" title="Email Preview"></iframe>
        </div>
      </div>

    </main>

  </div>

  <script>
    const emails = {json_data};
    let currentIndex = 0;
    let currentCategory = 'ALL';
    let currentView = 'desktop';

    function renderList() {{
      const listEl = document.getElementById('template-list');
      const searchVal = document.getElementById('search-input').value.toLowerCase().trim();
      listEl.innerHTML = '';

      const filtered = emails.filter((item) => {{
        const matchesCat = (currentCategory === 'ALL' || item.category === currentCategory);
        const matchesSearch = !searchVal || 
          item.name.toLowerCase().includes(searchVal) ||
          item.subject.toLowerCase().includes(searchVal) ||
          item.template.toLowerCase().includes(searchVal) ||
          item.category.toLowerCase().includes(searchVal);
        return matchesCat && matchesSearch;
      }});

      if (filtered.length === 0) {{
        listEl.innerHTML = '<div class="p-4 text-center text-xs text-slate-500">No matching templates found</div>';
        return;
      }}

      filtered.forEach((item) => {{
        const originalIndex = emails.findIndex(e => e.id === item.id);
        const isSelected = originalIndex === currentIndex;
        
        const card = document.createElement('button');
        card.className = `w-full text-left p-2.5 rounded-lg border transition text-xs flex flex-col gap-1 ${{
          isSelected 
            ? 'bg-indigo-600/20 border-indigo-500/50 text-white shadow-sm ring-1 ring-indigo-500/30' 
            : 'bg-slate-900/40 border-slate-800/80 text-slate-300 hover:bg-slate-800/60 hover:text-white'
        }}`;
        card.onclick = () => selectTemplate(originalIndex);

        card.innerHTML = `
          <div class="flex items-center justify-between gap-1">
            <span class="font-semibold truncate ${{isSelected ? 'text-indigo-300' : 'text-slate-200'}}">${{item.name}}</span>
            <span class="text-[10px] font-mono px-1.5 py-0.2 bg-slate-800 text-slate-400 rounded shrink-0">#${{originalIndex + 1}}</span>
          </div>
          <div class="text-[11px] text-slate-400 truncate">${{item.subject}}</div>
          <div class="flex items-center justify-between text-[10px] text-slate-500 pt-0.5">
            <span class="text-indigo-400/90 font-medium">${{item.category}}</span>
            <span class="font-mono text-slate-500">${{item.illustration}}</span>
          </div>
        `;
        listEl.appendChild(card);
      }});
    }}

    function selectTemplate(index) {{
      currentIndex = index;
      renderList();

      const item = emails[index];
      document.getElementById('detail-name').innerText = `${{index + 1}}. ${{item.name}}`;
      document.getElementById('detail-category').innerText = item.category;
      document.getElementById('detail-template').innerText = item.template;
      document.getElementById('detail-subject').innerText = item.subject;
      document.getElementById('detail-preheader').innerText = `"${{item.preview_text}}"`;

      const iframe = document.getElementById('email-iframe');
      const doc = iframe.contentWindow.document;
      doc.open();
      doc.write(item.html);
      doc.close();

      setTimeout(() => {{
        try {{
          const bodyHeight = iframe.contentWindow.document.body.scrollHeight;
          if (bodyHeight > 300) {{
            iframe.style.height = (bodyHeight + 40) + 'px';
          }}
        }} catch(e) {{}}
      }}, 100);
    }}

    function setView(view) {{
      currentView = view;
      const container = document.getElementById('frame-container');
      const btnDesk = document.getElementById('btn-desktop');
      const btnMob = document.getElementById('btn-mobile');
      const btnFull = document.getElementById('btn-full');

      [btnDesk, btnMob, btnFull].forEach(b => {{
        b.className = b.className.replace('bg-indigo-600 text-white', 'text-slate-400 hover:text-white');
      }});

      if (view === 'desktop') {{
        container.className = 'w-[580px] bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-700/60 transition-all duration-300';
        btnDesk.className = btnDesk.className.replace('text-slate-400 hover:text-white', 'bg-indigo-600 text-white');
      }} else if (view === 'mobile') {{
        container.className = 'w-[375px] bg-white rounded-2xl shadow-2xl overflow-hidden border-4 border-slate-700 transition-all duration-300';
        btnMob.className = btnMob.className.replace('text-slate-400 hover:text-white', 'bg-indigo-600 text-white');
      }} else {{
        container.className = 'w-full max-w-4xl bg-white rounded-2xl shadow-2xl overflow-hidden border border-slate-700/60 transition-all duration-300';
        btnFull.className = btnFull.className.replace('text-slate-400 hover:text-white', 'bg-indigo-600 text-white');
      }}
    }}

    function setCategory(cat) {{
      currentCategory = cat;
      document.querySelectorAll('.cat-btn').forEach(btn => {{
        if (btn.getAttribute('data-cat') === cat) {{
          btn.className = 'cat-btn px-2.5 py-1 rounded bg-indigo-600 text-white font-medium whitespace-nowrap';
        }} else {{
          btn.className = 'cat-btn px-2 py-1 rounded bg-slate-900 text-slate-400 hover:text-slate-200 font-medium whitespace-nowrap';
        }}
      }});
      renderList();
    }}

    function filterTemplates() {{
      renderList();
    }}

    function openInNewTab() {{
      const item = emails[currentIndex];
      const win = window.open('', '_blank');
      win.document.write(item.html);
      win.document.close();
    }}

    window.addEventListener('keydown', (e) => {{
      if (e.target.tagName === 'INPUT') return;
      if (e.key === 'ArrowDown') {{
        e.preventDefault();
        if (currentIndex < emails.length - 1) selectTemplate(currentIndex + 1);
      }} else if (e.key === 'ArrowUp') {{
        e.preventDefault();
        if (currentIndex > 0) selectTemplate(currentIndex - 1);
      }}
    }});

    renderList();
    selectTemplate(0);
  </script>
</body>
</html>"""

    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(html_page, encoding='utf-8')
    return str(dest.resolve())

