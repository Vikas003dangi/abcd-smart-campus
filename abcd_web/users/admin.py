from django.contrib import admin
from django.contrib.auth.models import User
from .models import (
    StudentProfile, Seat, Complaint, Payment, Notification, 
    BroadcastMessage, BroadcastAttachment, VisitorIntent, PushSubscription, Course, 
    CourseCategory, StudyMaterial, LearningReminder, StudentAchievement,
    GuidanceRequest, ChatSession, DirectChatSession, Message, BlockedGuidance,
    RestrictedStudent, GroupChatSession, GroupMessage, GuidyBlock,
    TeacherProfile, SeatAssignment, SeatHoldRequest, SeatSwitchRequest, SeatSpecialRequest,
    FeeTransaction, DismissedFeeAlert, CourseReview, CourseQuestion, CourseAnswer,
    CourseShare, StudentMaterialAccess, StudentCourseInteraction,
    PerformanceRecord, StudentScore, TodoTask
)

admin.site.site_header = "ABCD Smart Campus • Master Administration"
admin.site.site_title = "ABCD Master Admin"
admin.site.index_title = "Master Database Control & System Architecture"


# -------------------------------------------------------------------
# TEACHER / STAFF PROFILE ADMIN
# -------------------------------------------------------------------
@admin.register(TeacherProfile)
class TeacherProfileAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'role_title', 'user', 'detail1', 'detail2', 'detail3')
    search_fields = ('display_name', 'role_title', 'user__username', 'user__email')
    autocomplete_fields = ['user']


# -------------------------------------------------------------------
# STUDENT PROFILE ADMIN
# -------------------------------------------------------------------
@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 
        'mobile_number', 
        'status', 
        'service_type', 
        'assigned_seat_info', 
        'shift',
        'admission_type'
    )
    list_filter = ('status', 'service_type', 'batch', 'shift', 'admission_type', 'seat__floor')
    search_fields = ('full_name', 'mobile_number', 'user__username', 'user__email')
    list_editable = ('status',)
    autocomplete_fields = ['seat', 'user']

    fieldsets = (
        ('Account Information', {
            'fields': ('user', 'status', 'admission_type', 'is_admitted', 'is_manual_pending')
        }),
        ('Personal Information', {
            'fields': ('full_name', 'dob', 'sex', 'mobile_number', 'whatsapp_number', 'sex_other', 'photo', 'email')
        }),
        ('Service Details', {
            'fields': ('service_type', 'batch', 'seat', 'shift', 'fee_expiry_date') 
        }),
    )

    def assigned_seat_info(self, obj):
        if obj.seat:
            return f"{obj.seat.seat_number} ({obj.seat.floor})"
        return "-"
    assigned_seat_info.short_description = "Seat"

    def delete_model(self, request, obj):
        if obj.user:
            obj.user.delete()
        else:
            obj.delete()

    def delete_queryset(self, request, queryset):
        user_ids = queryset.filter(user__isnull=False).values_list('user_id', flat=True)
        if user_ids:
            User.objects.filter(pk__in=list(user_ids)).delete()
        queryset.delete()


# -------------------------------------------------------------------
# SEAT & SEAT ASSIGNMENT ADMINS
# -------------------------------------------------------------------
@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    list_display = (
        'seat_number', 
        'floor', 
        'status', 
        'is_shift_enabled', 
        'current_occupants', 
        'hold_status',
        'is_locked'
    )
    list_filter = ('floor', 'status', 'is_shift_enabled', 'hold_status', 'is_locked')
    search_fields = ('seat_number',)
    list_editable = ('status', 'is_shift_enabled', 'is_locked')
    autocomplete_fields = ['hold_student']

    def current_occupants(self, obj):
        students = obj.students.all()
        if not students:
            return "-"
        return ", ".join([f"{s.full_name} ({s.shift})" for s in students])
    current_occupants.short_description = "Occupied By"


@admin.register(SeatAssignment)
class SeatAssignmentAdmin(admin.ModelAdmin):
    list_display = ('seat', 'student', 'shift_type', 'is_active', 'is_partial', 'hold_status', 'hold_start_date', 'hold_end_date')
    list_filter = ('shift_type', 'is_active', 'is_partial', 'hold_status', 'seat__floor')
    search_fields = ('student__full_name', 'student__mobile_number', 'seat__seat_number')
    autocomplete_fields = ['seat', 'student']


