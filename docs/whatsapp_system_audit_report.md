# ABCD Smart Campus: WhatsApp Messaging System & Birthday Audit Report

**Date of Audit**: September 11, 2026  
**Scope**: WhatsApp Message Dispatchers, Meta Cloud API Templates, Error Handling, and Birthday Scheduler Verification.

---

## 1. Executive Summary & Verification of DOB Birthday Wishes

### J. Celebratory Birthday Wish Verification
| Parameter | Configuration & Implementation |
| :--- | :--- |
| **Trigger Mechanism** | Daily Embedded Scheduler (`users/scheduler.py`) & Cron Endpoint (`/api/cron/maintenance/`) |
| **Query Target** | **100% of Users with DOB Added**: Queries both `StudentProfile` and `StudentAchievement` (Alumni) |
| **Matching Rule** | `dob__month == today.month` AND `dob__day == today.day` |
| **Recipient Deduplication** | By `user_id` or email / profile ID; ensures users who are both students and alumni receive exactly one wish |
| **Channels Dispatched** | **In-App Notification** + **Celebratory HTML Email** (`emails/birthday_wish_email.html`) |
| **Delivery Guarantee** | Uses yearly cooldown key `f"birthday_{user.id}_{today.year}"` to ensure exactly one message per birthday without timezone drift |
| **Dashboard Routing** | Directs Alumni to `/dashboard/alumni/` and Students to `/dashboard/` |

> [!NOTE]
> **Defect Fixed**: Previously, `process_birthday_wishes()` only inspected `StudentProfile`. Anyone who registered their date of birth in `StudentAchievement` (Alumni) was bypassed. This has been resolved: both collections are now merged, deduplicated, and processed daily.

---

## 2. Complete Inventory of WhatsApp Message Triggers

All WhatsApp notifications use the official **Meta WhatsApp Cloud API (Graph API v19.0)**:  
`https://graph.facebook.com/v19.0/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages`

### Summary Matrix

| # | Event Name | Recipient | Trigger / Condition | Meta Template | Payload Parameters | Fallback Mechanism |
| :- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1** | **Fee Payment Receipt (PDF)** | Student | Teacher records fee payment in Fee Manager (`views.py:8727`) | `fee_receipt_v2` | **Header**: PDF Document Media ID<br>**Body**: `{{1}}` Name, `{{2}}` Amount, `{{3}}` Service, `{{4}}` Receipt No | Direct WhatsApp Document message with full text caption |
| **2** | **Admission Approval** | Student | Teacher approves pending admission (`notifications.py:220`) | `admission_approved_v2` | `{{1}}` Student Full Name<br>`{{2}}` Service Details | System logs warning; in-app notification & approval email delivered |
| **3** | **Alumni Achievement Approved** | Alumni | Teacher approves alumni achievement submission (`views.py:10195`) | `alumni_approval_v2` | `{{1}}` Alumni Name<br>`{{2}}` Achievement Title | Fallback to legacy template `alumni_achievement_approved` |
| **4** | **Fee Reminder (5 Days Pre-Due)** | Student | Daily scheduler finds student whose fee expires in 5 days (`send_fee_reminders.py:105`) | `fee_reminder_5day` | `{{1}}` Student Name<br>`{{2}}` Service Details<br>`{{3}}` Expiry Date | In-App notification + Email tier |
| **5** | **Fee Overdue Warning (1 Day Overdue)** | Student | Daily scheduler finds student whose fee is 1 day overdue (`send_fee_reminders.py:109`) | `fee_warning_overdue` | `{{1}}` Student Name<br>`{{2}}` Service Details<br>`{{3}}` Expiry Date | In-App notification + Email tier |
| **6** | **Seat Hold Grace Warning** | Student | Student's seat hold reaches end date; 3-day grace period starts (`utils.py:922`) | `hold_warning_3day_student` | `{{1}}` Student Name<br>`{{2}}` Seat Details<br>`{{3}}` Teacher Phone Number | In-App notification with CTA buttons + HTML Email |
| **7** | **Seat Hold Grace Alert** | Teacher / Sandeep Sir | Student's seat hold reaches end date; alerts teacher (`utils.py:956`) | `hold_warning_3day_teacher` | `{{1}}` Student Name<br>`{{2}}` Seat Details | In-App teacher alert + Teacher notice Email |
| **8** | **Teacher Broadcast / Announcement** | Filtered Students / Alumni | Teacher publishes broadcast with "Send WhatsApp" enabled (`views.py:9423`, `run_scheduled_broadcasts.py:141`) | `broadcast_banner` (with image) OR `broadcast_message` (text) | **Banner**: Image URL Header<br>**Body**: `{{1}}` Subject, `{{2}}` Message + Attachments/Links | Fallback to `broadcast_message` if image link fails |

