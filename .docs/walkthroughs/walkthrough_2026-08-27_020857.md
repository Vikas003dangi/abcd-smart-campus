# Walkthrough: Storage Management, Media Lifecycles & Group Deletion

We have implemented an end-to-end server storage management system to ensure that media, documents, chat attachments, and unused files are automatically cleaned up from disk to minimize server storage costs.

---

## Key Modules & Implementations

### 1. 5-Day Resolved Complaints Image Cleanup
- **Management Command**: [`users/management/commands/cleanup_complaint_images.py`](file:///b:/ABCD/abcd_web/users/management/commands/cleanup_complaint_images.py)
  - Targets resolved complaints older than 5 days (`resolved_at <= now - 5 days`).
  - Physically deletes `image1`, `image2`, `image3` files from `media/complaints/` and sets their database fields to `None`.
  - Integrated into the daily maintenance block of [`run_local_scheduler.py`](file:///b:/ABCD/abcd_web/users/management/commands/run_local_scheduler.py).

### 2. Guidy 10-Day Chat Attachment Purge
- **Purge Function**: `purge_expired_media()` in [`users/views.py`](file:///b:/ABCD/abcd_web/users/views.py)
  - Scans `Message` and `GroupMessage` records with files older than 10 days.
  - Physically deletes files from disk (`media/guidy_temp/`), clears file references, and flags `media_expired = True`.
  - Runs automatically on the daily scheduler loop.

### 3. Guidy Group Deletion & Early Master Purge Lifecycle
- **Database Schema**: [`users/models.py`](file:///b:/ABCD/abcd_web/users/models.py) (Migration `0107_groupchatsession_deleted_at_and_more.py`)
  - Added `deleted_at`, `deleted_by_user`, and `deleted_for_users` ManyToMany field on `GroupChatSession`.
- **Master Deletion Trigger**:
  - When an admin or teacher deletes the group in [`guidy_group_manage_members`](file:///b:/ABCD/abcd_web/users/views.py):
    - Sets `group.is_active = False`, `deleted_by_user = request.user`, `deleted_at = timezone.now()`.
    - Adds the deleter to `group.deleted_for_users` (immediately removing the group from the deleter's active chat list).
    - Posts a system message to the group.
- **Member Experience & Banner Alert** ([`users/templates/users/guidy.html`](file:///b:/ABCD/abcd_web/users/templates/users/guidy.html)):
  - Other group members see a warning banner: *"You are no longer a part of this group. The group was deleted by {deleter_name}. All messages and media will automatically be purged in {days_left} days."*
  - The chat input area is locked/disabled.
  - A prominent **"Delete Group"** button is displayed.
- **Early Master Purge**:
  - Member deletion endpoint: `guidy_delete_group_for_user` ([`users/views.py`](file:///b:/ABCD/abcd_web/users/views.py)).
  - When each member clicks "Delete Group", they are added to `group.deleted_for_users`.
  - **Early Purge Condition**: If all members delete the group from their ends (`deleted_for_users.count() >= members.count()`), `purge_group_chat_session(group)` triggers immediately, permanently deleting all group messages, attachments, avatars, and the group row from the database without waiting for the 30-day cutoff!
  - 30-day auto-purge runs via `purge_expired_group_chats()` in the daily scheduler.

### 4. Broadcasts & Banners 20-Day Cleanup & Display Timing
- **20-Day Auto Cleanup**: [`users/management/commands/cleanup_broadcasts.py`](file:///b:/ABCD/abcd_web/users/management/commands/cleanup_broadcasts.py)
  - Deletes broadcast records older than 20 days and physically deletes attached banner images and files.
  - Added to daily scheduler in [`run_local_scheduler.py`](file:///b:/ABCD/abcd_web/users/management/commands/run_local_scheduler.py).
- **Banner Display Fix** ([`users/templates/users/_banner_popup.html`](file:///b:/ABCD/abcd_web/users/templates/users/_banner_popup.html)):
  - Removed `{% include 'users/_banner_popup.html' %}` from sub-pages ([`library_availability.html`](file:///b:/ABCD/abcd_web/users/templates/users/library_availability.html), [`your_seat_status.html`](file:///b:/ABCD/abcd_web/users/templates/users/your_seat_status.html)). Kept ONLY on base home/dashboards.
  - Added **10-second gap/delay** (`setTimeout(checkAndDisplayStudentBanner, 10000)`).
  - Persists dismissal in `sessionStorage` and `localStorage` and logs via server API to ensure the banner is shown only once per user.

### 5. Course & Study Material Storage Cascade Deletion
- **Signals** ([`users/models.py`](file:///b:/ABCD/abcd_web/users/models.py)):
  - `auto_delete_file_on_change` (`pre_save`): Physically deletes the old file immediately when a thumbnail or material file is updated/replaced.
  - `auto_delete_file_on_delete` (`post_delete`): Physically deletes files on disk when a `StudyMaterial` is deleted.
  - `auto_delete_course_files_on_delete` (`post_delete`): Cascades when a `Course` is deleted, physically removing the course thumbnail and all associated study material files and thumbnails from disk.

### 6. Duplicate Folder Removal & Orphan Media Audit
- Removed redundant empty folder [`b:\ABCD\abcd_web\complaints`](file:///b:/ABCD/abcd_web/complaints).
- Compared active database file records against physical disk files: safely deleted **30 unreferenced orphan files** (including legacy videos, duplicate thumbnails, and unlinked student photos), immediately recovering **222.27 MB** of disk space.

---

## Verification & Automated Tests

All 15 automated test cases passed cleanly:
```bash
venv\Scripts\python.exe manage.py test users
```

**Test Results:**
- `test_complaint_image_cleanup_after_5_days`: PASSED
- `test_broadcast_cleanup_after_20_days`: PASSED
- `test_guidy_chat_media_purge_10_days`: PASSED
- `test_guidy_group_deletion_lifecycle_and_early_purge`: PASSED
- `test_edit_student_profile_preserves_user_email`: PASSED
- `test_update_contact_info_api_preserves_user_email`: PASSED
- `test_student_profile_form_initial_email_prepopulation`: PASSED
- `test_course_and_interaction_lifecycle`: PASSED
- `test_pending_student_course_access_and_guest_behavior`: PASSED
- `test_seat_hold_and_auto_promotion_flow`: PASSED
- `test_birthday_wishes_and_auto_attendance`: PASSED

**Result:** `Ran 15 tests in 7.916s - OK`
