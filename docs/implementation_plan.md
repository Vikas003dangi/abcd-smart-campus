# Implementation Plan: Universal Profile Avatars, Logout Reliability, and Alarm/TWA Diagnostics

Address all issues reported by the user across the app:
1. Bottom bar profile button & avatar/photo display and click behavior across Guest, Student, Alumni, and Teacher dashboards.
2. Logout 404 / 500 errors across the application.
3. Notification enable button loop in To-Do Hub, battery optimization guidance for background alarms, and APK/TWA splash/loading explanation.

---

## User Review Required

> [!IMPORTANT]
> - **Bottom Nav Profile Behavior:**
>   - **Guest Page:** The bottom bar profile icon will now display the user's avatar image in a circle (`default_avatar.png` or gender avatar). Clicking it will smoothly navigate to the Guest Profile page (`/profile/guest/`).
>   - **Student & Alumni Dashboards:** The bottom bar profile icon displays the student/alumni circular photo or gender-aware silhouette avatar (`default_avatar_male.png` / `default_avatar_female.png` / `default_avatar.png`). Clicking it navigates to `/profile/` (which routes to Student Details or Alumni Details).
>   - **Teacher Dashboard:** Displays the teacher circular photo (Sandy Sir / Vaku photos for existing teachers; gender-aware silhouette avatar for any future new teachers without photo). Clicking it navigates to `/teacher/profile/`.
> - **Logout 404/500 Fix:**
>   - Remove `@login_required` on `/logout/` so expired or guest sessions never trigger redirects to broken URLs.
>   - Wrap all queries in `home_page_view` (YouTube, courses, complaints, seats) with fail-safe defaults so the landing page after logout CAN NEVER return a 500 error.
>   - Add the standard logout confirmation modal to `guest_page.html` for consistency with Student and Teacher dashboards.
> - **Notification Enable Button Loop in To-Do Hub:**
>   - Fix `enableAlarmNotificationsNow()` in `todo.html`: When Android/Chrome has notifications blocked (`Notification.permission === 'denied'`), instead of failing silently in an endless loop, display a guided instructions modal showing how to enable notifications in Android Settings > Apps > ABCD Campus > Notifications.
>   - Add clear battery optimization guidance ("Set Battery to Unrestricted") so background alarms are not killed by Android's Doze mode.

---

## Proposed Changes

### 1. Avatar & Profile Utility Fixes

#### [MODIFY] [`users/utils.py`](file:///b:/ABCD/abcd_web/users/utils.py)
- In `get_profile_photo_url()`:
  - Fix incorrect file paths: change `/static/data/avatar_male.png` & `/static/data/avatar_female.png` to `/static/data/default_avatar_male.png` and `/static/data/default_avatar_female.png`.
  - Remove external `ui-avatars.com` fallback. Instead, fall back to our local silhouette avatars:
    - Male &rarr; `/static/data/default_avatar_male.png`
    - Female &rarr; `/static/data/default_avatar_female.png`
    - Common / Guest / Unspecified &rarr; `/static/data/default_avatar.png`

---

### 2. Bottom Nav & Profile Click Fixes Across Dashboards

#### [MODIFY] [`users/templates/users/guest_page.html`](file:///b:/ABCD/abcd_web/users/templates/users/guest_page.html)
- Replace `<i class='bx bx-user'></i>` in `#bnavProfile` with a circular avatar image:
  ```html
  <img src="{% current_user_photo %}" alt="Profile" class="bnav-profile-circle" style="width: 24px; height: 24px; border-radius: 50%; object-fit: cover;">
  ```
- Remove the broken `bnavProfile.addEventListener('click', ...)` listener that called `e.preventDefault()` and attempted to open a non-existent `noProfilePopup`.
- Clicking `#bnavProfile` will now directly navigate to `{% url 'users:profile' %}` (which safely routes authenticated guests to `users:guest_profile_details`).
- Add `#logoutConfirmModal` and `#logoutConfirmOverlay` matching student & teacher dashboards so logging out from Guest page is smooth and consistent.