@admin.register(SeatHoldRequest)
class SeatHoldRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'seat', 'start_date', 'duration_text', 'status', 'cancel_requested', 'created_at')
    list_filter = ('status', 'cancel_requested', 'seat__floor')
    search_fields = ('student__full_name', 'seat__seat_number')


@admin.register(SeatSwitchRequest)
class SeatSwitchRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'target_seat', 'target_shift', 'status', 'created_at')
    list_filter = ('status', 'target_shift')
    search_fields = ('student__full_name',)

# -------------------------------------------------------------------
# COURSE, STUDY MATERIAL & REVIEW ADMINS
# -------------------------------------------------------------------
class StudyMaterialInline(admin.TabularInline):
    model = StudyMaterial
    extra = 1

@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'order', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('order', 'is_active')

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'playlist_id', 'video_count', 'is_active', 'target_public', 'target_coaching', 'target_library')
    list_filter = ('is_active', 'target_public', 'target_coaching', 'target_library', 'category')
    search_fields = ('title', 'description', 'playlist_id')
    list_editable = ('is_active',)
    inlines = [StudyMaterialInline]

@admin.register(StudyMaterial)
class StudyMaterialAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'material_type', 'is_public', 'created_at')
    list_filter = ('material_type', 'is_public', 'course')
    search_fields = ('title', 'course__title')
    list_editable = ('is_public',)

@admin.register(CourseReview)
class CourseReviewAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'guest_name', 'rating', 'comment', 'created_at')
    list_filter = ('rating', 'course')
    search_fields = ('course__title', 'student__full_name', 'guest_name', 'comment')

@admin.register(CourseQuestion)
class CourseQuestionAdmin(admin.ModelAdmin):
    list_display = ('course', 'student', 'question', 'is_resolved', 'created_at')
    list_filter = ('is_resolved', 'course')
    search_fields = ('course__title', 'student__full_name', 'question')

@admin.register(CourseAnswer)
class CourseAnswerAdmin(admin.ModelAdmin):
    list_display = ('question', 'user', 'answer_text', 'is_teacher_answer', 'created_at')
    list_filter = ('is_teacher_answer',)
    search_fields = ('user__username', 'answer_text')


# -------------------------------------------------------------------
# PERFORMANCE & STUDENT MARKS ADMIN
# -------------------------------------------------------------------
@admin.register(PerformanceRecord)
class PerformanceRecordAdmin(admin.ModelAdmin):
    list_display = ('batch', 'topic', 'total_marks', 'created_at')
    list_filter = ('batch', 'created_at')
    search_fields = ('batch', 'topic')

@admin.register(StudentScore)
class StudentScoreAdmin(admin.ModelAdmin):
    list_display = ('student', 'record', 'marks_obtained')
    search_fields = ('student__full_name', 'record__topic')
    autocomplete_fields = ['student', 'record']


# -------------------------------------------------------------------
# FINANCIAL PAYMENTS & FEE TRANSACTIONS
# -------------------------------------------------------------------
@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('student', 'month', 'year', 'amount', 'date_paid')
    list_filter = ('year', 'month', 'student__service_type', 'student__seat__floor')
    search_fields = ('student__full_name', 'student__mobile_number')
    readonly_fields = ('date_paid',)

@admin.register(FeeTransaction)
class FeeTransactionAdmin(admin.ModelAdmin):
    list_display = ('student', 'total_amount', 'receipt_number', 'payment_date', 'expiry_date')
    list_filter = ('payment_date', 'expiry_date')
    search_fields = ('student__full_name', 'receipt_number')

@admin.register(DismissedFeeAlert)
class DismissedFeeAlertAdmin(admin.ModelAdmin):
    list_display = ('teacher', 'student', 'expiry_date', 'created_at')
    list_filter = ('expiry_date', 'created_at')
    search_fields = ('teacher__username', 'student__full_name')


# -------------------------------------------------------------------
# COMPLAINTS, SUPPORT & NOTIFICATIONS
# -------------------------------------------------------------------
@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'status', 'role', 'rating', 'created_at')
    list_filter = ('status', 'subject', 'role', 'rating')
    search_fields = ('student__full_name', 'message', 'custom_subject')
    list_editable = ('status',)
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'category', 'is_read', 'created_at')
    list_filter = ('category', 'is_read')
    search_fields = ('user__username', 'title')

