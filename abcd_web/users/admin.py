from django.contrib import admin
from django.contrib.auth.models import User
from .models import (
    StudentProfile, Seat, Complaint, Payment, Notification, 
    BroadcastMessage, VisitorIntent, PushSubscription, Course, 
    CourseCategory, StudyMaterial, LearningReminder, StudentAchievement,
    GuidanceRequest, ChatSession, Message, BlockedGuidance,
    RestrictedStudent, GroupChatSession, GroupMessage
)


# -------------------------------------------------------------------
# LEARNING REMINDER ADMIN
# -------------------------------------------------------------------
@admin.register(LearningReminder)
class LearningReminderAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'title', 'reminder_time', 'is_sent')
    list_filter = ('is_sent', 'course')
    search_fields = ('user__username', 'title')

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
    search_fields = ('full_name', 'mobile_number', 'user__username')
    list_editable = ('status',)
    
    # Enable autocomplete for Seat (Foreign Key) and User
    autocomplete_fields = ['seat', 'user']

    fieldsets = (
        ('Account Information', {
            'fields': ('user', 'status', 'admission_type')
        }),
        ('Personal Information', {
            'fields': ('full_name', 'dob', 'sex', 'mobile_number', 'whatsapp_number', 'sex_other', 'photo')
        }),
        ('Service Details', {
            'fields': ('service_type', 'batch', 'seat', 'shift') 
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
# SEAT ADMIN (Fixed for new model structure)
# -------------------------------------------------------------------
@admin.register(Seat)
class SeatAdmin(admin.ModelAdmin):
    # 'student' field is gone. We use 'current_occupants' (method) and 'hold_student' (FK)
    list_display = (
        'seat_number', 
        'floor', 
        'status', 
        'is_shift_enabled', 
        'current_occupants', 
        'hold_status'
    )
    
    list_filter = ('floor', 'status', 'is_shift_enabled', 'hold_status')
    search_fields = ('seat_number',)
    
    # Use hold_student because that is the only FK to StudentProfile now
    autocomplete_fields = ['hold_student']

    def current_occupants(self, obj):
        # Reverse lookup for students sitting here
        students = obj.students.all()
        if not students:
            return "-"
        return ", ".join([f"{s.full_name} ({s.shift})" for s in students])
    
    current_occupants.short_description = "Occupied By"


# -------------------------------------------------------------------
# OTHER ADMINS
# -------------------------------------------------------------------

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('student', 'month', 'year', 'amount', 'date_paid')
    # student__seat__floor is valid because seat is now a FK in StudentProfile
    list_filter = ('year', 'month', 'student__service_type', 'student__seat__floor')
    search_fields = ('student__full_name', 'student__mobile_number')
    readonly_fields = ('date_paid',)


@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    list_display = ('student', 'subject', 'status', 'rating', 'created_at')
    list_filter = ('status', 'subject', 'rating')
    search_fields = ('student__full_name', 'message')
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


@admin.register(VisitorIntent)
class VisitorIntentAdmin(admin.ModelAdmin):
    list_display = ('user', 'intent_type', 'reminder_sent', 'resolved', 'created_at')
    list_filter = ('intent_type', 'reminder_sent', 'resolved')


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')


# -------------------------------------------------------------------
# COURSE & MATERIAL ADMINS (Fixed for Slug)
# -------------------------------------------------------------------

class StudyMaterialInline(admin.TabularInline):
    model = StudyMaterial
    extra = 1

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'playlist_id', 'video_count', 'is_active', 'target_public', 'target_coaching', 'target_alumni', 'target_library', 'target_private')
    inlines = [StudyMaterialInline]

@admin.register(CourseCategory)
class CourseCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    # This automatically fills the slug field based on the name
    prepopulated_fields = {'slug': ('name',)}


# -------------------------------------------------------------------
# STUDENT ACHIEVEMENT ADMIN
# -------------------------------------------------------------------
@admin.register(StudentAchievement)
class StudentAchievementAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'current_post', 'selection_year', 'status', 'rating', 'created_at')
    list_filter = ('status', 'selection_year', 'rating')
    search_fields = ('first_name', 'last_name', 'current_post', 'working_city')
    list_editable = ('status',)


# -------------------------------------------------------------------
# GUIDY ADMIN – Admin/Sandeep Sir can view & manage blocks/disputes
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
        """Admin action to unblock selected student-alumni pairs."""
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