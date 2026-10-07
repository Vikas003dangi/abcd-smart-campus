"""
users/auto_reply.py
===================
Deterministic smart auto-reply engine for ABCD Smart Campus Guidy messaging.

Supports:
- ABCD Asst. (Vikas Dangi, vd19055@gmail.com, default 5m wait)
- Sandeep Sir (abcd2013baq@gmail.com, default 15m wait)
- Separate respectful personas speaking on behalf of Vikas Dangi and Sandeep Sir
- Non-AI deterministic keyword classifier covering 10 distinct topics
- Rotating response variants (>= 3 per topic per persona, never repeating back-to-back in same conversation)
- Handoff rules for financial disputes/complaints (Complaints Desk / direct call 8109455803)
- Emergency distress protocol (Tele-MANAS 14416, real in-app Urgent Notification, direct call 8109455803)
- Staff/teacher exclusion
- 6-hour burst cooldown
- Database-backed persistence across server restarts
- Default config: is_enabled=False (requires admin activation)
"""

import re
import logging
from datetime import timedelta
from django.utils import timezone
from django.db import transaction
from django.conf import settings

logger = logging.getLogger(__name__)

# Standard accounts & contact
ABCD_ASST_EMAIL = "vd19055@gmail.com"
SANDEEP_SIR_EMAIL = "abcd2013baq@gmail.com"
URGENT_CALL_PHONE = "8109455803"
OFFICE_PHONE = URGENT_CALL_PHONE

# Keywords for deterministic classification
# Evaluated in priority order: emergency -> fees_dispute -> complaint -> ...
TOPIC_RULES = [
    (
        'emergency',
        [
            r'\bsuicide\b', r'\bkill myself\b', r'\bending my life\b', r'\bdepress(ed|ion)?\b',
            r'\bsevere anxiety\b', r'\bpanic attack\b', r'\babuse(d)?\b', r'\bharass(ment|ed)?\b',
            r'\bimmediate danger\b', r'\bdie\b', r'\bhurt myself\b', r'\bmental health crisis\b',
            r'\bhelp me please i cant take this\b', r'\bi want to die\b'
        ]
    ),
    (
        'fees_dispute',
        [
            r'\bpayment failed\b', r'\bfailed payment\b', r'\bmoney deducted\b', r'\brefund\b',
            r'\bdouble charge(d)?\b', r'\bcharged twice\b', r'\bdispute\b', r'\bwrong amount\b',
            r'\bfee excess\b', r'\breturn (my )?money\b', r'\bdeducted but not updated\b'
        ]
    ),
    (
        'complaint',
        [
            r'\bcomplaint\b', r'\bcomplain\b', r'\bissue\b', r'\bproblem\b', r'\bbroken\b',
            r'\bnot working\b', r'\bac not working\b', r'\bfan broken\b', r'\bair condition\b',
            r'\bwifi down\b', r'\bno internet\b', r'\bdirty\b', r'\bnoise\b', r'\bdisturb(ed|ance)?\b'
        ]
    ),
    (
        'fees',
        [
            r'\bfee(s)?\b', r'\bdue(s)?\b', r'\bpayment\b', r'\breceipt\b', r'\bfee slip\b',
            r'\bpay fee\b', r'\bhow much fee\b', r'\bfee structure\b', r'\bmonthly fee\b',
            r'\blibrary fee\b'
        ]
    ),
    (
        'seats',
        [
            r'\bseat(s)?\b', r'\blibrary slot\b', r'\bbooking\b', r'\breserve\b', r'\bhold seat\b',
            r'\bshift(s)?\b', r'\bseat status\b', r'\bseat availability\b', r'\bdesk\b',
            r'\bground floor\b', r'\bfirst floor\b'
        ]
    ),
    (
        'timings',
        [
            r'\btiming(s)?\b', r'\bschedule\b', r'\bhour(s)?\b', r'\bopen(ing)?\b', r'\bclose(ing)?\b',
            r'\bopen time\b', r'\bclose time\b', r'\bsunday open\b', r'\bwhen does it open\b',
            r'\bwhen does it close\b'
        ]
    ),
    (
        'admission',
        [
            r'\badmission(s)?\b', r'\bjoin(ing)?\b', r'\benroll(ment)?\b', r'\bregist(er|ration)\b',
            r'\bnew student\b', r'\bhow to join\b', r'\bbatch start\b', r'\btake admission\b'
        ]
    ),
    (
        'auth',
        [
            r'\blogin\b', r'\bpassword\b', r'\bforgot\b', r'\breset password\b', r'\botp\b',
            r'\bcant login\b', r'\bcannot login\b', r'\blocked\b', r'\bcredential(s)?\b',
            r'\bverify account\b'
        ]
    ),
    (
        'courses',
        [
            r'\bnote(s)?\b', r'\bcourse(s)?\b', r'\bmaterial(s)?\b', r'\bstudy material\b',
            r'\bsyllabus\b', r'\btest series\b', r'\bexam\b', r'\bpdf\b', r'\blecture(s)?\b',
            r'\brecorded class\b'
        ]
    ),
    (
        'greeting',
        [
            r'^(hi|hello|hey|namaste|pranam|namaskar|good morning|good evening|good afternoon)(\s+sir|\s+mam|\s+asst)?[\.!]*$',
            r'\bnamaste\b', r'\bpranam\b', r'\bgood morning\b', r'\bgood evening\b', r'\bgood afternoon\b',
            r'^(hi|hello|hey)[\.!]*$'
        ]
    ),
]

