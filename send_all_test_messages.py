import os, sys, time, json, urllib.request
sys.stdout.reconfigure(encoding='utf-8')
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'abcd_web.settings')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'abcd_web'))
django.setup()

from django.conf import settings
from users.models import FeeTransaction
from users.utils.receipt_generator import generate_fee_receipt_pdf

TOKEN = getattr(settings, 'WHATSAPP_API_TOKEN')
PHONE_ID = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID')
RECIPIENT = '917974154551'
URL = f"https://graph.facebook.com/v19.0/{PHONE_ID}/messages"
MEDIA_URL = f"https://graph.facebook.com/v19.0/{PHONE_ID}/media"

headers = {
    'Authorization': f'Bearer {TOKEN}',
    'Content-Type': 'application/json'
}

def send_json(payload):
    req = urllib.request.Request(
        URL,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers
    )
    try:
        res = urllib.request.urlopen(req)
        return json.loads(res.read().decode())
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"HTTP ERROR {e.code}: {err}")
        return None

def upload_pdf(filename, pdf_bytes):
    boundary = '----WebKitFormBoundary7MA4YWxkTrZu0gW'
    body = []
    body.append(f'--{boundary}'.encode('utf-8'))
    body.append(b'Content-Disposition: form-data; name="messaging_product"')
    body.append(b'')
    body.append(b'whatsapp')
    
    body.append(f'--{boundary}'.encode('utf-8'))
    body.append(b'Content-Disposition: form-data; name="type"')
    body.append(b'')
    body.append(b'application/pdf')
    
    body.append(f'--{boundary}'.encode('utf-8'))
    body.append(f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode('utf-8'))
    body.append(b'Content-Type: application/pdf')
    body.append(b'')
    body.append(pdf_bytes)
    body.append(f'--{boundary}--'.encode('utf-8'))
    body.append(b'')
    
    req_body = b'\r\n'.join(body)
    req = urllib.request.Request(
        MEDIA_URL,
        data=req_body,
        headers={
            'Authorization': f'Bearer {TOKEN}',
            'Content-Type': f'multipart/form-data; boundary={boundary}'
        }
    )
    try:
        res = urllib.request.urlopen(req)
        data = json.loads(res.read().decode())
        return data.get('id')
    except urllib.error.HTTPError as e:
        print(f"Media Upload Error: {e.code} - {e.read().decode()}")
        return None

print("==================================================")
print(f"Dispatching Ultra-Premium WhatsApp Messages to: {RECIPIENT}")
print("==================================================")

FOOTER_TEXT = "This is system generated message of ABCD do not reply here.."

# 1. Student Side: Official Approved Template (Hold Warning)
print("\n[1/9] [STUDENT] Seat Hold Expiry Warning (Official Meta Template)...")
p1 = {
    "messaging_product": "whatsapp",
    "to": RECIPIENT,
    "type": "template",
    "template": {
        "name": "hold_warning_3day_student",
        "language": {"code": "en_US"},
        "components": [
            {
                "type": "body",
                "parameters": [
                    {"type": "text", "text": "Nitin Sharma"},
                    {"type": "text", "text": "Ground Floor Library Seat 14 (Morning Shift)"},
                    {"type": "text", "text": "9827662450"}
                ]
            }
        ]
    }
}
r1 = send_json(p1)
print("Result 1:", "SUCCESS" if r1 else "FAILED")
time.sleep(2.5)