@admin.register(BroadcastMessage)
class BroadcastMessageAdmin(admin.ModelAdmin):
    list_display = ('subject', 'sender', 'target_group', 'status', 'created_at')
    list_filter = ('target_group', 'status')
    search_fields = ('subject', 'message')

@admin.register(BroadcastAttachment)
class BroadcastAttachmentAdmin(admin.ModelAdmin):
    list_display = ('broadcast', 'file', 'created_at')

@admin.register(VisitorIntent)
class VisitorIntentAdmin(admin.ModelAdmin):
    list_display = ('user', 'intent_type', 'reminder_sent', 'resolved', 'created_at')
    list_filter = ('intent_type', 'reminder_sent', 'resolved')

@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')


# -------------------------------------------------------------------
# STUDENT ACHIEVEMENTS & REMINDERS
# -------------------------------------------------------------------
@admin.register(StudentAchievement)
class StudentAchievementAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'current_post', 'selection_year', 'status', 'rating', 'created_at')
    list_filter = ('status', 'selection_year', 'rating')
    search_fields = ('first_name', 'last_name', 'current_post', 'working_city')
    list_editable = ('status',)

@admin.register(LearningReminder)
class LearningReminderAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'title', 'reminder_time', 'is_sent')
    list_filter = ('is_sent', 'course')
    search_fields = ('user__username', 'title')

@admin.register(TodoTask)
class TodoTaskAdmin(admin.ModelAdmin):
    list_display = ('user', 'category', 'is_done', 'is_pinned', 'created_at')
    list_filter = ('category', 'is_done', 'is_pinned')
    search_fields = ('user__username', 'category')
    list_editable = ('is_done', 'is_pinned')


# -------------------------------------------------------------------
# GUIDY & CHAT SESSIONS ADMIN
# -------------------------------------------------------------------
@admin.register(GuidanceRequest)
class GuidanceRequestAdmin(admin.ModelAdmin):
    list_display = ('student', 'alumni', 'status', 'created_at')
    list_filter = ('status',)
    search_fields = ('student__username', 'alumni__first_name', 'alumni__last_name')
    readonly_fields = ('student', 'alumni', 'created_at', 'updated_at')

@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'is_active', 'created_at')
    list_filter = ('is_active',)
    readonly_fields = ('request', 'created_at')

@admin.register(DirectChatSession)
class DirectChatSessionAdmin(admin.ModelAdmin):
    list_display = ('user1', 'user2', 'is_active', 'created_at', 'session_ended_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('user1__username', 'user2__username')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('session', 'sender', 'content_preview', 'timestamp', 'is_read')
    list_filter = ('is_read',)
    search_fields = ('sender__username', 'content')
    readonly_fields = ('session', 'sender', 'timestamp')

    def content_preview(self, obj):
        return obj.content[:60]
    content_preview.short_description = "Content"

@admin.register(BlockedGuidance)
class BlockedGuidanceAdmin(admin.ModelAdmin):
    list_display = ('alumni', 'student', 'created_at')
    search_fields = ('alumni__first_name', 'alumni__last_name', 'student__username')
    readonly_fields = ('alumni', 'student', 'created_at')
    actions = ['unblock_selected']

    def unblock_selected(self, request, queryset):
        count = queryset.count()
        queryset.delete()
        self.message_user(request, f"✅ Successfully unblocked {count} pair(s).")
    unblock_selected.short_description = "Unblock selected student-alumni pairs"

@admin.register(RestrictedStudent)
class RestrictedStudentAdmin(admin.ModelAdmin):
    list_display = ('alumni', 'student', 'reason', 'created_at')
    search_fields = ('alumni__first_name', 'alumni__last_name', 'student__username')
    readonly_fields = ('created_at',)

@admin.register(GroupChatSession)
class GroupChatSessionAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'created_by__username')
    readonly_fields = ('created_at',)

@admin.register(GroupMessage)
class GroupMessageAdmin(admin.ModelAdmin):
    list_display = ('group', 'sender', 'content_preview', 'timestamp')
    search_fields = ('group__name', 'sender__username', 'content')
    readonly_fields = ('timestamp',)

    def content_preview(self, obj):
        return obj.content[:60]
    content_preview.short_description = "Content"

@admin.register(GuidyBlock)
class GuidyBlockAdmin(admin.ModelAdmin):
    list_display = ('blocker', 'blocked', 'created_at')
    search_fields = ('blocker__username', 'blocked__username')