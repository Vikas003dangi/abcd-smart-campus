# Multi-Service Fee Architecture & Workflow Documentation

## 1. Architectural Overview & Context

Historically, ABCD Smart Campus maintained a single global `fee_expiry_date` on the `StudentProfile` model. As the campus expanded to offer distinct **Coaching** and **Library** facilities—and admitted students enrolled in **Both** simultaneously—a critical architectural problem emerged:
- Coaching fees and Library fees operate on independent billing cycles, pricing tiers, and renewal schedules.
- Overwriting a single `fee_expiry_date` caused one service's payment to prematurely extend or truncate the other service's validity.
- Reminder emails, WhatsApp messages, push notifications, and overdue dashboard badges conflated both services, confusing students and administrators.

The **Service-Aware Fee Architecture** resolves this by establishing full service separation across the database models, calculation engines, user interfaces, communication pipelines, and background reminder tasks.

---

## 2. Database Schema & Data Models

### 2.1. `StudentProfile` Model (`users/models.py`)
- **`coaching_fee_expiry_date` (`models.DateField`, nullable)**: Tracks validity for Coaching enrollment.
- **`library_fee_expiry_date` (`models.DateField`, nullable)**: Tracks validity for Library enrollment.
- **`fee_expiry_date` (`models.DateField`, nullable)**: Retained as a synced composite pointer:
  - For `service_type == 'Both'`: `min([d for d in [coaching_fee_expiry_date, library_fee_expiry_date] if d])` (earliest upcoming expiry).
  - For `service_type == 'Coaching'`: mirrors `coaching_fee_expiry_date`.
  - For `service_type == 'Library'`: mirrors `library_fee_expiry_date`.
- **Properties**:
  - `effective_coaching_expiry`: Returns `coaching_fee_expiry_date` (or `fee_expiry_date` as fallback for pure coaching legacy data).
  - `effective_library_expiry`: Returns `library_fee_expiry_date` (or `fee_expiry_date` as fallback for pure library legacy data).
  - `is_coaching_expired`, `is_library_expired`: Boolean flags evaluated against `timezone.localdate()`.

### 2.2. `FeePayment` Model (`users/models.py`)
- **`service` (`models.CharField`, choices `['coaching', 'library']`, default `'coaching'`)**:
  - Explicitly scopes each recorded calendar month fee.
  - Unique constraint: `unique_together = ('student', 'month', 'year', 'service')`, allowing a student enrolled in `Both` to have separate payments recorded for the same month/year.

### 2.3. `FeeTransaction` Model (`users/models.py`)
- **`service` (`models.CharField`, choices `['coaching', 'library']`, default `'coaching'`)**:
  - Scopes the financial transaction, receipt number (`ABCD_YY/NNNNNNN`), and payment mode to the respective service.

### 2.4. `DismissedFeeAlert` Model (`users/models.py`)
- **`service` (`models.CharField`, choices `['coaching', 'library']`, default `'coaching'`)**:
  - Scopes teacher dashboard alert dismissals.
  - Unique constraint: `unique_together = ('teacher', 'student', 'expiry_date', 'service')`.
  - Dismissing an alert for Coaching overdue does not hide a separate Library overdue alert for the same student.

---

## 3. Expiry Calculation & Synchronization Flow

```
                      +---------------------------------------+
                      |       Teacher / Admin Submits         |
                      |        Fee Action in Calendar         |
                      +---------------------------------------+
                                          |
                                          v
                      +---------------------------------------+
                      |         Target Service Scoped         |
                      |         ('coaching' | 'library')      |
                      +---------------------------------------+
                                          |
                        +-----------------+-----------------+
                        |                                   |
                        v                                   v
             [ Standard Payment / Range ]            [ Clear Expiry ]
                        |                                   |
                        v                                   v
          Recalculate or apply manual date        Target service expiry set
             for the specific service             to None; cache cleared;
                        |                         reminders/alerts suppressed
                        +-----------------+-----------------+
                                          |
                                          v
                      +---------------------------------------+
                      |    sync_overall_fee_expiry_date()     |
                      |   - Computes composite min() for Both |
                      |   - Preserves independent dates       |
                      +---------------------------------------+
```