# 2. Student Side: Fee Payment Receipt (Attached PDF + Premium Card Button)
print("\n[2/9] [STUDENT] Fee Payment Receipt with PDF & Dashboard Button...")
trans = FeeTransaction.objects.last()
if trans:
    pdf_buf = generate_fee_receipt_pdf(trans)
    pdf_bytes = pdf_buf.getvalue()
    clean_rcpt = str(trans.receipt_number).replace('/', '_')
    media_id = upload_pdf(f"Fee_Receipt_{clean_rcpt}.pdf", pdf_bytes)
    if media_id:
        caption = (
            f"🧾 *OFFICIAL FEE RECEIPT*\n\n"
            f"Dear *Nitin Sharma*,\n"
            f"Your fee payment of *₹{trans.total_amount or 1500}* has been successfully received and recorded at *ABCD Coaching & Library*. ✅\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 *PAYMENT SUMMARY*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🧾 *Receipt No:* {clean_rcpt}\n"
            f"💵 *Amount Paid:* ₹{trans.total_amount or 1500}\n"
            f"📚 *Service:* Library (Ground Floor, Seat 14, Morning Shift)\n"
            f"📎 *Receipt File:* Attached above (PDF)\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Warm regards,\n*Accounts Team | ABCD Campus*"
        )
        p2_doc = {
            "messaging_product": "whatsapp",
            "to": RECIPIENT,
            "type": "document",
            "document": {
                "id": media_id,
                "filename": f"Fee_Receipt_{clean_rcpt}.pdf",
                "caption": caption
            }
        }
        send_json(p2_doc)
        time.sleep(1.5)
        # Interactive Button message
        p2_btn = {
            "messaging_product": "whatsapp",
            "to": RECIPIENT,
            "type": "interactive",
            "interactive": {
                "type": "cta_url",
                "body": {
                    "text": "Your fee ledger and digital validity are updated. Tap below to access your Student Dashboard."
                },
                "footer": {"text": FOOTER_TEXT},
                "action": {
                    "name": "cta_url",
                    "parameters": {
                        "display_text": "View Dashboard",
                        "url": "https://abcdcampus.in/dashboard/"
                    }
                }
            }
        }
        r2 = send_json(p2_btn)
        print("Result 2:", "SUCCESS" if r2 else "FAILED")
time.sleep(2.5)

# 3. Student Side: Ultra-Beautiful Admission Approved Card
print("\n[3/9] [STUDENT] Ultra-Premium Admission Approved Card...")
p3 = {
    "messaging_product": "whatsapp",
    "to": RECIPIENT,
    "type": "interactive",
    "interactive": {
        "type": "cta_url",
        "header": {
            "type": "text",
            "text": "🎓 ADMISSION CONFIRMED"
        },
        "body": {
            "text": (
                "Dear *Nitin Sharma*,\n\n"
                "Welcome to the *ABCD Smart Campus* family! 🎉\n"
                "We are pleased to inform you that your admission application has been reviewed and officially *APPROVED*. ✅\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📋 *ENROLLMENT DETAILS*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📚 *Coaching Batch:* Spoken English & PD\n"
                "🏛 *Smart Library:* Ground Floor, Seat 14\n"
                "⏰ *Shift:* Morning (8:00 AM – 2:00 PM)\n"
                "📅 *Admission Date:* 26 Sep 2026\n"
                "⚡️ *Status:* Active & Confirmed\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Your digital seat pass and learning portal are now active. Tap below to log in and start your learning journey.\n\n"
                "Warm regards,\n"
                "*Team ABCD Smart Campus*"
            )
        },
        "footer": {"text": FOOTER_TEXT},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": "Go To Login",
                "url": "https://abcdcampus.in/login/"
            }
        }
    }
}
r3 = send_json(p3)
print("Result 3:", "SUCCESS" if r3 else "FAILED")
time.sleep(2.5)

