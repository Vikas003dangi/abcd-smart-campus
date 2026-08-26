# Storage Optimization & Media Lifecycle Implementation Plan

This plan establishes an automated, zero-waste storage architecture to prevent unwanted media accumulation, free up server disk space, and manage the complete lifecycle of all media across Complaints, Guidy Chat, Broadcasts/Banners, Courses, and Profile photos.

---

## 1. Summary of Identified Areas & Actions

| Area | Storage Path | Auto-Deletion & Lifecycle Rules |
|---|---|---|
| **Complaints Media** | `media/complaints/` | Auto-delete images 5 days after resolution. Wired into daily scheduler. |
| **Guidy Media & Group Chats** | `media/guidy_temp/`<br>`media/group_photos/` | • 10-day auto-purge for all message media (images, docs, audio, voice notes).<br>• Group deletion: Deleting teacher/admin marks group as deleted. Members see notice banner with a 30-day countdown and a "Delete" button.<br>• **Early Master Purge**: If all members delete it from their end, immediately wipe all messages/media from disk without waiting 30 days. |
| **Broadcasts & Ads Banners** | `media/broadcast_attachments/`<br>`media/broadcast_banners/`<br>`media/broadcast_files/` | • Auto-delete broadcast records & physical files older than 20 days.<br>• Attach `post_delete` & `pre_save` signals to clean files on manual delete/edit.<br>• **Banner Display Fix**: Show banner only on base home pages (10-second delay), only once per user. |
| **Courses & Study Materials** | `media/course_thumbnails/`<br>`media/study_materials/`<br>`media/material_thumbnails/` | • `post_delete` on `Course`: Immediately purges course thumbnail, all course material files, and material thumbnails from disk.<br>• `post_delete` on `StudyMaterial`: Immediately purges file and thumbnail from disk.<br>• `pre_save` on `Course` & `StudyMaterial`: Deletes old file when replaced with a new one. |
| **Folder Cleanup** | `b:\ABCD\abcd_web\complaints` | Remove empty, unused folder. |
| **Orphan Media Purge** | `media/` (all subfolders) | Delete the 30 orphaned, unreferenced files on disk (freeing **~222.3 MB** immediately). |

---

## 2. Proposed Changes

### Component 1: Background Automation Scheduler (`users/management/commands/run_local_scheduler.py`)

#### [MODIFY] [run_local_scheduler.py](file:///b:/ABCD/abcd_web/users/management/commands/run_local_scheduler.py)
- Wire all daily cleanup commands into the scheduler loop:
  1. `cleanup_complaint_images` (purges images of complaints resolved >= 5 days ago).
  2. `cleanup_broadcasts` (purges broadcasts & media >= 20 days old).
  3. `purge_expired_media()` (purges chat attachments >= 10 days old).
  4. `purge_expired_group_chats()` (purges group chats deleted >= 30 days ago).

---

### Component 2: Guidy Group Deletion & Storage Lifecycle (`users/models.py`, `users/views.py`, `users/templates/users/guidy.html`)

#### [MODIFY] [users/models.py](file:///b:/ABCD/abcd_web/users/models.py)
- Add tracking fields to `GroupChatSession`:
  - `deleted_by_user` (`ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)`): The admin/teacher who initiated deletion.
  - `deleted_at` (`DateTimeField(null=True, blank=True)`): Timestamp when the group was marked deleted.
  - `deleted_for_users` (`ManyToManyField(User, blank=True)`): Members who have deleted/cleared the group from their end.

#### [MODIFY] [users/views.py](file:///b:/ABCD/abcd_web/users/views.py)
- Update group deletion handler (`guidy_group_manage_members` / `guidy_delete_group`):
  - When an admin or teacher deletes the group:
    - Set `group.is_active = False`, `group.deleted_by_user = request.user`, `group.deleted_at = timezone.now()`.
    - Add `request.user` to `group.deleted_for_users`.
    - Check if all members have cleared it; if so, immediately execute `purge_group_chat_session(group)`.
  - Add API endpoint `guidy_delete_group_for_user`:
    - Allows non-admin members to click "Delete Group from my end".
    - Adds member to `group.deleted_for_users`.
    - Checks if `group.deleted_for_users.count() >= group.members.count()`. If yes, immediately purge all messages, physical files, and the group row.
