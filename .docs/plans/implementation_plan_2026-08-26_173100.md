# Implementation Plan: Email Architecture & Contact Prompt Fixes

Fix the separation between Account/Credential Emails (`User.email`) and Contact/Notification Emails (`StudentProfile.email` / `StudentAchievement.email`), and ensure the contact info lock popup on the student dashboard only triggers when contact information is genuinely missing.

## User Review Required

> [!IMPORTANT]
> - **Account Email (`User.email`)**: Stored at registration / Google Sign-in. Used strictly for authentication, login, password reset OTPs, and account security. Will no longer be overwritten when a user updates their profile or enters a contact email.
> - **Contact Email (`StudentProfile.email` / `StudentAchievement.email`)**: Used for all transactional notifications, approval emails, fee receipts, seat alerts, broadcasts, etc. Defaults to `User.email` if not explicitly specified.
> - **Dashboard Popup**: Will only trigger when both contact email and user email are absent, or when WhatsApp number is missing (e.g. when a teacher creates a student manually).

---

## Proposed Changes

### 1. `users/forms.py`
- In `StudentProfileForm`:
  - Pre-populate `email` from existing `profile.email` or `user.email` in `__init__`.
  - Save `instance.email = self.cleaned_data.get('email')` in `save()`.
- In `EditStudentProfileForm`:
  - Add `'email'` to `Meta.fields`.
  - Update `save()` to assign `student.email = email` instead of overwriting `student.user.email`.
- In `StudentAchievementForm`:
  - Pre-populate `self.initial['email']` from `profile.email` or `user.email` in `__init__`.
- In `EditAlumniProfileForm`:
  - Update `save()` to assign `achievement.email = email` instead of overwriting `achievement.user.email`.

### 2. `users/views.py`
- In `admission_form_view`:
  - Pre-populate `form.initial['email']` with `request.user.email` when creating a new admission form.
  - Default `student_profile.email` to `request.user.email` if the user leaves the email field blank.
- In `achievement_form_view`:
  - Default `obj.email` to `request.user.email` (or `profile.email`) if left blank.
- In `update_contact_info_api`:
  - Set `profile.email = email` (and sync to `achievement.email`).
  - Only update `user.email` if `user.email` is currently empty.
- In `send_fee_receipt` and Broadcast views:
  - Route emails to `get_user_notification_email()` rather than `user.email` directly.

### 3. `users/notifications.py`
- In `send_seat_switch_approval_email`, `send_seat_rejection_email`, `send_student_progress_email`:
  - Use `get_user_notification_email(student)` to resolve the correct recipient email address.

### 4. `users/utils.py`
- In `_fire_reminder`, `process_learning_reminders`, and broadcast helper:
  - Use `get_user_notification_email()` for recipient email resolution.

### 5. `users/templates/users/student_dashboard.html`
- Update lock overlay condition:
  - Check `not profile.email and not user.email` so registered / Google users are never prompted unnecessarily.

---

## Verification Plan

### Automated Tests
- Run `venv\Scripts\python.exe manage.py test users` to verify all existing and new unit tests pass.
- Add test cases covering:
  - Admission form email inheritance without overwriting `user.email`.
  - Edit profile saving to `profile.email` and preserving `user.email`.
  - Contact lock condition evaluation.
  - Notification email routing to contact email vs credential emails.

### Security Scan
- Run Snyk security scan on modified files.