#### [MODIFY] [`users/templates/users/student_dashboard.html`](file:///b:/ABCD/abcd_web/users/templates/users/student_dashboard.html)
- Fix the boolean operator precedence in the bottom navigation condition:
  - Change `{% if not is_approved_coaching and not has_pending_coaching or not is_approved_library and not has_pending_library %}` so it doesn't mistakenly catch library-only or coaching-only students.
  - Ensure the bottom bar profile link always renders the circular avatar (`<img src="{% current_user_photo %}" class="bnav-profile-circle">`) and links to `{% url 'users:profile' %}`.

#### [MODIFY] [`users/templates/users/teacher_dashboard.html`](file:///b:/ABCD/abcd_web/users/templates/users/teacher_dashboard.html)
- In the bottom navigation:
  - Ensure the profile item ALWAYS displays an image in a circle (`<img src="{{ final_photo }}" class="bnav-profile-circle">`).
  - If no custom photo is present, fallback to `{% current_user_photo %}` (which gives Sandy/Vaku photos for existing teachers, or gender-aware avatar for new teachers).

---

### 3. Logout Reliability & 500 Error Prevention

#### [MODIFY] [`users/views.py`](file:///b:/ABCD/abcd_web/users/views.py)
- **`logout_view`:**
  - Remove `@login_required` decorator. If an unauthenticated user or user with expired session hits `/logout/`, log them out safely without redirecting to login or throwing 404.
  - Explicitly redirect to `users:home_page` with cache-busting headers.
- **`home_page_view`:**
  - Wrap all data queries (`get_latest_youtube_videos()`, `get_accessible_courses()`, `StudentAchievement.objects.filter()`, `Complaint.objects.filter()`, `get_available_seats_count()`) with `try/except` blocks with safe fallback values (empty lists / 0 counts).
  - Guarantee that `home_page_view` NEVER throws a 500 error under any circumstances.

---

### 4. To-Do Hub: Notification Enable Loop & Battery Optimization Guidance

#### [MODIFY] [`users/templates/users/todo.html`](file:///b:/ABCD/abcd_web/users/templates/users/todo.html)
- **Fix Notification Enable Loop:**
  - In `enableAlarmNotificationsNow()`:
    - Check `Notification.permission`. If `'denied'`, show an informative modal:
      - Title: "Notifications Blocked"
      - Message: Explaining that notifications were previously denied in browser/app settings.
      - Step-by-step instructions: "To allow alarms: Open your phone Settings &rarr; Apps &rarr; ABCD Campus (or Chrome) &rarr; Notifications &rarr; Turn ON."
      - Prevent the endless "Enable &rarr; nothing happens &rarr; Enable" loop.
- **Battery Optimization Notice:**
  - When user toggles ON the alarm switch in reminder modal, show a subtle, dismissible tip:
    - "💡 Tip: For alarms to ring reliably when your screen is locked, ensure Battery Optimization is set to **Unrestricted** for ABCD Campus in your phone settings."

---

## Verification Plan

### Automated / Syntax Verification
- Run `python manage.py check` to verify all views, urls, and template tags.

### Manual / Browser Verification
1. **Profile in Bottom Bar:**
   - Log in as Guest &rarr; verify bottom bar shows circular avatar image &rarr; click profile &rarr; verify opens `/profile/guest/`.
   - Log in as Student &rarr; verify bottom bar shows circular photo/avatar &rarr; click profile &rarr; verify opens `/my-details/`.
   - Log in as Alumni &rarr; verify bottom bar shows circular photo/avatar &rarr; click profile &rarr; verify opens alumni profile.
   - Log in as Teacher &rarr; verify bottom bar shows circular photo &rarr; click profile &rarr; verify opens `/teacher/profile/`.
2. **Logout:**
   - Log out from Guest page, Student dashboard, and Teacher dashboard &rarr; verify smooth redirect to Home page without 404 or 500 errors.
   - Test hitting `/logout/` in an incognito window &rarr; verify redirects to Home page without errors.
3. **To-Do Hub Alarm & Notifications:**
   - Open To-Do Hub &rarr; open Reminder modal &rarr; toggle Alarm ON.
   - Click "Enable" on notification banner &rarr; verify clear dialog with Android settings instructions appears if permission is denied, breaking the loop.