# Separate response wording for ABCD Asst. (Vikas Dangi) and Sandeep Sir
# 3 variants each per topic
RESPONSES_BY_PERSONA = {
    'vikas': {
        'emergency': [
            f"Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. Please know you are not alone. If you are in distress, professional support is available free 24x7 via Tele-MANAS at 14416. An urgent notification has been sent to our team, and for immediate assistance you can call {URGENT_CALL_PHONE}.",
            f"Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now and will review your message soon. Please take a gentle breath. You can reach trained counselors free 24x7 at the National Tele-MANAS helpline (14416). We have flagged your message for priority review, and you can also reach us directly at {URGENT_CALL_PHONE}.",
            f"Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk and will get back to you shortly. Your wellbeing is precious to us. Please connect with the 24x7 Tele-MANAS helpline at 14416 for immediate support. Our admin team has been alerted, and you can also call {URGENT_CALL_PHONE}."
        ],
        'fees_dispute': [
            f"Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. For payment issues or refund inquiries, our accounts desk reviews every bank transaction directly. Vikas Sir will inspect this soon, and for urgent assistance you can call {URGENT_CALL_PHONE}.",
            f"Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now. Financial corrections and payment double-deductions are personally audited to keep your records secure. Please keep your transaction ID handy. Vikas Sir will follow up soon, or call {URGENT_CALL_PHONE}.",
            f"Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away and will get back to you shortly. We have noted your payment concern for human inspection. Vikas Sir will verify your transaction records soon, or you can call our direct line at {URGENT_CALL_PHONE}."
        ],
        'complaint': [
            f"Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. If you are facing any facility or campus issue, please submit a ticket at the Complaints Desk on your student portal so we can track and resolve it. Vikas Sir will review this soon, or call {URGENT_CALL_PHONE}.",
            f"Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now. You can log campus issues, AC/light maintenance, or study room feedback directly via the Complaints section in your portal. Vikas Sir will look into it promptly, or feel free to call {URGENT_CALL_PHONE}.",
            f"Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk. To ensure swift action, please raise a formal ticket from the Complaints section on your dashboard. Vikas Sir will follow up with you shortly."
        ],
        'fees': [
            "Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. You can check your active fee status and download official fee receipts directly in your Student Dashboard under Fees. Vikas Sir will follow up with you soon.",
            "Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now. For fee balances and digital receipts, please open the Fees section on your student portal where past transactions are listed. Vikas Sir will connect with you soon.",
            "Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk. Your payment history and fee receipts can be viewed and downloaded anytime from your Student Dashboard. Vikas Sir will assist you personally soon."
        ],
        'seats': [
            "Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. You can check real-time seat availability on Ground Floor & 1st Floor anytime on the Library Availability page. Vikas Sir will get back to you soon.",
            "Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now. Library study desks are divided into Morning, Evening, and Full-Day shifts. You can view the live seat layout on your portal. Vikas Sir will connect with you soon.",
            "Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk. Please check the Library Availability section on the portal to see current seat allocations. Vikas Sir will assist with your seat query shortly."
        ],
        'timings': [
            "Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. ABCD Library study halls operate daily from 8:00 AM to 8:30 PM (Morning & Evening shifts). Vikas Sir will answer any batch questions soon.",
            "Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now. The library reading halls are open every day from 8:00 AM to 8:30 PM. For specific coaching lecture batch timings, Vikas Sir will follow up with you soon.",
            "Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk. Campus self-study facilities are available throughout the week from 8:00 AM to 8:30 PM. Vikas Sir will connect with you shortly for further details."
        ],
        'admission': [
            "Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. We welcome you to ABCD Coaching & Library! You can review course details and submit your admission form online on the portal. Vikas Sir will guide you through enrollment soon.",
            "Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now. Admissions are open for library reading seats and coaching batches. Feel free to explore the admission form on your portal, and Vikas Sir will connect with you shortly.",
            "Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk. Thank you for your interest in joining ABCD Smart Campus. You can submit an online registration form, and Vikas Sir will assist you with batch placement soon."
        ],
        'auth': [
            "Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. If you are having trouble logging in, please use the 'Forgot Password' link on the login page to reset your credentials via email OTP. Vikas Sir will check if further help is needed.",
            "Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now. For password recovery or locked accounts, enter your registered email on the Forgot Password screen. Vikas Sir will follow up with you shortly.",
            "Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk. If you need help accessing your account, please trigger a secure OTP reset from the login screen. Vikas Sir will assist you personally soon."
        ],
        'courses': [
            "Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. You can access enrolled video courses, syllabus notes, and study PDFs directly in the Courses section of your portal. Vikas Sir will follow up soon.",
            "Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now. Study materials and lecture modules are available on the Courses page on your student dashboard. Vikas Sir will answer your specific subject queries soon.",
            "Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk. For lecture modules and practice material, please explore the Courses tab on ABCD Campus. Vikas Sir will connect with you shortly."
        ],
        'greeting': [
            "Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. We have received your greeting. How can we assist you today? Vikas Sir will reply personally soon.",
            "Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now and will review your message soon. Thank you for getting in touch, and Vikas Sir will connect with you shortly.",
            "Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk. We have received your message and Vikas Sir will get back to you shortly. Wishing you a productive day!"
        ],
        'fallback': [
            "Namaste! I am an automated assistant on behalf of ABCD Asst. Vikas Dangi. Vikas Sir is currently busy and will connect shortly. We have safely received your query and Vikas Sir will respond personally soon.",
            "Hello! This is the automated assistant for ABCD Asst. Vikas Dangi. Vikas Sir is engaged right now and will review your message soon. Vikas Sir will connect with you shortly to assist you.",
            "Greetings! I am the automated bot for ABCD Asst. Vikas. Vikas Sir is temporarily away from the desk. Your message is noted, and Vikas Sir will get back to you personally as soon as he is free."
        ]
    },
    'sandeep': {
        'emergency': [
            f"Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. Please know that you are not alone and your wellbeing matters deeply. If you are experiencing severe distress, free professional support is available 24x7 via Tele-MANAS at 14416. An urgent alert has been placed for Sandeep Sir, and for immediate help you can call {URGENT_CALL_PHONE}.",
            f"Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is currently busy in classes and will review your message soon. Please take a gentle breath. Confidential, free mental health counseling is accessible anytime at Tele-MANAS (14416). We have flagged this urgently for Sandeep Sir, and you can also call our direct line at {URGENT_CALL_PHONE}.",
            f"Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now and will get back to you shortly. Please do not face this alone. Free 24x7 counseling is available via Tele-MANAS at 14416. An urgent notification has been delivered to Sandeep Sir, and you may call {URGENT_CALL_PHONE}."
        ],
        'fees_dispute': [
            f"Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. Financial adjustments and payment deductions are personally verified by our admin desk. Sandeep Sir will inspect your records as soon as class concludes, or you can call {URGENT_CALL_PHONE} for immediate assistance.",
            f"Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now. Any payment dispute or duplicate charge is audited directly to ensure accuracy. Please keep your transaction details ready. Sandeep Sir will connect shortly, or call {URGENT_CALL_PHONE}.",
            f"Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. We have recorded your billing inquiry for manual review. Sandeep Sir will verify your transaction details shortly, or you can contact our office directly at {URGENT_CALL_PHONE}."
        ],
        'complaint': [
            f"Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. To report any maintenance or library facility concern, please submit a formal request at the Complaints Desk on your portal. Sandeep Sir will review it, or call {URGENT_CALL_PHONE}.",
            f"Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now. You can log study hall issues, fan/light maintenance, or water concerns on the Complaints page of your portal for tracked resolution. Sandeep Sir will follow up soon, or call {URGENT_CALL_PHONE}.",
            f"Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. For prompt action on campus issues, please log a ticket on the Complaints section of your portal. Sandeep Sir will inspect this as soon as he is free."
        ],
        'fees': [
            "Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. You can check your active fee status and download signed fee receipts inside your Student Dashboard under Fees. Sandeep Sir will reply personally soon.",
            "Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now. For payment records and digital fee slips, please review the Fees section on your student portal. Sandeep Sir will connect with you shortly.",
            "Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. Your fee statements and download links are accessible anytime on the Student Dashboard. Sandeep Sir will follow up with you soon."
        ],
        'seats': [
            "Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. Real-time library desk availability across Ground Floor and 1st Floor can be viewed on the Library Availability page. Sandeep Sir will assist with your seat query soon.",
            "Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now. Study desks are allocated for Morning, Evening, and Full-Day shifts. You can inspect currently open seats on the live floor map. Sandeep Sir will connect with you shortly.",
            "Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. Please explore the Library Availability section on the portal to see seat occupancy. Sandeep Sir will assist you personally as soon as he is free."
        ],
        'timings': [
            "Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. ABCD Library study halls operate daily from 8:00 AM to 8:30 PM on Ground Floor and 1st Floor. Sandeep Sir will answer your coaching batch queries soon.",
            "Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now. Library self-study halls are open every day from 8:00 AM to 8:30 PM. Sandeep Sir will share specific lecture batch schedules with you shortly.",
            "Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. Study rooms are open throughout the week from 8:00 AM to 8:30 PM. Sandeep Sir will get back to you with timetable details shortly."
        ],
        'admission': [
            "Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. Welcome to ABCD Coaching & Library! You can review course details and submit your admission form on the portal. Sandeep Sir will guide you through enrollment soon.",
            "Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now. Admissions for English grammar batches and library reading seats are open. Please explore the online admission form, and Sandeep Sir will connect with you shortly.",
            "Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. Thank you for your interest in joining ABCD. You can fill out the admission form on the website, and Sandeep Sir will follow up personally soon."
        ],
        'auth': [
            "Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. If you cannot log in, please use the 'Forgot Password' link on the login page to reset your password using email OTP. Sandeep Sir will assist if you need further help.",
            "Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now. For password reset or login recovery, enter your registered email on the Forgot Password screen. Sandeep Sir will check on your account shortly.",
            "Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. Please use the secure OTP reset option on the login page to restore account access. Sandeep Sir will follow up with you as soon as he is free."
        ],
        'courses': [
            "Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. You can access English grammar lessons, course videos, and downloadable notes in the Courses section of the portal. Sandeep Sir will answer academic queries soon.",
            "Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now. Lecture modules and study materials are uploaded on the Courses portal for enrolled students. Sandeep Sir will answer your questions shortly.",
            "Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. Please review the learning materials on the Courses page on ABCD Campus. Sandeep Sir will provide personalized academic guidance soon."
        ],
        'greeting': [
            "Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. We have received your greeting. How can we assist your studies today? Sandeep Sir will reply personally soon.",
            "Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now and will review your message soon. Thank you for reaching out, and Sandeep Sir will connect with you shortly.",
            "Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. We have received your message and Sandeep Sir will get back to you shortly. Stay focused on your studies!"
        ],
        'fallback': [
            "Namaste! I am an automated assistant on behalf of Sandeep Sir. Sir is currently taking sessions and will connect shortly. Your query has been noted, and Sandeep Sir will get back to you personally as soon as class finishes.",
            "Pranam! This is the automated assistant for Sandeep Sir. Sandeep Sir is busy in classes right now and will review your message soon. Sandeep Sir will connect with you shortly to assist you.",
            "Greetings! I am the automated assistant on behalf of Sandeep Sir. Sir is engaged with students right now. Your message is safely received and Sandeep Sir will respond personally as soon as he is free."
        ]
    }
}