# 4. Student Side: 5-Day Advance Fee Reminder Card
print("\n[4/9] [STUDENT] 5-Day Advance Fee Reminder Card...")
p4 = {
    "messaging_product": "whatsapp",
    "to": RECIPIENT,
    "type": "interactive",
    "interactive": {
        "type": "cta_url",
        "header": {
            "type": "text",
            "text": "🔔 FEE DUE REMINDER"
        },
        "body": {
            "text": (
                "Dear *Nitin Sharma*,\n\n"
                "This is a friendly reminder that your monthly fee subscription is approaching renewal. 📅\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "⏳ *RENEWAL DETAILS*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📚 *Facility:* Library (Ground Floor, Seat 14)\n"
                "⏰ *Shift:* Morning (8:00 AM – 2:00 PM)\n"
                "⏳ *Days Left:* 5 Days Remaining\n"
                "📅 *Due Date:* 01 Oct 2026\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please submit your fee on or before the due date to ensure uninterrupted seat reservation and library access.\n\n"
                "Warm regards,\n"
                "*Team ABCD Smart Campus*"
            )
        },
        "footer": {"text": FOOTER_TEXT},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": "Pay Fees Online",
                "url": "https://abcdcampus.in/dashboard/"
            }
        }
    }
}
r4 = send_json(p4)
print("Result 4:", "SUCCESS" if r4 else "FAILED")
time.sleep(2.5)

# 5. Student Side: Overdue Fee Warning Notice Card
print("\n[5/9] [STUDENT] Overdue Fee Warning Notice Card...")
p5 = {
    "messaging_product": "whatsapp",
    "to": RECIPIENT,
    "type": "interactive",
    "interactive": {
        "type": "cta_url",
        "header": {
            "type": "text",
            "text": "⚠️ FEE OVERDUE NOTICE"
        },
        "body": {
            "text": (
                "⚠️ *URGENT FEE OVERDUE NOTICE*\n\n"
                "Dear *Nitin Sharma*,\n"
                "Your monthly service tenure expired on *25 Sep 2026* and is now *OVERDUE*. ❗️\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🔴 *ACCOUNT STATUS*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📚 *Enrolled In:* Coaching & Library (Seat 14)\n"
                "📅 *Expired On:* 25 Sep 2026\n"
                "⚠️ *Action Required:* Immediate Settlement\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please clear your pending dues immediately to prevent automated seat deactivation and cancellation.\n\n"
                "Direct Helpline: +91 98276 62450\n"
                "*Administration | ABCD Campus*"
            )
        },
        "footer": {"text": FOOTER_TEXT},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": "Clear Dues Now",
                "url": "https://abcdcampus.in/dashboard/"
            }
        }
    }
}
r5 = send_json(p5)
print("Result 5:", "SUCCESS" if r5 else "FAILED")
time.sleep(2.5)

# 6. Teacher Side: Student Seat Hold Expiry Alert Card
print("\n[6/9] [TEACHER] Student Seat Hold Expiry Alert Card...")
p6 = {
    "messaging_product": "whatsapp",
    "to": RECIPIENT,
    "type": "interactive",
    "interactive": {
        "type": "cta_url",
        "header": {
            "type": "text",
            "text": "⌛️ SEAT HOLD ALERT"
        },
        "body": {
            "text": (
                "Dear *Sandeep Sir*,\n\n"
                "A student's seat hold tenure has reached its expiry milestone today.\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📋 *HOLD SUMMARY*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "👤 *Student:* Nitin Sharma\n"
                "🏛 *Seat Allotted:* Ground Floor, Seat 14\n"
                "⏰ *Shift:* Morning (8:00 AM – 2:00 PM)\n"
                "⏳ *Grace Period:* 3 Days Activated\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Please log in to your Teacher Dashboard to manage, extend, or release this seat.\n\n"
                "*ABCD Campus Automation*"
            )
        },
        "footer": {"text": FOOTER_TEXT},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": "Teacher Portal",
                "url": "https://abcdcampus.in/teacher/"
            }
        }
    }
}
r6 = send_json(p6)
print("Result 6:", "SUCCESS" if r6 else "FAILED")
time.sleep(2.5)