### 3.1. Calculation Rules
1. **Fee Range Calculation (`sync_student_fee_chain`)**:
   - Calculates paid contiguous blocks filtered strictly by `service=target_service`.
   - Accounts for active and historic `StudentHoldPeriod` records scoped to the student.
2. **Explicit Override (`manualExpiryDate`)**:
   - When a teacher overrides the date in the modal, it updates only `coaching_fee_expiry_date` or `library_fee_expiry_date`.
3. **Clear Expiry Action (`clear_expiry`)**:
   - Sets the target service's expiry date to `None`.
   - Resets `fee_expiry_date` to `None` (or to the remaining active service's expiry date if `Both`).
   - Does not auto-recalculate until a new fee payment is explicitly recorded.

---

## 4. UI & Dashboard Experience

### 4.1. Fee Calendar (`/users/fee-calendar/<id>/`)
- **Service Selection Modal (`fee_calendar_choice.html`)**:
  - If a student is enrolled in `Both` and no `?service=` query parameter is supplied, the teacher is presented with a modal to choose whether to manage **Coaching Fees** or **Library Fees**.
- **Service Tabs**:
  - The calendar page includes dynamic service switcher tabs when `student.service_type == 'Both'`, allowing seamless toggling between Coaching and Library calendars.
- **Process Fees API**:
  - `POST /users/api/student/<id>/process-fees/?service=<service>`:
  - Both query parameter and request body payload provide `service: currentService` redundancy.

### 4.2. Student Fee Record (`student_fee_record.html`)
- Displays service badges (`Coaching` / `Library`).
- Dual-service students have tabs to filter transaction logs and receipt downloads per service.

### 4.3. Teacher Dashboard (`teacher_dashboard.html`)
- Overdue list separates students by service with dedicated badge styling.
- `DismissedFeeAlert` actions dismiss alerts per service without suppressing alerts for other facilities.

---

## 5. Communications & Notification Channels

### 5.1. Fee Receipts (WhatsApp & Email)
- Receipts generated include the service name in the header, message text, and PDF breakdown.
- WhatsApp message sends a service-branded document:
  - `send_fee_receipt_whatsapp(student, receipt_number, pdf_content, service=...)`
  - Filename format: `Fee_Receipt_<ReceiptNo>_<Service>.pdf`.

### 5.2. Automated Reminders (`python manage.py send_fee_reminders`)
- Evaluates each student's active services independently:
  - For `Both`: checks `coaching_fee_expiry_date` and `library_fee_expiry_date` separately.
  - Sends distinct notifications for each service meeting the reminder criteria (e.g. 10 days before, 3 days before, on expiry, or overdue).
- **Anti-Spam & Cooldowns**:
  - Cache key `fee_reminder_sent_{student.id}_{service}_{stage}_{today}` prevents duplicate alerts within a 24-hour window per service.
- **Suppression on `None` Expiry**:
  - If an expiry date is `None` (e.g. after 'Clear Expiry'), the command logs a skip and generates zero alerts.

---

## 6. Audit & Ambiguity Reporting Tool

To audit legacy data or resolve ambiguities in production, run the management command:

```bash
# Generate report of students with legacy or ambiguous fee states
python manage.py report_fee_service_ambiguity

# Automatically backfill legacy single-service records to their respective service fields
python manage.py report_fee_service_ambiguity --auto-heal
```

---

## 7. Automated Test Suite

The test suite in `users/tests_service_aware_fees.py` includes 22 unit and integration tests covering:
- Service isolation during payment creation and updates.
- Independent expiry date calculations.
- Min-date composite logic for dual-service students.
- Per-service WhatsApp and email notifications.
- Independent 24-hour reminder cooldowns.
- `clear_expiry` suppression of reminders, overdue alerts, and dashboard lists.

To run the suite:
```bash
python manage.py test users.tests_service_aware_fees
```