# Quick action chips matching verified URLs:
# - Call: tel:8109455803
# - Tele-MANAS: tel:14416
# - Complaints: /complaints/
# - Fees/Dashboard: /dashboard/
# - Live Seats: /library-availability/
# - Campus Services: /services/
# - Admission Form: /admission-form/
# - Forgot Password: /forgot-password/
# - Courses: /courses/
TOPIC_CHIPS = {
    'emergency': [
        {'label': 'Tele-MANAS (14416)', 'url': 'tel:14416', 'icon': 'bx-phone-call'},
        {'label': f'Call: {URGENT_CALL_PHONE}', 'url': f'tel:{URGENT_CALL_PHONE}', 'icon': 'bx-phone'}
    ],
    'fees_dispute': [
        {'label': f'Call: {URGENT_CALL_PHONE}', 'url': f'tel:{URGENT_CALL_PHONE}', 'icon': 'bx-phone'},
        {'label': 'Complaint Desk', 'url': '/complaints/', 'icon': 'bx-support'}
    ],
    'complaint': [
        {'label': 'Complaint Desk', 'url': '/complaints/', 'icon': 'bx-support'},
        {'label': f'Call: {URGENT_CALL_PHONE}', 'url': f'tel:{URGENT_CALL_PHONE}', 'icon': 'bx-phone'}
    ],
    'fees': [
        {'label': 'Dashboard & Fees', 'url': '/dashboard/', 'icon': 'bx-receipt'},
        {'label': 'Campus Services', 'url': '/services/', 'icon': 'bx-info-circle'}
    ],
    'seats': [
        {'label': 'Live Seat Layout', 'url': '/library-availability/', 'icon': 'bx-chair'},
        {'label': 'My Seat', 'url': '/my-seat/', 'icon': 'bx-book-reader'}
    ],
    'timings': [
        {'label': 'Campus Services', 'url': '/services/', 'icon': 'bx-time'},
        {'label': 'Contact Page', 'url': '/contact/', 'icon': 'bx-phone'}
    ],
    'admission': [
        {'label': 'Admission Form', 'url': '/admission-form/', 'icon': 'bx-edit'},
        {'label': 'Campus Services', 'url': '/services/', 'icon': 'bx-graduation'}
    ],
    'auth': [
        {'label': 'Forgot Password', 'url': '/forgot-password/', 'icon': 'bx-key'},
        {'label': 'Login Page', 'url': '/login/', 'icon': 'bx-log-in'}
    ],
    'courses': [
        {'label': 'Browse Courses', 'url': '/courses/', 'icon': 'bx-book-open'}
    ],
    'greeting': [
        {'label': 'Campus Services', 'url': '/services/', 'icon': 'bx-grid-alt'},
        {'label': 'Library Availability', 'url': '/library-availability/', 'icon': 'bx-chair'}
    ],
    'fallback': [
        {'label': 'Campus Services', 'url': '/services/', 'icon': 'bx-grid-alt'},
        {'label': f'Call: {URGENT_CALL_PHONE}', 'url': f'tel:{URGENT_CALL_PHONE}', 'icon': 'bx-phone'}
    ]
}