# 7. Teacher Side: New Fee Payment Received Alert Card
print("\n[7/9] [TEACHER] New Fee Payment Received Alert Card...")
p7 = {
    "messaging_product": "whatsapp",
    "to": RECIPIENT,
    "type": "interactive",
    "interactive": {
        "type": "cta_url",
        "header": {
            "type": "text",
            "text": "💰 PAYMENT RECORDED"
        },
        "body": {
            "text": (
                "Dear *Sandeep Sir*,\n\n"
                "A new student fee payment has been successfully recorded in the campus management system. ✅\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📋 *TRANSACTION DETAILS*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "👤 *Student:* Nitin Sharma\n"
                "📚 *Service:* Library (Ground Floor, Seat 14, Morning)\n"
                "💵 *Amount Collected:* ₹1,500\n"
                "🧾 *Receipt No:* ABCD_26_4078470\n"
                "📅 *New Valid Until:* 26 Oct 2026\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "*ABCD Campus Accounts System*"
            )
        },
        "footer": {"text": FOOTER_TEXT},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": "Teacher Portal",
                "url": "https://abcdcampus.in/teacher/"
            }
        }
    }
}
r7 = send_json(p7)
print("Result 7:", "SUCCESS" if r7 else "FAILED")
time.sleep(2.5)

# 8. Alumni Side: Alumni Achievement Approved Card
print("\n[8/9] [ALUMNI] Honorary Alumni Approval Card...")
p8 = {
    "messaging_product": "whatsapp",
    "to": RECIPIENT,
    "type": "interactive",
    "interactive": {
        "type": "cta_url",
        "header": {
            "type": "text",
            "text": "🏆 ALUMNI VERIFIED"
        },
        "body": {
            "text": (
                "🎉 *CONGRATULATIONS NITIN SHARMA!*\n\n"
                "Your alumni achievement request has been officially verified and *APPROVED*. 🌟\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🎖 *ACHIEVEMENT SUMMARY*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🎖 *Honor:* Selected as Sub-Inspector (SSC CGL)\n"
                "🏛 *Institution:* ABCD Competitive Study Point\n"
                "📜 *Recognition:* Listed in ABCD Hall of Fame\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Your inspiring journey motivates all fellow students. Tap below to visit the Alumni Portal and view your profile.\n\n"
                "With proud regards,\n"
                "*Sandeep Raghuwanshi & Team ABCD*"
            )
        },
        "footer": {"text": FOOTER_TEXT},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": "View Hall of Fame",
                "url": "https://abcdcampus.in/hall-of-fame/"
            }
        }
    }
}
r8 = send_json(p8)
print("Result 8:", "SUCCESS" if r8 else "FAILED")
time.sleep(2.5)

# 9. Campus Broadcast Announcement Card
print("\n[9/9] [BROADCAST] Official Campus Broadcast Notice Card...")
p9 = {
    "messaging_product": "whatsapp",
    "to": RECIPIENT,
    "type": "interactive",
    "interactive": {
        "type": "cta_url",
        "header": {
            "type": "text",
            "text": "📢 CAMPUS NOTICE"
        },
        "body": {
            "text": (
                "📢 *ABCD SMART CAMPUS NOTICE*\n\n"
                "*Regarding:* Gandhi Jayanti Schedule & Special Test Series\n\n"
                "Dear Students,\n"
                "Please review the schedule updates for the upcoming week:\n\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "📋 *SCHEDULE HIGHLIGHTS*\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "🚫 *Coaching Batches:* Closed on 2nd October\n"
                "🏛 *Smart Library:* Open 24/7 as usual\n"
                "📝 *Special Test Series:* Starting 3rd October\n"
                "━━━━━━━━━━━━━━━━━━━━\n\n"
                "Monthly test schedules and room allocations are available on the campus website.\n\n"
                "Warm regards,\n"
                "*Director's Office | ABCD Campus*"
            )
        },
        "footer": {"text": FOOTER_TEXT},
        "action": {
            "name": "cta_url",
            "parameters": {
                "display_text": "Visit Website",
                "url": "https://abcdcampus.in/"
            }
        }
    }
}
r9 = send_json(p9)
print("Result 9:", "SUCCESS" if r9 else "FAILED")

print("\n==================================================")
print("All 9 Ultra-Premium Messages Dispatched Successfully!")
print("==================================================")