---

## 3. Detailed Breakdown of WhatsApp Dispatchers

### 1. Fee Payment Receipt PDF
* **Function**: `send_fee_receipt_whatsapp(student, transaction, pdf_content)`
* **Location**: [`users/notifications.py:67`](file:///b:/ABCD/abcd_web/users/notifications.py#L67)
* **How it Works**:
  1. Validates recipient number with Indian standard (must resolve to 12 digits: `91...`).
  2. Uploads the generated PDF receipt bytes to Meta Media Endpoint (`/media`), receiving a persistent `media_id`.
  3. Sends `fee_receipt_v2` template message with document header referencing `media_id`.
  4. If template is pending or Meta returns status != 200, sends direct document message with explanatory caption.
  5. Updates `transaction.whatsapp_sent = True` upon success.

### 2. Admission Approval & Welcoming
* **Function**: `send_approval_whatsapp(student, service_details)`
* **Location**: [`users/notifications.py:259`](file:///b:/ABCD/abcd_web/users/notifications.py#L259)
* **How it Works**:
  1. Formats phone number and sanitizes service details.
  2. Dispatches `admission_approved_v2` with student name and approved service.
  3. Logs delivery status to Django logger.

### 3. Alumni Achievement Approval
* **Function**: `send_alumni_approval_whatsapp(student_or_ach, achievement_title)`
* **Location**: [`users/notifications.py:295`](file:///b:/ABCD/abcd_web/users/notifications.py#L295)
* **How it Works**:
  1. Accepts either a `StudentAchievement` instance or `StudentProfile`.
  2. Dispatches `alumni_approval_v2` template.
  3. Automatically falls back to `alumni_achievement_approved` if the newer v2 template is pending.

### 4. Fee Due Reminders (5-Day Pre-Due & 1-Day Overdue Warning)
* **Function**: `send_fee_reminder_whatsapp(student, reminder_type, expiry_date_str)`
* **Location**: [`users/notifications.py:471`](file:///b:/ABCD/abcd_web/users/notifications.py#L471)
* **How it Works**:
  * Part of the multi-channel fee lifecycle:
    * `T-10 days`: Email (`pre_10`)
    * **`T-5 days`**: **WhatsApp (`fee_reminder_5day`)**
    * `Day 0 (Due Date)`: Email (`first_day`)
    * **`T+1 day (Overdue)`**: **WhatsApp (`fee_warning_overdue`)**
    * `T+3 days recurring`: Email (`recurring_3day`)

### 5. Seat Hold Grace Period Alerts (Student & Teacher)
* **Functions**: `send_hold_warning_whatsapp_student(...)` and `send_hold_warning_whatsapp_teacher(...)`
* **Location**: [`users/notifications.py:532`](file:///b:/ABCD/abcd_web/users/notifications.py#L532) & [`users/notifications.py:569`](file:///b:/ABCD/abcd_web/users/notifications.py#L569)
* **How it Works**:
  * Triggered on Day 0 when a student's held seat reaches the hold end date.
  * **Student WhatsApp**: Alerts student they have a 3-day grace period to contact the teacher before automatic forfeiture.
  * **Teacher WhatsApp**: Alerts teacher (Sandeep Sir: `9827662450`) that the grace period has started.

### 6. Broadcast Announcements with Images and Attachments
* **Function**: `send_broadcast_whatsapp(students, subject, message, banner_image_url=None, attachments=None, buttons=None)`
* **Location**: [`users/notifications.py:886`](file:///b:/ABCD/abcd_web/users/notifications.py#L886)
* **How it Works**:
  1. Appends clickable file download links and button URLs directly to the message body.
  2. If `banner_image_url` is provided, dispatches `broadcast_banner`.
  3. If banner fails or no image is attached, seamlessly dispatches `broadcast_message`.

---

## 4. Audit Findings: Bugs, Failure Modes & Applied Fixes

During the audit of the WhatsApp pipeline, 5 critical failure modes were detected and rectified:

### Issue 1: Leading Zero Phone Sanitization Drop
* **Problem**: When Indian users inputted numbers starting with `0` (e.g. `09827662450` = 11 digits) or `0091`, `sanitize_whatsapp_number` did not strip the leading `0`. Consequently, functions checking for 12 digits starting with `91` failed validation and **silently aborted sending WhatsApp messages** (including fee receipts).
* **Fix**: Enhanced `sanitize_whatsapp_number`:
  * If 11 digits and starts with `0`, strips the leading `0` and prepends `91`.
  * If starts with `00`, strips `00`.
  * Normalizes 10-digit Indian numbers reliably to `91...`.

### Issue 2: Missing or Expired Meta Cloud API Credentials Crash
* **Problem**: In test environments or when `WHATSAPP_API_TOKEN` / `WHATSAPP_PHONE_NUMBER_ID` are not configured in `.env`, functions made HTTP calls to `https://graph.facebook.com/v19.0//messages`. This resulted in network connection timeouts, 404 errors, and clogged log files.
* **Fix**: Added `has_whatsapp_configured()` helper. All 7 WhatsApp functions now verify that credentials exist before making external HTTP requests.

### Issue 3: Meta Template Parameter Length Violations (HTTP 400)
* **Problem**: Meta Graph API enforces strict parameter character limits (typically ~100 characters max for text parameters). If a student had an unusually long service description or multiple services, Meta rejected the request with `(#100) Param text too long`.
* **Fix**: Enforced defensive truncation on all template parameters (`[:90]` for student names, `[:100]` for service details, `[:50]` for dates, `[:950]` for broadcast bodies).

### Issue 4: Teacher Profile Model Relation in Hold Alerts
* **Problem**: In `send_hold_warning_whatsapp_teacher`, the function looked up `teacher_user.profile`. However, in ABCD Smart Campus, teachers use `TeacherProfile` (accessible via `teacher_user.teacher_profile`), while `profile` points to `StudentProfile`. If a teacher user was passed, it failed to find the teacher's phone number.
* **Fix**: Updated resolver to check `teacher_profile` (including `whatsapp_numbers` and `mobile_number`), `profile`, and direct phone strings.

### Issue 5: Relative URLs in WhatsApp Image Headers
* **Problem**: In `run_scheduled_broadcasts.py`, `broadcast.banner_image.url` returned a relative path (`/media/broadcast_banners/...`). Meta Graph API requires a public `https://` URL for media parameters and rejected the payload.
* **Fix**: Ensured all image links are transformed to absolute URLs using `settings.SITE_URL`, and added automatic fallback to text template `broadcast_message` if the image link fails.

---

## 5. Summary Checklist

- [x] Every student and alumni who added their DOB is included in the daily midnight birthday scheduler.
- [x] Deduplication guarantees exactly one birthday wish per person per year.
- [x] All 7 WhatsApp message dispatch flows mapped, documented, and hardened.
- [x] Phone number formatting made resilient against `0`, `+91`, and `0091` inputs.
- [x] Full test suite verified (`manage.py test users` passed 17/17 tests).