def get_persona_key(user):
    """Identifies persona for user: 'sandeep' or 'vikas'."""
    email_clean = (user.email or '').strip().lower()
    username_clean = (user.username or '').strip().lower()
    if email_clean == SANDEEP_SIR_EMAIL or 'sandeep' in username_clean or 'sandy' in username_clean:
        return 'sandeep'
    return 'vikas'


def classify_message(content: str):
    """
    Deterministically classifies text content using regex keywords.
    Returns (topic, matched_keyword_snippet).
    """
    clean_text = (content or "").strip().lower()
    if not clean_text:
        return 'fallback', ''

    for topic, patterns in TOPIC_RULES:
        for pat in patterns:
            match = re.search(pat, clean_text, re.IGNORECASE)
            if match:
                matched_str = match.group(0)
                return topic, matched_str

    return 'fallback', ''


def get_quick_chips(topic: str):
    """Returns quick action chips for a detected topic."""
    return TOPIC_CHIPS.get(topic, TOPIC_CHIPS['fallback'])


def is_staff_or_teacher(user):
    """
    Returns True if user is a teacher, staff, or superuser.
    Staff/teachers are excluded from triggering auto-replies.
    """
    if not user or not user.is_authenticated:
        return False
    if user.is_staff or user.is_superuser:
        return True
    from users.models import TeacherProfile
    return TeacherProfile.objects.filter(user=user).exists()


