# users/urls.py
from django.urls import path
from . import views

app_name = "users"

urlpatterns = [
    # ============================
    # Main Site & Authentication
    # ============================
    path('', views.home_page_view, name='home_page'),
    path('about/', views.about_us_view, name='about_us'),
    path('services/', views.services_view, name='services'),
    path('contact/', views.contact_view, name='contact'),
    
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),

    # Forgot password (email + OTP flow)
    path('forgot-password/', views.forgot_password_request, name='forgot_password'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('reset-password/', views.reset_password_view, name='reset_password'),

    # Post-login routing (normal + Google)
    path('post-login/', views.post_login_router, name='post_login_router'),
    path('smart-back/', views.smart_back_router, name='smart_back_router'),

    # ============================
    # Admission & Public
    # ============================

    path('admission-form/', views.admission_form_view, name='admission_form'),
    path('guest-home/', views.guest_page_view, name='guest_page'),

    path('library-availability/', views.library_availability_view, name='library_availability'),
    path('resolved-complaints/', views.public_resolved_complaints, name='public_resolved_complaints'),

    
    # ============================
    # Student Dashboard
    # ============================
    path('dashboard/', views.student_dashboard_view, name='student_dashboard'),
    path('alumni/dashboard/', views.alumni_dashboard_view, name='alumni_dashboard'),
    path('my-details/', views.student_details_S_view, name='student_details_S'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/guest/', views.guest_profile_details_view, name='guest_profile_details'),
    path('profile/change-password/', views.change_password_view, name='change_password'),
    path('profile/otp-status/', views.otp_status_view, name='otp_status'),
    path('my-seat/', views.your_seat_status_view, name='your_seat_status'),

    # Student complaints
    path("complaints/", views.student_complaints_view, name="student_complaints"),
    path("student/complaints/", views.student_complaints_view, name="student_complaints_alias"),
    path("complaints/success/<int:complaint_id>/", views.student_complaints_success_view, name="student_complaints_success"),
    path("complaints/rate/<int:complaint_id>/", views.submit_complaint_rating, name="complaint_rate"),
    
    path('api/complaint-ratings/', views.complaint_ratings_api, name='complaint_ratings_api'),

    # Notfications Mark as view
    path("notifications/mark-read/", views.mark_notifications_read, name="mark_notifications_read"),
    
    # ---------------------------------------------
    # Courses and Study Materials (Public/Students)
    path("courses/", views.courses_view, name="courses"),
    path("courses/<int:course_id>/", views.course_detail_view, name="course_detail"),
    
    # Download material
    path("materials/download/<int:material_id>/",views.download_study_material_view,name="download_study_material"),

    # ============================
    # Teacher Dashboard
    # ============================
    path('teacher/', views.teacher_dashboard_view, name='teacher_dashboard'),
    path('api/teacher/live-stats/', views.teacher_live_stats_api, name='teacher_live_stats_api'),

    # Students CRED
    path('teacher/student/<int:student_id>/', views.student_details_view, name='student_details'),
    path('teacher/student/<int:student_id>/edit/', views.edit_student_view, name='edit_student'),
    path('teacher/student/<int:student_id>/approve/', views.approve_student_view, name='approve_student'),
    path('teacher/student/<int:student_id>/delete/', views.delete_student_view, name='delete_student'),
    
    # Photo Management
    path('student/<int:student_id>/photo/upload/', views.upload_profile_photo, name='upload_profile_photo'),
    path('student/<int:student_id>/photo/delete/', views.delete_profile_photo, name='delete_profile_photo'),

    # ---------------------
    # Update complaint status
    path("teacher/complaints/<int:complaint_id>/status/",views.update_complaint_status_view,name="update_complaint_status"),

    # Delete complaint
    path('teacher/complaint/delete/<int:complaint_id>/', views.delete_complaint, name='delete_complaint'),  
    # ---------------------

    # ---------------------
    # Seat Management
    path('teacher/seat-status/', views.teacher_seat_status_view, name='teacher_seat_status'),
    path('teacher/seat-manager/', views.teacher_seat_status_view, name='teacher_seat_manager'),

    # ---------------------
    # Fee Management
    path('teacher/student/<int:student_id>/fees/', views.fee_calendar_view, name='fee_calendar'),
    path('api/process_fees/<int:student_id>/', views.process_fees_view, name='process_fees'),
    path('api/delete_payment/<int:student_id>/<int:year>/<str:month_name>/', views.delete_payment_view, name='delete_payment'),
    path('teacher/dismiss-fee-expired/', views.dismiss_fee_expired_alerts, name='dismiss_fee_expired_alerts'),

    # ---------------------
    # | Course Management |
    # ---------------------
    # Dashboard: list & manage all courses
    path("teacher/courses/",views.teacher_courses_view,name="teacher_courses"),

    # Sync courses from YouTube playlists and Add more Course
    path("teacher/courses/sync/",views.sync_courses_view,name="sync_courses"),
    path("teacher/courses/add/", views.add_course_view, name="add_course"),

    # YouTube Sync Wizard API
    path("api/yt/playlists/", views.yt_fetch_playlists_api, name="yt_fetch_playlists"),
    path("api/yt/videos/", views.yt_fetch_videos_api, name="yt_fetch_videos"),
    path("api/yt/import-playlist/", views.yt_import_playlist_api, name="yt_import_playlist"),
    path("api/yt/create-custom-course/", views.yt_create_custom_course_api, name="yt_create_custom_course"),

    # Manage study materials for a course
    path("teacher/courses/<int:course_id>/materials/",views.teacher_course_materials_view,name="teacher_course_materials"),

    #add more material in course
    path("teacher/courses/<int:course_id>/materials/add/", views.add_material_view, name="add_material"),
    path("teacher/courses/<int:course_id>/materials/bulk-update/", views.bulk_update_materials, name="bulk_update_materials"),
    path("teacher/materials/<int:material_id>/edit/", views.edit_material_view, name="edit_material"),
    
    # Toggle Course active / inactive
    path("teacher/courses/<int:course_id>/toggle/",views.toggle_course_status,name="toggle_course_status"),
    path("teacher/courses/<int:course_id>/edit/",views.edit_course_view,name="edit_course"),
    path("teacher/courses/<int:course_id>/preview/", views.teacher_course_preview_view, name="teacher_course_preview"),

    # Delete Course and Study Materials
    path("teacher/courses/<int:course_id>/delete/",views.delete_course,name="delete_course"),
    path("teacher/courses/materials/delete/<int:material_id>/",views.delete_study_material,name="delete_study_material"),

    # ---------------------
    # Teacher Broadcast Message and its history record 
    path("teacher/broadcast/", views.teacher_broadcast_view, name="teacher_broadcast"),
    path("teacher/broadcast/delete/<int:pk>/", views.delete_broadcast_view, name="delete_broadcast"),
    path("teacher/broadcast/bulk-delete/", views.bulk_delete_broadcasts_view, name="bulk_delete_broadcasts"),
    path("teacher/broadcast/history/", views.broadcast_history_view, name="broadcast_history"),
    path("teacher/broadcast/drafts/", views.get_drafts_api, name="get_drafts_api"),
    path("teacher/broadcast/resend/<int:broadcast_id>/", views.resend_failed_broadcast, name="resend_failed_broadcast"),
    path("api/student/active-banner/", views.get_active_student_banner_api, name="get_active_student_banner_api"),
    path("api/student/banner/dismiss/<int:banner_id>/", views.dismiss_student_banner_api, name="dismiss_student_banner_api"),
    
    # Student Progress
    path("teacher/progress/", views.student_progress_view, name="student_progress"),

    # Visitor Insights
    path("teacher/visitor-insights/", views.visitor_insights_view, name="visitor_insights"),
    # Clear Visitor Intents
    path("teacher/visitor-insights/clear/", views.clear_visitor_intents, name="clear_visitor_intents"),
    path("teacher/visitor-insights/delete-selected/", views.delete_selected_visitor_intents, name="delete_selected_visitor_intents"),
    
    # Fees Record (Accounting History)
    path("teacher/fees-record/", views.fees_record_view, name="fees_record"),
    path("teacher/fees-record/bulk-delete/", views.bulk_delete_fees_action, name="bulk_delete_fees"),
    path("teacher/fees-record/download/<int:transaction_id>/", views.download_fee_receipt_view, name="download_fee_receipt"),
    path("teacher/fee-receipt/download/<int:transaction_id>/", views.download_fee_receipt_view),

    # ======================================================
    # ALL API URLs
    # ======================================================

    # Public + admission form (used by admission-seat-selector.js)
    path('api/get_public_seat_status/', views.get_public_seat_status_api, name='api_get_public_seat_status'),
    path('api/get-public-seat-status/', views.get_public_seat_status_api),
    path('api/gpt-public-seat-status/', views.get_public_seat_status_api),

    # API to record seat interest from public users
    path("api/seat-interest/", views.seat_interest_api, name="seat_interest_api"),

    # Toggle material privacy
    path("api/toggle-material-privacy/<int:material_id>/", views.toggle_material_privacy, name="toggle_material_privacy"),
    
    # Student dashboard APIs
    path('api/get_seat_status/', views.get_seat_status_api, name='api_get_seat_status'),
    path('api/request_seat_hold/', views.request_seat_hold_api, name='api_request_seat_hold'),
    path('api/request_seat_switch/', views.request_seat_switch_api, name='api_request_seat_switch'),
    path('api/cancel_seat_switch/', views.cancel_seat_switch_api, name='api_cancel_seat_switch'),

    # Teacher dashboard / seat manager APIs
    path('api/get_teacher_seat_status/', views.get_teacher_seat_status_api, name='api_get_teacher_seat_status'),
    path('api/get_student_list/', views.get_student_list_api, name='api_get_student_list'),
    path('api/teacher/seat_action/', views.seat_action_api, name='api_seat_action'),
    path('api/toggle_seat_lock/', views.toggle_seat_lock_api, name='api_toggle_seat_lock'),
    path('api/manage_hold_request/', views.manage_hold_request_api, name='api_manage_hold_request'),

    path('api/teacher/put_seat_on_hold/', views.teacher_put_seat_on_hold_api, name='api_teacher_put_seat_on_hold'),
    path('api/update_contact_info/', views.update_contact_info_api, name='api_update_contact_info'),
    path('teacher/seat_switch/<int:pk>/approve/', views.approve_seat_switch, name='approve_seat_switch'),
    path('teacher/seat_switch/<int:pk>/reject/', views.reject_seat_switch, name='reject_seat_switch'),

    # Push Notification Subscription API
    path("api/save-push-subscription/", views.save_push_subscription, name="save_push_subscription"),

    # Seat Special Request API
    path(
        'api/seat-special-request/',
        views.send_special_seat_request_api,
        name='seat_special_request_api'
    ),

    # Engagement Tracking API
    path('api/track-engagement/', views.track_engagement_api, name='track_engagement_api'),

    # Interactive Course APIs
    path('api/courses/<int:course_id>/review/', views.submit_course_review, name='submit_course_review'),
    path('api/courses/<int:course_id>/reminder/', views.save_learning_reminder, name='save_learning_reminder'),
    path('api/reminders/<int:reminder_id>/delete/', views.delete_learning_reminder, name='delete_learning_reminder'),
    path('api/courses/<int:course_id>/question/', views.submit_course_question, name='submit_course_question'),
    path('api/questions/<int:question_id>/answer/', views.submit_course_answer, name='submit_course_answer'),
    path('api/qa/upvote/', views.upvote_qa_api, name='upvote_qa_api'),
    path('api/qa/delete/', views.delete_qa_item, name='delete_qa_item'),
    path('api/reminders/due/', views.get_due_reminders, name='get_due_reminders'),
    path('api/courses/<int:course_id>/interaction/', views.toggle_course_interaction, name='toggle_course_interaction'),

    # ======================================================
    # STUDENT ACHIEVEMENTS & ALUMNI (HALL OF FAME)
    # ======================================================
    path('alumni/edit/', views.edit_alumni_view, name='edit_alumni'),
    path('achievement-form/', views.achievement_form_view, name='achievement_form'),
    path('hall-of-fame/', views.hall_of_fame_view, name='hall_of_fame'),
    path('achievement/<int:pk>/', views.achievement_detail_view, name='achievement_detail'),
    path('achievement/delete/<int:pk>/', views.delete_achievement, name='delete_achievement'),
    
    # Teacher Management
    path('teacher/achievements/<int:pk>/approve/', views.approve_achievement, name='approve_achievement'),
    path('teacher/achievements/<int:pk>/reject/', views.reject_achievement, name='reject_achievement'),

    # ======================================================
    # GUIDY – PRIVATE MENTORSHIP MESSAGING
    # ======================================================
    path('guidy/', views.guidy_home, name='guidy_home'),
    path('guidy/seek/<int:alumni_pk>/', views.guidy_seek_guidance, name='guidy_seek'),
    path('guidy/respond/<int:request_pk>/', views.guidy_respond, name='guidy_respond'),
    path('guidy/restrict/<int:request_pk>/', views.guidy_restrict_student, name='guidy_restrict'),
    path('guidy/status/<int:alumni_pk>/', views.guidy_check_status, name='guidy_check_status'),
    path('guidy/heartbeat/', views.guidy_heartbeat, name='guidy_heartbeat'),

    # 1-to-1 Chat
    path('guidy/chat/<int:session_id>/send/', views.guidy_send_message, name='guidy_send_message'),
    path('guidy/chat/<int:session_id>/poll/', views.guidy_poll_messages, name='guidy_poll'),
    path('guidy/chat/<int:session_id>/end/', views.guidy_end_session, name='guidy_end_session'),
    path('guidy/chat/<int:session_id>/msg/<int:msg_id>/delete/', views.guidy_delete_message, name='guidy_delete_msg'),
    path('guidy/chat/<int:session_id>/msg/<int:msg_id>/pin/', views.guidy_pin_message, name='guidy_pin_msg'),
    path('guidy/chat/<int:session_id>/msg/<int:msg_id>/star/', views.guidy_star_message, name='guidy_star_msg'),
    path('guidy/chat/<int:session_id>/search/', views.guidy_search_messages, name='guidy_search_msgs'),
    path('guidy/chat/<int:session_id>/clear/', views.guidy_clear_chat, name='guidy_clear_chat'),
    path('guidy/chat/<int:session_id>/delete-permanent/', views.guidy_delete_session_permanently, name='guidy_delete_session_permanently'),

    # 1-to-1 Direct Chat (standalone model)
    path('guidy/direct/<int:direct_id>/send/', views.guidy_send_message, name='guidy_send_message_direct'),
    path('guidy/direct/<int:direct_id>/poll/', views.guidy_poll_messages, name='guidy_poll_direct'),
    path('guidy/direct/<int:direct_id>/end/', views.guidy_end_session, name='guidy_end_session_direct'),
    path('guidy/direct/<int:direct_id>/msg/<int:msg_id>/delete/', views.guidy_delete_message, name='guidy_delete_msg_direct'),
    path('guidy/direct/<int:direct_id>/msg/<int:msg_id>/pin/', views.guidy_pin_message, name='guidy_pin_msg_direct'),
    path('guidy/direct/<int:direct_id>/msg/<int:msg_id>/star/', views.guidy_star_message, name='guidy_star_msg_direct'),
    path('guidy/direct/<int:direct_id>/search/', views.guidy_search_messages, name='guidy_search_msgs_direct'),
    path('guidy/direct/<int:direct_id>/clear/', views.guidy_clear_chat, name='guidy_clear_chat_direct'),
    path('guidy/direct/<int:direct_id>/delete-permanent/', views.guidy_delete_session_permanently, name='guidy_delete_session_permanently_direct'),

    path('guidy/load-older/', views.guidy_load_older, name='guidy_load_older'),
    path('guidy/chat-data/', views.guidy_load_chat_api, name='guidy_load_chat_api'),
    path('guidy/sessions/bulk-end/', views.guidy_bulk_end_sessions, name='guidy_bulk_end_sessions'),
    path('guidy/chats/bulk-clear/', views.guidy_bulk_clear_chats, name='guidy_bulk_clear_chats'),

    # Profile info drawer
    path('guidy/profile/<str:entity_type>/<int:entity_id>/', views.guidy_profile_info, name='guidy_profile_info'),

    # Group Chat
    path('guidy/groups/create/', views.guidy_create_group, name='guidy_create_group'),
    path('guidy/groups/<int:group_id>/send/', views.guidy_group_send_message, name='guidy_group_send'),
    path('guidy/groups/<int:group_id>/poll/', views.guidy_group_poll, name='guidy_group_poll'),
    path('guidy/groups/<int:group_id>/settings/update/', views.guidy_group_update_settings, name='guidy_group_update_settings'),
    path('guidy/groups/<int:group_id>/members/manage/', views.guidy_group_manage_members, name='guidy_group_manage_members'),
    path('guidy/groups/<int:group_id>/delete-for-user/', views.guidy_delete_group_for_user, name='guidy_delete_group_for_user'),
    path('guidy/contacts/', views.guidy_contacts_api, name='guidy_contacts_api'),
    path('guidy/teacher/direct-chat/', views.guidy_teacher_direct_chat, name='guidy_teacher_direct_chat'),
    path('guidy/profile/teacher/update/', views.guidy_update_teacher_profile, name='guidy_update_teacher_profile'),
    path('guidy/groups/<int:group_id>/search/', views.guidy_search_group_messages, name='guidy_search_group_msgs'),
    path('guidy/groups/<int:group_id>/clear/', views.guidy_group_clear_chat, name='guidy_group_clear_chat'),
    path('guidy/groups/<int:group_id>/msg/<int:msg_id>/delete/', views.guidy_delete_message, name='guidy_delete_msg_group'),
    path('guidy/groups/<int:group_id>/msg/<int:msg_id>/pin/', views.guidy_pin_message, name='guidy_pin_msg_group'),
    path('guidy/groups/<int:group_id>/msg/<int:msg_id>/star/', views.guidy_star_message, name='guidy_star_msg_group'),
    path('guidy/block/<int:user_id>/', views.guidy_block_user, name='guidy_block_user'),
    path('guidy/unblock/<int:user_id>/', views.guidy_unblock_user, name='guidy_unblock_user'),
    path('guidy/blocked-list/', views.guidy_blocked_list, name='guidy_blocked_list'),

    # ======================================================
    # NOTIFICATION MANAGEMENT
    # ======================================================
    path('notifications/delete/<int:notification_id>/', views.delete_notification_view, name='delete_notification'),
    path('notifications/mark-all-read/', views.mark_all_notifications_read_view, name='mark_all_notifications_read'),
    path('notifications/bulk-delete/', views.bulk_delete_notifications_view, name='bulk_delete_notifications'),
    path('api/notifications/', views.notifications_api_view, name='notifications_api'),
    path('notifications/mark-unread/<int:notification_id>/', views.mark_notification_unread_view, name='mark_notification_unread'),

    # ─────────────────────────────────────────────────────────────────────────────
    # TO-DO HUB (Isolated Buffer)
    # ─────────────────────────────────────────────────────────────────────────────
    path('todo/', views.todo_hub_page, name='todo_hub'),
    path('todo/search-students/', views.todo_search_students, name='todo_search_students'),
    path('todo/add-fee-reminder/', views.todo_add_fee_reminder, name='todo_add_fee_reminder'),
    path('todo/get-tasks/', views.todo_get_tasks, name='todo_get_tasks'),
    path('todo/trash/<int:task_id>/', views.todo_trash_task, name='todo_trash_task'),
    path('todo/recover/<int:task_id>/', views.todo_recover_task, name='todo_recover_task'),
    path('todo/delete/<int:task_id>/', views.todo_permanent_delete_task, name='todo_permanent_delete_task'),
    path('todo/update/<int:task_id>/', views.todo_update_task, name='todo_update_task'),
    path('todo/add-breakdown/', views.todo_add_breakdown, name='todo_add_breakdown'),
    path('todo/add-todo/', views.todo_add_todo_task, name='todo_add_todo'),
    path('todo/add-note/', views.todo_add_note_task, name='todo_add_note'),
    path('todo/update-metadata/<int:task_id>/', views.todo_update_metadata, name='todo_update_metadata'),
    path('todo/bulk-action/', views.todo_bulk_action, name='todo_bulk_action'),
    path('todo/add-reminder/', views.todo_add_reminder, name='todo_add_reminder'),
    path('todo/update-reminder/<int:task_id>/', views.todo_update_reminder, name='todo_update_reminder'),
]