- Create `purge_group_chat_session(group)` utility:
  - Iterates through all `GroupMessage` files and `group.photo`, physically deleting them from disk (`os.remove`), deletes messages, and deletes the group row.
- Create `purge_expired_group_chats()` utility:
  - Finds any group where `deleted_at <= timezone.now() - timedelta(days=30)` and executes `purge_group_chat_session(group)`.

#### [MODIFY] [users/templates/users/guidy.html](file:///b:/ABCD/abcd_web/users/templates/users/guidy.html)
- If a group is marked as deleted (`deleted_at` is set) and current user has not yet clicked "Delete":
  - Show status banner: *"You are no longer a part of this group. The group was deleted by {deleted_by_name}. Messages and media will automatically be purged in {days_left} days."*
  - Display a red "Delete Group" button allowing the user to clear it from their interface and trigger the early master purge if they are the last member.

---

### Component 3: Course & Study Material Physical File Signals (`users/models.py`)

#### [MODIFY] [users/models.py](file:///b:/ABCD/abcd_web/users/models.py)
- Attach `pre_save` signal to `Course` and `StudyMaterial` to physically delete old files when replaced with a new upload.
- Attach `post_delete` signal to `Course`:
  - Deletes `course.thumbnail` file from disk.
  - Loops over related `StudyMaterial` objects and deletes their `file` and `thumbnail` files from disk.
- Attach `post_delete` signal to `StudyMaterial`:
  - Deletes `file` and `thumbnail` files from disk.
- Attach `pre_save` and `post_delete` signals to `BroadcastMessage` for `banner_image` and `attachment`.

---

### Component 4: Ads Banner 10-Second Delay & Base-Page-Only Logic (`users/templates/users/_banner_popup.html` & Sub-templates)

#### [MODIFY] [users/templates/users/_banner_popup.html](file:///b:/ABCD/abcd_web/users/templates/users/_banner_popup.html)
- Update display trigger to wait **10 seconds** (`setTimeout(checkAndDisplayStudentBanner, 10000)`).
- Ensure dismissed/viewed banner IDs are stored in `localStorage` and sent to backend (`dismiss_student_banner_api`) so a user is never prompted more than once.

#### [MODIFY] Sub-page Templates
- Remove `{% include 'users/_banner_popup.html' %}` from sub-pages:
  - [`library_availability.html`](file:///b:/ABCD/abcd_web/users/templates/users/library_availability.html)
  - [`your_seat_status.html`](file:///b:/ABCD/abcd_web/users/templates/users/your_seat_status.html)
- Keep only on the primary base home pages:
  - [`student_dashboard.html`](file:///b:/ABCD/abcd_web/users/templates/users/student_dashboard.html)
  - [`alumni_dashboard.html`](file:///b:/ABCD/abcd_web/users/templates/users/alumni_dashboard.html)
  - [`guest_page.html`](file:///b:/ABCD/abcd_web/users/templates/users/guest_page.html)
  - [`home_page.html`](file:///b:/ABCD/abcd_web/users/templates/home_page.html)

---

### Component 5: Orphan Media Purge & Legacy Folder Deletion

#### [DELETE] [b:\ABCD\abcd_web\complaints](file:///b:/ABCD/abcd_web/complaints)
- Remove empty unused folder `complaints/` from root directory.

#### Safe Deletion of 30 Orphan Files in `media/`
- Delete the 30 identified orphaned files that have 0 references in the database (reclaiming **222.27 MB** of disk space immediately).

---

## 3. Verification Plan

### Automated Tests
- Run Django test suite:
  ```bash
  venv\Scripts\python.exe manage.py test users
  ```
- Add unit tests verifying:
  1. `Course` and `StudyMaterial` file deletions on cascade delete and update.
  2. Guidy group deletion lifecycle, member clearing, and early master purge when all members clear.
  3. `cleanup_complaint_images` purges images of complaints resolved >= 5 days ago.
  4. `cleanup_broadcasts` purges records & files older than 20 days.
  5. Banner API only returns unviewed banners and tracks views correctly.

### Manual Verification
- Test group creation, deletion by teacher, member view with countdown banner and "Delete" button.
- Verify orphan cleanup script results in 0 orphan files.