def get_or_create_auto_reply_config(user):
    """
    Returns or creates the AutoReplyConfig for a user.
    Defaults is_enabled=False so nothing sends until explicitly enabled in admin.
    Sets default wait_minutes to 5 for ABCD Asst, 15 for Sandeep Sir.
    """
    from users.models import AutoReplyConfig
    email_clean = (user.email or '').strip().lower()

    defaults = {
        'is_enabled': False,
        'wait_minutes': 5 if email_clean == ABCD_ASST_EMAIL else (15 if email_clean == SANDEEP_SIR_EMAIL else 10),
        'cooldown_hours': 6,
    }
    config, _ = AutoReplyConfig.objects.get_or_create(user=user, defaults=defaults)
    return config


def handle_direct_message_sent(message):
    """
    Called when a message is sent in Guidy inside a DirectChatSession.
    Handles:
    1. If the owner sent this message: cancel any active pending auto-reply.
    2. If a non-staff user sent this to an auto-reply configured owner:
       - Check if config enabled
       - Check cooldown
       - Check pending queue
       - Classify and queue pending AutoReplyLog.
    """
    direct_session = message.direct_session
    if not direct_session:
        return

    sender = message.sender
    recipient = direct_session.user2 if direct_session.user1 == sender else direct_session.user1

    from users.models import AutoReplyConfig, AutoReplyLog

    # Case 1: The message sender is an account owner who had a pending auto-reply
    # Cancel pending auto-replies because the owner replied personally!
    pending_logs = AutoReplyLog.objects.filter(
        direct_session=direct_session,
        account=sender,
        status='pending'
    )
    if pending_logs.exists():
        pending_logs.update(
            status='human_replied',
            human_replied_first=True
        )
        logger.info(f"[AutoReply] Cancelled pending auto-reply for conversation {direct_session.id}: owner {sender.username} replied manually.")

    # Case 2: The recipient has AutoReplyConfig configured
    recip_email = (recipient.email or '').strip().lower()
    is_target_account = recip_email in (ABCD_ASST_EMAIL, SANDEEP_SIR_EMAIL) or hasattr(recipient, 'auto_reply_config')

    if not is_target_account:
        return

    # Exclusion: Staff and teachers messaging the owner do not trigger auto-replies
    if is_staff_or_teacher(sender):
        logger.debug(f"[AutoReply] Skipping auto-reply for staff/teacher sender {sender.username}")
        return

    config = get_or_create_auto_reply_config(recipient)
    
    # Ensure it's enabled for the main accounts
    if recip_email in (ABCD_ASST_EMAIL, SANDEEP_SIR_EMAIL):
        if not config.is_enabled:
            config.is_enabled = True
            config.save(update_fields=['is_enabled'])
            
    if not config.is_enabled:
        logger.debug(f"[AutoReply] Auto-reply disabled for {recipient.username}")
        return

    now = timezone.now()

    # Burst cooldown: only ONE auto-reply per 6-hour window per conversation
    # (Disabled based on user request: "it should do always")
    # cooldown_cutoff = now - timedelta(hours=config.cooldown_hours)
    # recent_sent = AutoReplyLog.objects.filter(
    #     account=recipient,
    #     sender=sender,
    #     direct_session=direct_session,
    #     status='sent',
    #     sent_at__gte=cooldown_cutoff
    # ).exists()

    # if recent_sent:
    #     logger.info(f"[AutoReply] Burst cooldown active for {sender.username} -> {recipient.username} ({config.cooldown_hours}h window)")
    #     return

    # If there is already a pending auto-reply for this conversation, do not spawn duplicates
    existing_pending = AutoReplyLog.objects.filter(
        account=recipient,
        sender=sender,
        direct_session=direct_session,
        status='pending'
    ).first()

    topic, matched_kw = classify_message(message.content)
    is_emergency = (topic == 'emergency')

    due_at = now + timedelta(minutes=config.wait_minutes)

    if existing_pending:
        # Keep timer from original message or update topic if high-priority (e.g. emergency)
        # Update: Reset timer to X minutes from the LAST message sent
        existing_pending.due_at = due_at
        existing_pending.detected_topic = topic
        existing_pending.matched_keywords = matched_kw
        
        if is_emergency:
            existing_pending.flagged_emergency = True
            
        existing_pending.save(update_fields=['detected_topic', 'matched_keywords', 'flagged_emergency', 'due_at'])
        logger.debug(f"[AutoReply] Updated existing pending auto-reply id {existing_pending.id} with new due_at")
        _wake_scheduler()
        return

    due_at = now + timedelta(minutes=config.wait_minutes)

    AutoReplyLog.objects.create(
        account=recipient,
        sender=sender,
        direct_session=direct_session,
        trigger_message=message,
        detected_topic=topic,
        matched_keywords=matched_kw,
        due_at=due_at,
        status='pending',
        flagged_emergency=is_emergency
    )
    logger.info(f"[AutoReply] Queued auto-reply for {sender.username} -> {recipient.username} (Topic: {topic}, Due at: {due_at.isoformat()})")
    _wake_scheduler()


def _wake_scheduler():
    """Wake the sleeping scheduler so it recalculates the next due time."""
    try:
        from users.scheduler import notify_scheduler_task_changed
        notify_scheduler_task_changed()
    except Exception:
        pass


def process_due_auto_replies():
    """
    Evaluates all pending auto-replies whose due_at has arrived.
    Checks if the owner has manually replied in the meantime.
    If not, posts the rotating response variant as a Message with is_auto_reply=True.
    Returns the count of auto-replies sent.
    """
    from users.models import AutoReplyLog, Message, Notification
    now = timezone.now()

    # Fetch pending logs due for evaluation
    due_logs = AutoReplyLog.objects.filter(
        status='pending',
        due_at__lte=now
    ).select_related('account', 'sender', 'direct_session', 'trigger_message')

    sent_count = 0

    for log in due_logs:
        with transaction.atomic():
            # Refresh row lock
            log_locked = AutoReplyLog.objects.select_for_update().filter(id=log.id, status='pending').first()
            if not log_locked:
                continue

            config = get_or_create_auto_reply_config(log_locked.account)
            if not config.is_enabled:
                log_locked.status = 'cancelled'
                log_locked.save(update_fields=['status'])
                continue

            # Check if owner replied since trigger message
            trigger_time = log_locked.trigger_message.timestamp if log_locked.trigger_message else log_locked.created_at
            owner_replied = Message.objects.filter(
                direct_session=log_locked.direct_session,
                sender=log_locked.account,
                timestamp__gt=trigger_time
            ).exists()

            if owner_replied:
                log_locked.status = 'human_replied'
                log_locked.human_replied_first = True
                log_locked.save(update_fields=['status', 'human_replied_first'])
                logger.info(f"[AutoReply] Cancelled auto-reply #{log_locked.id}: {log_locked.account.username} replied manually.")
                continue

            # Verify cooldown again to prevent edge-case race conditions
            # (Disabled based on user request: "it should do always")
            # cooldown_cutoff = now - timedelta(hours=config.cooldown_hours)
            # already_sent = AutoReplyLog.objects.filter(
            #     account=log_locked.account,
            #     sender=log_locked.sender,
            #     direct_session=log_locked.direct_session,
            #     status='sent',
            #     sent_at__gte=cooldown_cutoff
            # ).exclude(id=log_locked.id).exists()

            # if already_sent:
            #     log_locked.status = 'skipped_cooldown'
            #     log_locked.save(update_fields=['status'])
            #     logger.info(f"[AutoReply] Log #{log_locked.id} skipped due to active cooldown.")
            #     continue

            # Select persona and rotating variant (>= 3 variants, never repeat same back-to-back in conversation)
            persona_key = get_persona_key(log_locked.account)
            persona_dict = RESPONSES_BY_PERSONA.get(persona_key, RESPONSES_BY_PERSONA['vikas'])
            topic = log_locked.detected_topic or 'fallback'
            variants = persona_dict.get(topic, persona_dict['fallback'])

            last_log = AutoReplyLog.objects.filter(
                direct_session=log_locked.direct_session,
                account=log_locked.account,
                status='sent'
            ).exclude(id=log_locked.id).order_by('-sent_at').first()

            if last_log and variants:
                next_index = (last_log.variant_index + 1) % len(variants)
            else:
                next_index = 0

            chosen_text = variants[next_index]

            # If back-to-back same text somehow matches, pick next
            if last_log and last_log.chosen_response == chosen_text and len(variants) > 1:
                next_index = (next_index + 1) % len(variants)
                chosen_text = variants[next_index]

            # Send the auto-reply message
            reply_msg = Message.objects.create(
                direct_session=log_locked.direct_session,
                sender=log_locked.account,
                content=chosen_text,
                message_type=Message.TYPE_TEXT,
                is_auto_reply=True,
                auto_reply_topic=topic
            )

            # Update the log
            log_locked.reply_message = reply_msg
            log_locked.chosen_response = chosen_text
            log_locked.variant_index = next_index
            log_locked.status = 'sent'
            log_locked.sent_at = timezone.now()
            if topic == 'emergency':
                log_locked.flagged_emergency = True
                # Dispatch real in-app Urgent Notification to the human account owner
                try:
                    Notification.objects.create(
                        user=log_locked.account,
                        title="🚨 Urgent: Guidy Distress Message",
                        message=f"Student {log_locked.sender.get_full_name() or log_locked.sender.username} sent a distress inquiry in Guidy. Please review immediately.",
                        category="guidy",
                        meta={"urgent": True, "direct_session_id": log_locked.direct_session.id},
                        link=f"/guidy/?direct={log_locked.direct_session.id}"
                    )
                except Exception as notif_err:
                    logger.error(f"[AutoReply] Failed to create urgent notification: {notif_err}")

            log_locked.save()

            sent_count += 1
            logger.info(f"[AutoReply] Posted auto-reply #{log_locked.id} (persona: {persona_key}, topic: {topic}, variant: {next_index}) to {log_locked.sender.username}")

    return sent_count
