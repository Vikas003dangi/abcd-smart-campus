# users/models.py
from django.conf import settings
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import os
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save, pre_save, post_delete
from django.dispatch import receiver
import logging

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# ABCD UTILITIES
# -------------------------------------------------------------------
def abcd_format_name(name):
    """ABCD Standard Name Normalizer: NITIN -> Nitin, nitin dangi -> Nitin Dangi"""
    if not name: return ""
    return " ".join(p.strip().capitalize() for p in name.split())


# -------------------------------------------------------------------
# SEAT MODEL
# -------------------------------------------------------------------
class Seat(models.Model):
    FLOOR_CHOICES = [('Ground Floor', 'Ground Floor'), ('1st Floor', '1st Floor')]
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('pending', 'Pending'),
        ('on_hold', 'On Hold'),
    ]

    HOLD_STATUS_CHOICES = [
        ('none', 'None'),
        ('pending', 'Pending'),
        ('active', 'Active'),
    ]

    seat_number = models.CharField(max_length=10)
    floor = models.CharField(max_length=50, choices=FLOOR_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='available')
    
    # --- SHIFT CONFIGURATION ---
    # Set this to True for Seats 40-53 on Ground Floor
    is_shift_enabled = models.BooleanField(default=False, help_text="If True, allows Morning/Evening shifts")

    # --- HOLD OWNER TRACKING ---
    # We use this to know who put the seat on hold.
    # The actual occupants are linked via StudentProfile.
    hold_student = models.ForeignKey(
        'StudentProfile', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='held_seat_record'
    )
    
    hold_start_date = models.DateField(null=True, blank=True)
    hold_end_date = models.DateField(null=True, blank=True)

    # --- HOLD REQUESTS ---
    hold_status = models.CharField(max_length=10, choices=HOLD_STATUS_CHOICES, default='none', null=True, blank=True)
    hold_request_date = models.DateTimeField(null=True, blank=True)
    hold_request_duration = models.CharField(max_length=20, null=True, blank=True)

    # --- LOCKING ---
    is_locked = models.BooleanField(default=False, help_text="If True, seat is locked by librarian and cannot be occupied")
    locked_shifts = models.CharField(max_length=50, blank=True, null=True, default='', help_text="Comma-separated list of locked shifts: morning, evening, full")

    # --- AVAILABILITY ---
    available_since = models.DateTimeField(null=True, blank=True)


    def clean(self):
        super().clean()

        # Shift-based seats are strictly Ground Floor seats 40–53
        if self.is_shift_enabled:
            try:
                seat_no = int(self.seat_number)
            except ValueError:
                raise ValidationError("Seat number must be numeric for shift-enabled seats.")

            if self.floor != 'Ground Floor' or not (40 <= seat_no <= 53):
                raise ValidationError(
                    "Shift-based seating is allowed only for Ground Floor seats 40–53."
                )
            
    def mark_available(self):
        self.hold_student = None
        self.status = 'available'
        self.hold_status = 'none'
        self.hold_start_date = None
        self.available_since = timezone.now()
        self.save()

    def recalc_status(self, save=True):
        """
        Derives Seat.status from its active SeatAssignments.
        Rule:
        - No active assignments -> available
        - All active assignments on hold -> on_hold
        - Any active assignment NOT on hold -> occupied
        """
        active = self.assignments.filter(is_active=True)
        if not active.exists():
            # Check for GENUINE pending requests (not historical records)
            has_pending = self.assignments.filter(
                is_active=False, 
                student__status='pending', 
                student__seat_id=self.id
            ).exists()
            
            if has_pending:
                self.status = 'pending'
            else:
                self.status = 'available'
        else:
            # If ANY active assignment is NOT on hold, it's occupied.
            # Only if ALL are on hold do we show on_hold color globally.
            if any(a.hold_status != 'active' for a in active):
                self.status = 'occupied'
            else:
                self.status = 'on_hold'
        
        if save:
            self.save(update_fields=['status'])
        return self.status


    def is_hold_expired(self, today=None):
        """
        Detects expired hold.
        DOES NOT modify seat or assignments.
        """
        if self.status != 'on_hold':
            return False

        if not self.hold_end_date:
            return False

        today = today or timezone.localtime(timezone.now()).date()
        return today > self.hold_end_date


    @property
    def is_special_shift_seat(self):
        return self.is_shift_enabled


    def __str__(self):
        return f"{self.floor} - Seat {self.seat_number} ({self.status})"

# -------------------------------------------------------------------
# STUDENT PROFILE
# -------------------------------------------------------------------
class StudentProfile(models.Model):
    SEX_CHOICES = [('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')]
    SERVICE_CHOICES = [('Coaching', 'Coaching'), ('Library', 'Library')]
    
    STATUS_CHOICES = [
        ('pending', 'Pending'), 
        ('admitted', 'Admitted'),
        ('on_hold', 'On Hold'), 
    ]
    
    BATCH_CHOICES = [
        ('Grammar Batch 1', 'Grammar Batch 1'),
        ('Grammar Batch 2', 'Grammar Batch 2'),
        ('Grammar Batch 3', 'Grammar Batch 3'), 
        ('Grammar Batch 4', 'Grammar Batch 4'),
        ('Spoken English 1', 'Spoken English & PD Batch 1'),
        ('Spoken English 2', 'Spoken English & PD Batch 2'),
    ]

    ADMISSION_TYPE_CHOICES = [
        ('new', 'New Admission'),
        ('existing', 'Already Admitted'),
    ]

    SHIFT_CHOICES = [
        ('full', 'Full Day'),
        ('morning', 'Morning (8AM - 2PM)'),
        ('evening', 'Evening (2PM - 8PM)'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    full_name = models.CharField(max_length=100)
    
    # --- DOB ---
    dob = models.DateField(null=True, blank=True, verbose_name="Date of Birth")
    
    sex = models.CharField(max_length=10, choices=SEX_CHOICES)
    sex_other = models.CharField(max_length=50, blank=True, null=True)
    
    coaching_pending = models.BooleanField(default=False)
    library_pending = models.BooleanField(default=False)
    email = models.EmailField(blank=True, null=True)
    
    # --- PHOTO ---
    photo = models.ImageField(upload_to='student_photos/', blank=True, null=True)
    # address = models.TextField()

    mobile_number = models.CharField(max_length=15)
    whatsapp_number = models.CharField(max_length=15)

    service_type = models.CharField(max_length=20, choices=SERVICE_CHOICES)
    batch = models.CharField(max_length=50, choices=BATCH_CHOICES, blank=True, null=True)
    
    # --- SEAT CONNECTION ---
    seat = models.ForeignKey(
        'Seat', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='students' 
    )
    shift = models.CharField(max_length=10, choices=SHIFT_CHOICES, default='full')
    
    admission_type = models.CharField(max_length=10, choices=ADMISSION_TYPE_CHOICES, default='new')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    is_admitted = models.BooleanField(default=False)
    is_manual_pending = models.BooleanField(default=False)
    fee_expiry_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    password_last_updated = models.DateTimeField(null=True, blank=True)

    @property
    def has_library_seat(self):
        """
        Check if the library student has a valid assigned seat.
        Used for sidebar logic and dashboard routing.
        """
        return self.service_type in ['Library', 'Both'] and self.seat_id is not None

    @property
    def photo_url(self):
        """
        Returns the profile photo URL with a cache buster if it exists.
        Falls back to StudentAchievement photo, then to default avatar.
        """
        if self.photo:
            try:
                import os
                if os.path.exists(self.photo.path):
                    return f"{self.photo.url}?v={int(os.path.getmtime(self.photo.path))}"
                return self.photo.url
            except Exception:
                return self.photo.url
        
        try:
            from .models import StudentAchievement
            achievement = StudentAchievement.objects.filter(user=self.user).first()
            if achievement and achievement.photo:
                import os
                if os.path.exists(achievement.photo.path):
                    return f"{achievement.photo.url}?v={int(os.path.getmtime(achievement.photo.path))}"
                return achievement.photo.url
        except Exception:
            pass
            
        return "/static/data/default_avatar.png"

    @property
    def is_temporary(self):
        """
        Check if the student is a temporary/partial tenant on their assigned seat.
        """
        from .models import SeatAssignment
        assignment = SeatAssignment.objects.filter(student=self, is_active=True).first()
        return assignment.is_partial if assignment else False

    def save(self, *args, **kwargs):
        """
        Universal synchronization: Keeps SeatAssignment in sync with StudentProfile.
        Ensures that changing status in 'Edit Student' automatically updates the Seat Manager.
        """
        # Flag to prevent infinite recursion during sync
        if getattr(self, '_syncing', False):
            super().save(*args, **kwargs)
            return

        # --- ABCD Standard Name Normalization ---
        if self.full_name:
            self.full_name = abcd_format_name(self.full_name)
        
        # Also sync User first_name/last_name if linked
        if self.user:
            parts = self.full_name.split()
            first = parts[0] if len(parts) > 0 else ""
            last = " ".join(parts[1:]) if len(parts) > 1 else ""
            self.user.first_name = first
            self.user.last_name = last
            self.user.save(update_fields=['first_name', 'last_name'])

        is_new = self._state.adding
        # Check if status is changing
        old_record = None
        if not is_new:
            try:
                # Use a fresh query to get the value from DB
                old_record = StudentProfile.objects.filter(pk=self.pk).first()
            except Exception:
                pass

        super().save(*args, **kwargs)

        # Sync common details to StudentAchievement if it exists and both are approved
        from .models import StudentAchievement
        try:
            ach = StudentAchievement.objects.filter(user=self.user, status='approved').first()
            if ach and self.status == 'admitted':
                first_name, *rest = (self.full_name or '').split(' ', 1)
                last_name = rest[0] if rest else ''
                gender = self.sex
                if gender not in ['Male', 'Female', 'Other']:
                    gender = 'Male'
                
                if (ach.first_name != first_name or ach.last_name != last_name or ach.gender != gender or 
                    ach.dob != self.dob or ach.email != self.email or ach.whatsapp_number != self.whatsapp_number or
                    ach.mobile_number != self.mobile_number):
                    ach.first_name = first_name
                    ach.last_name = last_name
                    ach.gender = gender
                    ach.dob = self.dob
                    ach.email = self.email
                    ach.whatsapp_number = self.whatsapp_number
                    ach.mobile_number = self.mobile_number
                    ach._syncing = True
                    ach.save()
        except Exception:
            pass

        # Skip sync for Coaching or if no seat
        if self.service_type not in ['Library', 'Both'] or not self.seat:
            return

        # SYNC TO SEAT ASSIGNMENT
        # Only if status has changed (or it's a new record with a seat)
        if old_record and old_record.status == self.status:
             return

        # Find active or latest assignment for this student
        # Note: SeatAssignment is defined later in the file, so we use a local import
        from .models import SeatAssignment
        assignment = SeatAssignment.objects.filter(student=self, is_active=True).first()
        if not assignment:
            assignment = SeatAssignment.objects.filter(student=self).order_by('-created_at').first()

        if assignment:
            self._syncing = True
            try:
                if getattr(self, '_syncing_from_assignment', False):
                    pass
                elif self.status == 'admitted':
                    if assignment and assignment.is_active:
                        # Clear hold status on assignment
                        if assignment.hold_status != 'none':
                            assignment.hold_status = 'none'
                            assignment.hold_start_date = None
                            assignment.hold_end_date = None
                            assignment.save(update_fields=['hold_status', 'hold_start_date', 'hold_end_date'])
                        
                        # Clear hold status on seat
                        if self.seat:
                            seat = self.seat
                            if seat.hold_student_id == self.id:
                                seat.hold_status = 'none'
                                seat.hold_start_date = None
                                seat.hold_end_date = None
                                seat.hold_student = None
                                if seat.status == 'on_hold':
                                    seat.status = 'occupied'
                                seat.save(update_fields=['hold_status', 'hold_start_date', 'hold_end_date', 'hold_student', 'status'])
                                seat.recalc_status()

                            # Deactivate partial tenants
                            from .models import SeatAssignment
                            temps = SeatAssignment.objects.filter(
                                seat=seat, 
                                is_active=True, 
                                is_partial=True
                            ).exclude(pk=assignment.pk)
                            for t in temps:
                                t.deactivate()
                elif self.status == 'on_hold':
                    if assignment.is_active:
                        if assignment.hold_status != 'active':
                            assignment.hold_status = 'active'
                            assignment.save(update_fields=['hold_status'])
                elif self.status == 'pending':
                    if assignment.is_active:
                        assignment.is_active = False
                        assignment.save(update_fields=['is_active'])

            finally:
                self._syncing = False

    def __str__(self):
        return self.full_name


# -------------------------------------------------------------------
# COMPLAINT MODEL
# -------------------------------------------------------------------
class Complaint(models.Model):
    SUBJECT_WIFI = "wifi"
    SUBJECT_NOISE = "noise"
    SUBJECT_CLEANING = "cleaning"
    SUBJECT_WASHROOM = "washroom"
    SUBJECT_LOST_FOUND = "lost_found"
    SUBJECT_WATER = "water"
    SUBJECT_OTHER = "other"

    SUBJECT_CHOICES = [
        (SUBJECT_WIFI, "Wi-Fi / Internet issue"),
        (SUBJECT_NOISE, "Noise / Disturbance"),
        (SUBJECT_CLEANING, "Cleaning issue"),
        (SUBJECT_WASHROOM, "Washroom / Toilet"),
        (SUBJECT_LOST_FOUND, "Lost & Found"),
        (SUBJECT_WATER, "Water cooler / Drinking water"),
        (SUBJECT_OTHER, "Anything else"),
    ]

    STATUS_NEW = "new"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_RESOLVED = "resolved"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_IN_PROGRESS, "In progress"),
        (STATUS_RESOLVED, "Resolved"),
    ]

    student = models.ForeignKey(
        "StudentProfile", on_delete=models.CASCADE, related_name="complaints"
    )
    role = models.CharField(
        max_length=10,
        choices=[('student', 'Student'), ('alumni', 'Alumni')],
        default='student',
        help_text="Role of the complainant when making this complaint"
    )
    subject = models.CharField(max_length=50, choices=SUBJECT_CHOICES)
    custom_subject = models.CharField(
        max_length=120,
        blank=True,
        help_text="Used when subject = Anything else",
    )
    message = models.TextField()

    image1 = models.ImageField(upload_to="complaints/", blank=True, null=True)
    image2 = models.ImageField(upload_to="complaints/", blank=True, null=True)
    image3 = models.ImageField(upload_to="complaints/", blank=True, null=True)

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    # student feedback after resolution
    rating = models.PositiveSmallIntegerField(null=True, blank=True)  # 1-5
    feedback = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if self.status == self.STATUS_RESOLVED:
            if not self.resolved_at:
                self.resolved_at = timezone.now()
        else:
            self.resolved_at = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Complaint #{self.id} by {self.student.full_name}"

    @property
    def code(self) -> str:
        # human-friendly complaint ID
        return f"C{self.id:05d}"

    @property
    def display_subject(self) -> str:
        if self.subject == self.SUBJECT_OTHER and self.custom_subject:
            return self.custom_subject
        return dict(self.SUBJECT_CHOICES).get(self.subject, "Complaint")


@receiver(post_delete, sender=Complaint)
def auto_delete_complaint_images_on_delete(sender, instance, **kwargs):
    """Deletes image files from storage (Local / Cloudinary) when Complaint is deleted."""
    for image_field in [instance.image1, instance.image2, instance.image3]:
        if image_field:
            try:
                image_field.delete(save=False)
            except Exception:
                try:
                    if hasattr(image_field, 'path') and os.path.isfile(image_field.path):
                        os.remove(image_field.path)
                except Exception:
                    pass


# -------------------------------------------------------------------
# COURSE AND STUDY MATERIAL MODELS
# -------------------------------------------------------------------

class CourseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)  # <--- This was missing
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class Course(models.Model):
    title = models.CharField(max_length=255)
    playlist_id = models.CharField(max_length=200, unique=True, blank=True, null=True)
    description = models.TextField(blank=True)
    video_url = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # manual category (optional)
    category = models.ForeignKey(
        CourseCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="courses"
    )

    # auto control
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ✅ NEW FIELDS
    video_count = models.PositiveIntegerField(default=0)
    video_ids = models.TextField(blank=True, null=True) # Comma-separated YT IDs for custom courses
    last_synced_at = models.DateTimeField(null=True, blank=True)
    thumbnail = models.ImageField(upload_to='course_thumbnails/', blank=True, null=True)

    # Target audience configuration fields
    target_public = models.BooleanField(default=True)
    target_coaching = models.BooleanField(default=False)
    target_coaching_batches = models.TextField(blank=True, default="")
    target_alumni = models.BooleanField(default=False)
    target_library = models.BooleanField(default=False)
    target_library_floors = models.TextField(blank=True, default="")
    target_private = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    @property
    def thumbnail_display_url(self):
        """Returns uploaded thumbnail URL or falls back to YouTube CDN thumbnail."""
        if self.thumbnail:
            try:
                return self.thumbnail.url
            except Exception:
                pass
        # Direct YouTube CDN fallback for custom / synced courses
        if self.video_ids:
            first_id = self.video_ids.split(',')[0].strip()
            if first_id:
                return f"https://img.youtube.com/vi/{first_id}/hqdefault.jpg"
        first_mat = self.materials.filter(material_type='video').first()
        if first_mat and first_mat.external_url:
            import re
            m = re.search(r'(?:v=|\/embed\/|\/watch\?v=|youtu\.be\/|\/v\/|e\/|watch\?feature=player_embedded&v=)([a-zA-Z0-9_-]{11})', first_mat.external_url)
            if m:
                return f"https://img.youtube.com/vi/{m.group(1)}/hqdefault.jpg"
        return None

    @property
    def average_rating(self):
        # Use simple aggregation or calculate from reviews
        avg = self.reviews.aggregate(models.Avg('rating'))['rating__avg']
        return round(avg, 1) if avg else 0.0

    @property
    def review_count(self):
        return self.reviews.count()


class StudyMaterial(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='materials')
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="study_materials/", blank=True, null=True)
    external_url = models.URLField(blank=True, null=True) # For YT videos or external links
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    MATERIAL_TYPES = [
        ('video', 'Video'),
        ('document', 'Document'),
        ('image', 'Image'),
        ('link', 'Link'),
    ]
    material_type = models.CharField(max_length=20, choices=MATERIAL_TYPES, default='document')
    order = models.PositiveIntegerField(default=0)
    thumbnail = models.ImageField(upload_to="material_thumbnails/", blank=True, null=True)
    is_public = models.BooleanField(default=False)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

    @property
    def youtube_id(self):
        if self.external_url and 'youtu' in self.external_url:
            import re
            regex = r'(?:v=|\/)([0-9A-Za-z_-]{11}).*'
            match = re.search(regex, self.external_url)
            if match: return match.group(1)
        return None

    class Meta:
        ordering = ['order', 'created_at']

# Student_dashboard NOTIFICATIOS
class Notification(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="notifications"
    )
    title = models.CharField(max_length=100)
    message = models.TextField()
    link = models.CharField(max_length=255, blank=True, null=True)

    category = models.CharField(
        max_length=50,
        choices=[
            ("course", "Course"),
            ("admission", "Admission"),
            ("hold", "Seat Hold"),
            ("complaint", "Complaint"),
            ("payment", "Payment"),
            ("fee", "Fee"),
            ("fee_teacher", "Fee Teacher"),
            ("reminder", "Reminder"),
            ("guidy", "Guidy"),
            ("general", "General"),
        ],
        default="general"
    )

    meta = models.JSONField(blank=True, null=True, help_text="Extra data for UI or logic (e.g., student_id, reminder_type)")
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)  # Set when marked as read; used for 5-day cleanup
    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):
        return f"{self.user.username} - {self.title}"


class DismissedFeeAlert(models.Model):
    """
    Tracks fee expired alerts dismissed by a teacher for a specific student and fee_expiry_date.
    If the student's fee is later extended and then expires again on a new date, they automatically reappear.
    """
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="dismissed_fee_alerts")
    student = models.ForeignKey('StudentProfile', on_delete=models.CASCADE, related_name="dismissed_fee_alerts")
    expiry_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('teacher', 'student', 'expiry_date')

    def __str__(self):
        return f"Dismissed alert for {self.student.full_name} ({self.expiry_date}) by {self.teacher.username}"

# -------------------------------------------------------------------
# BROADCAST MESSAGE MODEL (history container)
# -------------------------------------------------------------------

class BroadcastMessage(models.Model):
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="broadcasts"
    )

    subject = models.CharField(max_length=200)
    message = models.TextField()

    target_group = models.CharField(max_length=20)
    floor = models.CharField(max_length=20, blank=True, null=True)
    batch = models.CharField(max_length=50, blank=True, null=True)

    send_whatsapp = models.BooleanField(default=False)
    send_email = models.BooleanField(default=False)

    # scheduling (used in phase 2)
    send_at = models.DateTimeField(blank=True, null=True)

    status = models.CharField(
        max_length=20,
        choices=[
            ("sent", "Sent"),
            ("scheduled", "Scheduled"),
            ("failed", "Failed"),
            ("processing", "Processing"),
        ],
        default="sent"
    )

    is_sent = models.BooleanField(default=True)
    is_draft = models.BooleanField(default=False)
    failed_user_ids = models.JSONField(default=list, blank=True)
    attachment = models.FileField(upload_to="broadcast_attachments/", blank=True, null=True)
    
    # Store targeted individual IDs for history
    selected_ids = models.JSONField(null=True, blank=True, help_text="List of User IDs if target_group is individuals")

    # New Ads Banner fields
    message_type = models.CharField(
        max_length=20,
        choices=[("broadcast", "Broadcast Message"), ("banner", "Ads Banner")],
        default="broadcast"
    )
    banner_type = models.CharField(
        max_length=20,
        choices=[("image", "Image to Banner"), ("text", "Write to Banner")],
        blank=True,
        null=True
    )
    banner_image = models.FileField(upload_to="broadcast_banners/", blank=True, null=True)
    banner_buttons = models.JSONField(default=list, blank=True, null=True, help_text="List of CTA button dicts")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="Auto-delete and expiration timestamp")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.message_type.upper()}] {self.subject} - {self.created_at}"


class BannerViewLog(models.Model):
    """Tracks whether a student has viewed/dismissed an Ads Banner pop-up."""
    broadcast = models.ForeignKey(BroadcastMessage, on_delete=models.CASCADE, related_name="view_logs")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="banner_views")
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("broadcast", "user")

    def __str__(self):
        return f"{self.user.username} viewed banner {self.broadcast.id}"



class BroadcastAttachment(models.Model):
    broadcast = models.ForeignKey(BroadcastMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to="broadcast_files/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Attachment for {self.broadcast.subject}"

@receiver(post_delete, sender=BroadcastAttachment)
def auto_delete_broadcast_attachment_on_delete(sender, instance, **kwargs):
    """Deletes file from storage (Local / Cloudinary) when BroadcastAttachment is deleted."""
    if instance.file:
        try:
            instance.file.delete(save=False)
        except Exception:
            try:
                if hasattr(instance.file, 'path') and os.path.isfile(instance.file.path):
                    os.remove(instance.file.path)
            except Exception:
                pass

# -------------------------------------------------------------------
# PAYMENT MODEL
# -------------------------------------------------------------------
class Payment(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='payments')
    month = models.CharField(max_length=20)
    year = models.IntegerField()
    amount = models.DecimalField(max_digits=8, decimal_places=2)
    # Day *inside* that month that you choose in Fee Calendar
    date_paid = models.DateField(default=timezone.localdate)

    # Actual date when teacher saved/updated this payment
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'month', 'year')

    def __str__(self):
        return f'{self.student.full_name} - {self.month} {self.year}'


# -------------------------------------------------------------------
# FEE TRANSACTION MODEL (Receipt Layer)
# -------------------------------------------------------------------
class FeeTransaction(models.Model):
    """
    ABCD Dedicated Accounting Layer.
    This model stores immutable snapshots of fee submissions for receipt generation.
    It is kept SEPARATE from the Payment model to avoid breaking the fee calendar 
    and reminder systems which depend on Payment.
    """
    student = models.ForeignKey(
        StudentProfile, 
        on_delete=models.CASCADE, 
        related_name='fee_transactions'
    )
    teacher = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        related_name='processed_fee_transactions'
    )
    
    # Format: ABCD_YY/RANDOM7 (e.g. ABCD_26/00243514)
    receipt_number = models.CharField(
        max_length=30, 
        unique=True, 
        help_text="Unique receipt identifier for accounting"
    )
    
    payment_date = models.DateField(help_text="The date the teacher recorded this transaction")
    expiry_date = models.DateField(null=True, blank=True, help_text="The student's fee expiry date after this submission")
    
    # Frozen Data Snapshots
    service_snapshot = models.TextField(
        help_text="Frozen description of student service at time of payment"
    )
    months_snapshot = models.JSONField(
        help_text="Immutable list of months covered. Format: [{'month': '...', 'amount': ..., 'status': '...'}]"
    )
    
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Communication Status
    email_sent = models.BooleanField(default=False)
    whatsapp_sent = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Fee Transaction"
        verbose_name_plural = "Fee Transactions"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['receipt_number']),
            models.Index(fields=['student', 'created_at']),
        ]

    def __str__(self):
        return f"Receipt {self.receipt_number} - {self.student.full_name}"

    @staticmethod
    def generate_receipt_number():
        """
        Generates a unique receipt number based on ABCD rules.
        Format: ABCD_YY/RANDOM7
        """
        import random
        from django.utils import timezone
        
        prefix = "ABCD_"
        year_suffix = timezone.localdate().strftime("%y") # Last 2 digits of current year in IST
        
        while True:
            # Generate 7 random digits
            random_digits = "".join([str(random.randint(0, 9)) for _ in range(7)])
            receipt_no = f"{prefix}{year_suffix}/{random_digits}"
            
            # Uniqueness check against DB
            if not FeeTransaction.objects.filter(receipt_number=receipt_no).exists():
                return receipt_no



# -------------------------------------------------------------------
# VISITOR INTENT MODEL
# -------------------------------------------------------------------
class VisitorIntent(models.Model):
    INTENT_CHOICES = [
        ("guest_browsed", "Guest Browsed"),
        ("viewed_library", "Viewed Library Availability"),
        ("opened_admission", "Opened Admission Form"),
        ("selected_coaching", "Selected Coaching"),
        ("selected_library", "Selected Library"),
        ("selected_library_seat", "Selected Library Seat"),
    ]

    INTENT_SCOPE_CHOICES = [
        ("general", "General"),     # generic reminders
        ("specific", "Specific"),   # seat-specific reminders
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="visitor_intents"
    )

    intent_type = models.CharField(
        max_length=50,
        choices=INTENT_CHOICES
    )

    # Scope of intent (general or seat-specific)
    intent_scope = models.CharField(
        max_length=20,
        choices=INTENT_SCOPE_CHOICES,
        default="general"
    )

    # Extra data like seat number, floor, service type, etc.
    metadata = models.JSONField(blank=True, null=True)

    # --- Reminder system ---
    reminder_sent = models.BooleanField(default=False)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    # --- Auto-resolve once user is admitted ---
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # Prevent duplicate reminders efficiently
            models.Index(fields=["user", "intent_type", "intent_scope"]),
            models.Index(fields=["reminder_sent"]),
            models.Index(fields=["resolved"]),
        ]

    # Helper methods
    def mark_reminder_sent(self):
        self.reminder_sent = True
        self.reminder_sent_at = timezone.now()
        self.save(update_fields=["reminder_sent", "reminder_sent_at"])

    def mark_resolved(self):
        self.resolved = True
        self.resolved_at = timezone.now()
        self.save(update_fields=["resolved", "resolved_at"])

    def __str__(self):
        return f"{self.user.email} | {self.intent_type} | {self.intent_scope}"
# -----------------------------------------------------------------------------

# PUSH SUBSCRIPTION MODEL
# Stores push subscription info for web push notifications
class PushSubscription(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    endpoint = models.TextField(unique=True)
    keys = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"PushSubscription({self.user.email})"
# -----------------------------------------------------------------------------

# ============================================================
# SeatAssignment
# ------------------------------------------------------------
# Represents a single student's usage of a seat.
# This model is ADDITIVE and does NOT replace any existing logic.
# It will be used later for shift-based and partial seat handling.
# ============================================================

# users/models.py

class SeatAssignment(models.Model):

    # --- SHIFT-LEVEL HOLD SYSTEM ---
    # These fields allow a specific shift (e.g., Morning) to be on hold
    # independently of the Seat's main status.
    HOLD_STATUS_CHOICES = [
        ('none', 'None'),
        ('pending', 'Pending'),
        ('active', 'Active'),
    ]

    hold_status = models.CharField(
        max_length=10,
        choices=HOLD_STATUS_CHOICES,
        default='none',
        help_text="If 'active', this student is away, and their shift is eligible for partial allotment."
    )

    hold_start_date = models.DateField(
        null=True,
        blank=True,
        help_text="Start date for this specific assignment's hold."
    )

    hold_end_date = models.DateField(
        null=True,
        blank=True,
        help_text="End date for this specific assignment's hold."
    )

    # --- PARTIAL ALLOTMENT SYSTEM ---
    # This is the KEY field for your "Image 3.1" and "Image 3.2" scenarios.
    # It distinguishes the 'Tenant' from the 'Owner'.
    is_partial = models.BooleanField(
        default=False,
        help_text="If True, this is a 'Tenant' student occupying a seat/shift temporarily."
    )

    allow_hold_override = models.BooleanField(
        default=False,
        help_text="Teacher-approved override (corresponds with is_partial)."
    )

    SHIFT_FULL = 'full'
    SHIFT_MORNING = 'morning'
    SHIFT_EVENING = 'evening'

    SHIFT_CHOICES = [
        (SHIFT_FULL, 'Full Day'),
        (SHIFT_MORNING, 'Morning Shift'),
        (SHIFT_EVENING, 'Evening Shift'),
    ]

    seat = models.ForeignKey(
        'Seat',
        on_delete=models.CASCADE,
        related_name='assignments'
    )

    student = models.ForeignKey(
        'StudentProfile',
        on_delete=models.CASCADE,
        related_name='seat_assignments'
    )

    shift_type = models.CharField(
        max_length=10,
        choices=SHIFT_CHOICES,
        default=SHIFT_FULL
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Indicates whether this assignment is currently active (applies to both Owner and Tenant)."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Seat Assignment"
        verbose_name_plural = "Seat Assignments"
        ordering = ['-created_at']

        constraints = [
            # A student can still only be physically present in ONE active assignment
            models.UniqueConstraint(
                fields=['student'],
                condition=models.Q(is_active=True),
                name='unique_active_seatassignment_per_student'
            ),
        ]

    def sync_seat_status(self):
        """
        Updates the parent Seat status based on what is happening here.
        """
        seat = self.seat
        # If seat is officially on hold at the Seat level, don't overwrite it with 'occupied'
        if seat.status == 'on_hold':
            return

        self.recalc_seat_state()

    def recalc_seat_state(self):
        """
        Delegates to seat.recalc_status() for master color sync.
        """
        self.seat.recalc_status()

    def deactivate(self):
        if not self.is_active:
            return
        self.is_active = False
        self.save(update_fields=['is_active'])
        self.sync_student_pointer()
        self.recalc_seat_state()

    def sync_student_pointer(self):
        """
        Universal synchronization: Keeps StudentProfile in sync with SeatAssignment.
        Ensures Dashboard, Seat Manager, and Edit Student are always consistent.
        """
        student = self.student
        dirty_fields = []

        if self.is_active:
            # 1. Sync Seat Link
            if student.seat_id != self.seat_id:
                student.seat = self.seat
                dirty_fields.append('seat')
            
            # 2. Sync Shift
            if student.shift != self.shift_type:
                student.shift = self.shift_type
                dirty_fields.append('shift')

            # 3. Sync Administrative Status
            new_status = 'on_hold' if self.hold_status == 'active' else 'admitted'
            if student.status != new_status:
                student.status = new_status
                dirty_fields.append('status')
            
            # Always set is_admitted to True once they are active
            if not student.is_admitted:
                student.is_admitted = True
                dirty_fields.append('is_admitted')
            
            # 4. Clear Manual Pending Flag (since they are now admitted or on hold)
            if student.is_manual_pending:
                student.is_manual_pending = False
                dirty_fields.append('is_manual_pending')

        else:
            # Assignment Deactivated
            # Check if student has other active assignments before clearing
            has_other = SeatAssignment.objects.filter(
                student=student, 
                is_active=True
            ).exclude(pk=self.pk).exists()
            
            if not has_other:
                # Student has no active seats left
                if student.seat_id is not None:
                    student.seat = None
                    dirty_fields.append('seat')
                
                if student.shift != 'full':
                    student.shift = 'full'
                    dirty_fields.append('shift')
                
                # Check current status before forcing to admitted
                target_status = 'admitted' if student.is_admitted else 'pending'
                # If they were on hold, preserve it as long as possible or let the teacher decide.
                # But physically they have no seat, so 'on_hold' student status without a seat is valid.
                if student.status == 'on_hold':
                    pass # Keep on_hold status
                elif student.status != target_status:
                    student.status = target_status
                    dirty_fields.append('status')

        if dirty_fields:
            student._syncing_from_assignment = True
            student.save(update_fields=dirty_fields)

    def clean(self):
        super().clean()
        if not self.seat:
            return

        seat = self.seat
        target_shift = self.shift_type
        
        # Determine if this assignment is new, activating, or changing shift
        is_new_or_activating = False
        if not self.pk:
            is_new_or_activating = True
        else:
            old = SeatAssignment.objects.filter(pk=self.pk).first()
            if old and not old.is_active:
                is_new_or_activating = True
            elif old and old.shift_type != self.shift_type:
                is_new_or_activating = True

        if not self.is_active or not is_new_or_activating:
            # We don't perform collision checks when deactivating or simply updating status/holds
            return
            
        # 1. Get all CURRENT active people on this seat (excluding self)
        existing_assignments = SeatAssignment.objects.filter(
            seat=seat, is_active=True
        ).exclude(pk=self.pk)

        # ----------------------------------------------
        # LOGIC FOR NON-SHIFT SEATS (Simple Logic)
        # ----------------------------------------------
        if not seat.is_shift_enabled:
            if target_shift != self.SHIFT_FULL:
                raise ValidationError("This seat does not support shifts.")
            
            # Scenario: Seat is On Hold (Seat Level)
            if seat.status == 'on_hold':
                # Only allow if this is a Partial Tenant
                if not (self.is_partial or self.allow_hold_override):
                    raise ValidationError("This seat is currently on hold. You cannot take it normally.")
                
                # Prevent 2 Tenants on 1 Hold
                if existing_assignments.filter(is_partial=True).exists():
                    raise ValidationError("This seat already has a partial tenant.")
                
            # Scenario: Seat is Occupied Normally
            elif existing_assignments.exists():
                raise ValidationError("This seat is already fully occupied.")

            return

        # ----------------------------------------------
        # LOGIC FOR SHIFT SEATS (Ground Floor 40-53)
        # ----------------------------------------------
        # We need to check collisions for Morning, Evening, and Full Day separately.
        
        # Helper: Who is currently in Morning?
        morning_occupants = existing_assignments.filter(shift_type=self.SHIFT_MORNING)
        morning_owner = morning_occupants.filter(is_partial=False).first()
        morning_tenant = morning_occupants.filter(is_partial=True).first()

        # Helper: Who is currently in Evening?
        evening_occupants = existing_assignments.filter(shift_type=self.SHIFT_EVENING)
        evening_owner = evening_occupants.filter(is_partial=False).first()
        evening_tenant = evening_occupants.filter(is_partial=True).first()

        # Helper: Who is currently Full Day?
        full_occupants = existing_assignments.filter(shift_type=self.SHIFT_FULL)
        
        # A. IF I AM REQUESTING MORNING
        if target_shift == self.SHIFT_MORNING:
            if full_occupants.exists():
                full_owner = full_occupants.filter(is_partial=False).first()
                if full_owner and full_owner.hold_status == 'active':
                    if not self.is_partial:
                        raise ValidationError("Seat is on full day hold. You must request partial allotment.")
                    if morning_tenant or full_occupants.filter(is_partial=True).exists():
                        raise ValidationError("Morning shift already has a partial tenant.")
                    # SUCCESS: Owner is on full day hold, Morning is available for tenant
                else:
                    raise ValidationError("Seat is occupied by a full-day student.")
            
            if morning_owner:
                # Slot taken. Is it on hold?
                if morning_owner.hold_status == 'active':
                    # Yes, on hold. Am I a Partial Tenant?
                    if not self.is_partial:
                        raise ValidationError("Morning shift is on hold. You must request partial allotment.")
                    if morning_tenant:
                        raise ValidationError("Morning shift already has a partial tenant.")
                    # SUCCESS: Owner is on hold, I am partial.
                else:
                    # Not on hold. Blocked.
                    raise ValidationError("Morning shift is already occupied.")
            else:
                # No owner.
                pass # Free to take

        # B. IF I AM REQUESTING EVENING
        elif target_shift == self.SHIFT_EVENING:
            if full_occupants.exists():
                full_owner = full_occupants.filter(is_partial=False).first()
                if full_owner and full_owner.hold_status == 'active':
                    if not self.is_partial:
                        raise ValidationError("Seat is on full day hold. You must request partial allotment.")
                    if evening_tenant or full_occupants.filter(is_partial=True).exists():
                        raise ValidationError("Evening shift already has a partial tenant.")
                    # SUCCESS: Owner is on full day hold, Evening is available for tenant
                else:
                    raise ValidationError("Seat is occupied by a full-day student.")
            
            if evening_owner:
                if evening_owner.hold_status == 'active':
                    if not self.is_partial:
                        raise ValidationError("Evening shift is on hold. You must request partial allotment.")
                    if evening_tenant:
                        raise ValidationError("Evening shift already has a partial tenant.")
                else:
                    raise ValidationError("Evening shift is already occupied.")

        # C. IF I AM REQUESTING FULL DAY (The Complex S8 Scenario)
        elif target_shift == self.SHIFT_FULL:
            # 1. Check Full Day collision
            if full_occupants.exists():
                full_owner = full_occupants.filter(is_partial=False).first()
                full_tenant = full_occupants.filter(is_partial=True).first()
                if full_owner and full_owner.hold_status == 'active':
                    if not self.is_partial:
                        raise ValidationError("Seat is on full day hold. You must request partial allotment.")
                    if full_tenant:
                        raise ValidationError("Seat already has a full day partial tenant.")
                    # Success: Full Day Owner is on hold, new assignment is a tenant
                    return
                else:
                    raise ValidationError("Seat is already occupied by another full-day student.")

            # 2. Check Morning collision
            can_take_morning = False
            if not morning_owner:
                can_take_morning = True # Empty
            elif morning_owner.hold_status == 'active' and not morning_tenant and self.is_partial:
                can_take_morning = True # On hold, and I am partial
            
            # 3. Check Evening collision
            can_take_evening = False
            if not evening_owner:
                can_take_evening = True # Empty
            elif evening_owner.hold_status == 'active' and not evening_tenant and self.is_partial:
                can_take_evening = True # On hold, and I am partial

            # 4. Final Verdict for Full Day
            # We allow Full Day IF both slots are accessible (either empty OR hold-partial-able)
            if not (can_take_morning and can_take_evening):
                raise ValidationError("Cannot take full day. One or both shifts are blocked.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        self.sync_student_pointer()
        self.recalc_seat_state()

    def __str__(self):
        status = "Partial" if self.is_partial else "Owner"
        if self.hold_status == 'active':
            status += " (On Hold)"
        return f"Seat {self.seat.seat_number} - {self.student.full_name} [{self.shift_type}] - {status}"
    
# ============================================================
# SPECIAL SEAT REQUEST (Hold → Shift Request)
# ============================================================

class SeatSpecialRequest(models.Model):
    """
    Stores temporary/partial seat requests from students.
    For new students (no profile yet), we store user reference.
    For existing students, we store student profile reference.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    # For new students who don't have a profile yet
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='special_seat_requests_by_user',
        null=True,
        blank=True
    )

    # For existing students with a profile
    student = models.ForeignKey(
        'StudentProfile',
        on_delete=models.CASCADE,
        related_name='special_seat_requests',
        null=True,
        blank=True
    )

    seat = models.ForeignKey(
        'Seat',
        on_delete=models.CASCADE,
        related_name='special_requests'
    )

    requested_shift = models.CharField(
        max_length=10,
        choices=[
            ('morning', 'Morning'),
            ('evening', 'Evening'),
            ('full', 'Full Day'),
        ]
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        name = self.student.full_name if self.student else (self.user.username if self.user else "Unknown")
        return f"{name} → Seat {self.seat.seat_number} ({self.requested_shift})"
    
    @property
    def requester_name(self):
        """Get the name of the requester (either from student profile or user)"""
        if self.student:
            return self.student.full_name
        elif self.user:
            profile = getattr(self.user, 'profile', None)
            if profile:
                return profile.full_name
            return self.user.get_full_name() or self.user.username
        return "Unknown"


@receiver(post_delete, sender=SeatAssignment)
def cleanup_after_assignment_delete(sender, instance, **kwargs):
    """
    Safety net if someone deletes assignments manually.
    """
    try:
        instance.sync_student_pointer()
        instance.recalc_seat_state()
    except Exception:
        pass

@receiver(post_delete, sender=SeatAssignment)
def seatassignment_post_delete(sender, instance, **kwargs):
    instance.recalc_seat_state()


# SEAT HOLD REQUEST MODEL
class SeatHoldRequest(models.Model):
    seat = models.ForeignKey(Seat, on_delete=models.CASCADE)
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    start_date = models.DateField()
    duration_text = models.CharField(max_length=50)
    status = models.CharField(max_length=10, choices=[
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], default='pending')
    cancel_requested = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('seat', 'status')


# SEAT SWITCH REQUEST MODEL
class SeatSwitchRequest(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    student = models.ForeignKey(
        'StudentProfile',
        on_delete=models.CASCADE,
        related_name='seat_switch_requests'
    )
    target_seat = models.ForeignKey(
        'Seat',
        on_delete=models.CASCADE,
        related_name='switch_requests'
    )
    target_shift = models.CharField(
        max_length=10,
        choices=[
            ('morning', 'Morning'),
            ('evening', 'Evening'),
            ('full', 'Full Day'),
        ]
    )
    is_temporary = models.BooleanField(default=False)
    temp_hold_days = models.IntegerField(default=0)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.full_name} request switch to {self.target_seat.seat_number} ({self.target_shift})"


# -------------------------------------------------------------------
# COURSE Q&A AND REVIEWS
# -------------------------------------------------------------------

class CourseQuestion(models.Model):
    course = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='questions')
    student = models.ForeignKey('StudentProfile', on_delete=models.CASCADE, related_name='course_questions')
    material = models.ForeignKey('StudyMaterial', on_delete=models.SET_NULL, null=True, blank=True, related_name='questions')
    question = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_resolved = models.BooleanField(default=False)
    upvotes = models.ManyToManyField(User, related_name='upvoted_questions', blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Question by {self.student.full_name} on {self.course.title}"

class CourseAnswer(models.Model):
    question = models.ForeignKey(CourseQuestion, on_delete=models.CASCADE, related_name='answers')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='course_answers')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    answer_text = models.TextField()
    is_teacher_answer = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    upvotes = models.ManyToManyField(User, related_name='upvoted_answers', blank=True)

    class Meta:
        ordering = ['created_at']

class CourseReview(models.Model):
    course = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='reviews')
    student = models.ForeignKey('StudentProfile', on_delete=models.CASCADE, related_name='course_reviews', null=True, blank=True)
    rating = models.PositiveSmallIntegerField(help_text="Rating from 1 to 5")
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    guest_name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        if self.student:
            return f"{self.rating} stars by {self.student.full_name} for {self.course.title}"
        return f"{self.rating} stars by {self.guest_name or 'Unknown'} (Guest) for {self.course.title}"

# -------------------------------------------------------------------
# ENGAGEMENT TRACKING
# -------------------------------------------------------------------

class CourseShare(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='shares')
    student = models.ForeignKey(StudentProfile, on_delete=models.SET_NULL, null=True, blank=True)
    platform = models.CharField(max_length=50, blank=True, null=True) # e.g. 'whatsapp', 'generic'
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Share for {self.course.title} at {self.created_at}"

class StudentMaterialAccess(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='material_access')
    material = models.ForeignKey(StudyMaterial, on_delete=models.CASCADE, related_name='student_access')
    first_accessed = models.DateTimeField(auto_now_add=True)
    last_accessed = models.DateTimeField(auto_now=True)

    class Meta:
        # This ensures one record per student-material pair for "unique student" counting
        unique_together = ('student', 'material')
        verbose_name_plural = "Student Material Accesses"

    def __str__(self):
        return f"{self.student.full_name} accessed {self.material.title}"

class StudentCourseInteraction(models.Model):
    """
    ABCD Student-Course Lifecycle Tracking.
    Tracks persistent states like 'Favorite' and 'Archived' for individual students.
    """
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='course_interactions')
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='student_interactions')
    is_favorite = models.BooleanField(default=False)
    is_archived = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('student', 'course')
        verbose_name = "Student Course Interaction"
        verbose_name_plural = "Student Course Interactions"

    def __str__(self):
        return f"{self.student.full_name} - {self.course.title} (Fav: {self.is_favorite}, Arch: {self.is_archived})"

# -------------------------------------------------------------------
# NOTIFICATIONS AND REMINDERS
# -------------------------------------------------------------------

class LearningReminder(models.Model):
    RECURRENCE_CHOICES = [
        ('once', 'Once'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('custom', 'Custom Days'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='learning_reminders')
    course = models.ForeignKey('Course', on_delete=models.CASCADE, related_name='reminders')
    title = models.CharField(max_length=200)
    
    # For one-off reminders
    reminder_time = models.DateTimeField(null=True, blank=True)
    
    # For recurring reminders
    recurrence_type = models.CharField(max_length=20, choices=RECURRENCE_CHOICES, default='once')
    reminder_time_daily = models.TimeField(null=True, blank=True)
    days_of_week = models.CharField(max_length=100, blank=True, help_text="Comma-separated days: 0-6 (Mon-Sun)")
    
    is_sent = models.BooleanField(default=False)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['reminder_time', 'reminder_time_daily']

    def get_days_display(self):
        if not self.days_of_week:
            return ""
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        try:
            indices = [int(d.strip()) for d in self.days_of_week.split(",") if d.strip().isdigit()]
            return ", ".join([day_names[i] for i in indices if 0 <= i <= 6])
        except Exception:
            return self.days_of_week

    def __str__(self):
        return f"Reminder for {self.user.username} - {self.recurrence_type}"

# -------------------------------------------------------------------
# STUDENT ACHIEVEMENTS & ALUMNI SYSTEM
# -------------------------------------------------------------------

class StudentAchievement(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    SERVICE_CHOICES = [
        ('library', 'Library'),
        ('coaching', 'Coaching'),
        ('both', 'Both'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='achievements')
    
    # Basic Details
    first_name = models.CharField(max_length=50)
    last_name = models.CharField(max_length=50)
    about_yourself = models.TextField(help_text="Write something positive about yourself")
    current_post = models.CharField(max_length=200, help_text="Current post and year of selection")
    selection_year = models.IntegerField()
    working_city = models.CharField(max_length=100, help_text="City where you are currently working")
    short_achievement = models.CharField(max_length=50, help_text="Your Big Achievement Name in Shortcut (e.g. Post name short form)")
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    gender = models.CharField(max_length=10, choices=[('Male', 'Male'), ('Female', 'Female'), ('Other', 'Other')])
    dob = models.DateField(verbose_name="Date of Birth")
    photo = models.ImageField(upload_to='achievements/')
    
    # Service Usage
    services_used = models.CharField(max_length=20, choices=SERVICE_CHOICES)
    duration_years = models.IntegerField(default=0)
    duration_days = models.IntegerField(default=0)
    
    # Teacher Only Contact Details
    mobile_number = models.CharField(max_length=15, blank=True, null=True)
    whatsapp_number = models.CharField(max_length=15, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    
    # Feedback & Experience
    experience_feedback = models.TextField(verbose_name="Experience at ABCD library/coaching")
    
    # Dynamic Fields: Other Achievements
    # Format: [{"title": "...", "year": "..."}]
    other_achievements = models.JSONField(default=list, blank=True, help_text="Other achievements and year of achieving")
    
    # Rating
    rating = models.IntegerField(default=5) # 1 to 5 stars
    abcd_feedback = models.TextField(verbose_name="Feedback for ABCD")
    
    # Administrative
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def photo_url(self):
        """
        Returns the profile photo URL with a cache buster if it exists.
        Falls back to StudentProfile photo, then to default avatar.
        """
        if self.photo:
            try:
                import os
                if os.path.exists(self.photo.path):
                    return f"{self.photo.url}?v={int(os.path.getmtime(self.photo.path))}"
                return self.photo.url
            except Exception:
                return self.photo.url
        
        try:
            from .models import StudentProfile
            profile = StudentProfile.objects.filter(user=self.user).first()
            if profile and profile.photo:
                import os
                if os.path.exists(profile.photo.path):
                    return f"{profile.photo.url}?v={int(os.path.getmtime(profile.photo.path))}"
                return profile.photo.url
        except Exception:
            pass
            
        return "/static/data/default_avatar.png"

    def save(self, *args, **kwargs):
        # Flag to prevent infinite recursion during sync
        if getattr(self, '_syncing', False):
            super().save(*args, **kwargs)
            return

        super().save(*args, **kwargs)

        # Sync common details to StudentProfile if it exists and both are approved
        from .models import StudentProfile
        try:
            prof = StudentProfile.objects.filter(user=self.user, status='admitted').first()
            if prof and self.status == 'approved':
                full_name = f"{self.first_name} {self.last_name}"
                sex = self.gender.capitalize() if self.gender else 'Male'
                if sex not in ['Male', 'Female', 'Other']:
                    sex = 'Male'
                
                if (prof.full_name != full_name or prof.sex != sex or prof.dob != self.dob or
                    prof.email != self.email or prof.whatsapp_number != self.whatsapp_number or
                    prof.mobile_number != self.mobile_number):
                    prof.full_name = full_name
                    prof.sex = sex
                    prof.dob = self.dob
                    prof.email = self.email
                    prof.whatsapp_number = self.whatsapp_number
                    prof.mobile_number = self.mobile_number
                    prof._syncing = True
                    prof.save()
        except Exception:
            pass

    def __str__(self):
        return f"{self.first_name} {self.last_name} - {self.short_achievement} ({self.status})"

# -------------------------------------------------------------------
# STUDENT PROGRESS & PERFORMANCE
# -------------------------------------------------------------------

class PerformanceRecord(models.Model):
    batch = models.CharField(max_length=50) # e.g., 'Grammar Batch 1', 'Library'
    topic = models.CharField(max_length=100) # e.g., 'Voice Test', 'Debate'
    total_marks = models.IntegerField(default=100)
    show_in_percentage = models.BooleanField(default=True)
    show_in_marks = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.batch} - {self.topic} ({self.created_at.date()})"

class StudentScore(models.Model):
    record = models.ForeignKey(PerformanceRecord, on_delete=models.CASCADE, related_name='scores')
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='performance_scores')
    marks_obtained = models.IntegerField(default=0)

    class Meta:
        unique_together = ('record', 'student')

    def __str__(self):
        return f"{self.student.full_name} - {self.marks_obtained}/{self.record.total_marks}"


# -------------------------------------------------------------------
# GUIDY – PRIVATE MENTORSHIP MESSAGING SYSTEM
# -------------------------------------------------------------------

class GuidanceRequest(models.Model):
    """
    Tracks a student's request to connect with an alumni (guide).
    A ChatSession is created only when the alumni accepts.
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='guidance_requests_sent',
        help_text="The student (Seeker) who sends the request"
    )
    alumni = models.ForeignKey(
        'StudentAchievement',
        on_delete=models.CASCADE,
        related_name='guidance_requests_received',
        help_text="The alumni profile being requested"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    message = models.TextField(blank=True, help_text="Optional introductory message from student")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # A student can only have one active request to a given alumni at a time
        unique_together = ('student', 'alumni')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.username} → {self.alumni.full_name} [{self.status}]"


class ChatSession(models.Model):
    """
    Created automatically when an alumni accepts a GuidanceRequest,
    or manually for direct 1-to-1 chats.
    """
    request = models.OneToOneField(
        GuidanceRequest,
        on_delete=models.CASCADE,
        related_name='chat_session',
        null=True,
        blank=True
    )
    user_one = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_sessions_one',
        null=True,
        blank=True
    )
    user_two = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_sessions_two',
        null=True,
        blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    session_ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def student(self):
        if self.request:
            return self.request.student
        return self.user_one

    @property
    def alumni(self):
        if self.request:
            return self.request.alumni
        return None

    def __str__(self):
        if self.request:
            return f"Chat: {self.request.student.username} ↔ {self.request.alumni.full_name}"
        u1_name = self.user_one.username if self.user_one else 'None'
        u2_name = self.user_two.username if self.user_two else 'None'
        return f"Chat: {u1_name} ↔ {u2_name}"


class DirectChatSession(models.Model):
    """
    Model for true 1-on-1 direct messaging, independent of GuidanceRequest.
    """
    user1 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='direct_sessions_one'
    )
    user2 = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='direct_sessions_two'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    ended_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    session_ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('user1', 'user2')

    def __str__(self):
        return f"Direct: {self.user1.username} ↔ {self.user2.username}"


class Message(models.Model):
    """
    Individual chat messages inside a ChatSession.
    Supports rich content types, threading, pinning, starring, and soft-delete.
    Files are transient — uploaded temporarily, not stored permanently in DB.
    """
    TYPE_TEXT = 'text'
    TYPE_IMAGE = 'image'
    TYPE_VIDEO = 'video'
    TYPE_DOCUMENT = 'document'
    TYPE_AUDIO = 'audio'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Text'),
        (TYPE_IMAGE, 'Image'),
        (TYPE_VIDEO, 'Video'),
        (TYPE_DOCUMENT, 'Document'),
        (TYPE_AUDIO, 'Audio'),
    ]

    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages',
        null=True,
        blank=True
    )
    direct_session = models.ForeignKey(
        DirectChatSession,
        on_delete=models.CASCADE,
        related_name='messages',
        null=True,
        blank=True
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='guidy_messages_sent'
    )
    content = models.TextField(blank=True)
    message_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default=TYPE_TEXT
    )
    # Transient file attachment — stored in temp folder
    file = models.FileField(
        upload_to='guidy_temp/',
        null=True,
        blank=True
    )
    file_name = models.CharField(max_length=255, blank=True)

    # Threading
    reply_to = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replies'
    )

    # Message state flags
    is_pinned = models.BooleanField(default=False)
    is_starred_by_sender = models.BooleanField(default=False)
    is_starred_by_receiver = models.BooleanField(default=False)
    is_deleted_for_sender = models.BooleanField(default=False)
    is_deleted_for_all = models.BooleanField(default=False)
    media_expired = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)
    deleted_by = models.ManyToManyField(
        User,
        related_name='deleted_messages',
        blank=True
    )

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        sess = self.session or self.direct_session
        return f"[{sess}] {self.sender.username}: {self.content[:50]}"


class BlockedGuidance(models.Model):
    """
    Records blocks between alumni and students — now bidirectional.
    direction='alumni_blocks_student': Alumni blocked the student (cannot re-request, session closed).
    direction='student_blocks_alumni': Student blocked the alumni (student cannot be messaged).
    Only admin can view/resolve via Django Admin.
    """
    DIRECTION_ALUMNI = 'alumni_blocks_student'
    DIRECTION_STUDENT = 'student_blocks_alumni'
    DIRECTION_CHOICES = [
        (DIRECTION_ALUMNI, 'Alumni blocks Student'),
        (DIRECTION_STUDENT, 'Student blocks Alumni'),
    ]

    alumni = models.ForeignKey(
        'StudentAchievement',
        on_delete=models.CASCADE,
        related_name='blocks_issued'
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='guidy_blocks_received'
    )
    direction = models.CharField(
        max_length=25,
        choices=DIRECTION_CHOICES,
        default=DIRECTION_ALUMNI
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('alumni', 'student', 'direction')
        ordering = ['-created_at']
        verbose_name = "Blocked Guidance"
        verbose_name_plural = "Blocked Guidance Records"

    def __str__(self):
        if self.direction == self.DIRECTION_ALUMNI:
            return f"BLOCKED (alumni→student): {self.student.username} by {self.alumni.full_name}"
        return f"BLOCKED (student→alumni): {self.student.username} blocked {self.alumni.full_name}"


class RestrictedStudent(models.Model):
    """
    Alumni restricts a student — different from blocking.
    The chat session remains in history but the student cannot send NEW guidance requests
    to this alumni again until the restriction is lifted.
    Alumni can manage this list from their Guidy interface.
    """
    alumni = models.ForeignKey(
        'StudentAchievement',
        on_delete=models.CASCADE,
        related_name='restricted_students'
    )
    student = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='guidy_restrictions'
    )
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('alumni', 'student')
        ordering = ['-created_at']
        verbose_name = "Restricted Student"
        verbose_name_plural = "Restricted Students"

    def __str__(self):
        return f"RESTRICTED: {self.student.username} by {self.alumni.full_name}"


class GroupChatSession(models.Model):
    """
    A multi-member group mentorship chat.
    Created by alumni; students are added as members.
    """
    name = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='created_guidy_groups'
    )
    members = models.ManyToManyField(
        User,
        related_name='guidy_groups',
        blank=True
    )
    photo = models.ImageField(
        upload_to='group_photos/',
        null=True,
        blank=True
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    deleted_by_user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deleted_guidy_groups'
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_for_users = models.ManyToManyField(
        User,
        related_name='cleared_guidy_groups',
        blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Group Chat Session"
        verbose_name_plural = "Group Chat Sessions"

    def __str__(self):
        return f"Group: {self.name} (by {self.created_by.username})"


class GroupMessage(models.Model):
    """
    A message inside a GroupChatSession.
    Supports same rich features as 1-to-1 Message.
    """
    TYPE_TEXT = 'text'
    TYPE_IMAGE = 'image'
    TYPE_VIDEO = 'video'
    TYPE_DOCUMENT = 'document'
    TYPE_AUDIO = 'audio'
    TYPE_SYSTEM = 'system'
    TYPE_CHOICES = [
        (TYPE_TEXT, 'Text'),
        (TYPE_IMAGE, 'Image'),
        (TYPE_VIDEO, 'Video'),
        (TYPE_DOCUMENT, 'Document'),
        (TYPE_AUDIO, 'Audio'),
        (TYPE_SYSTEM, 'System'),
    ]

    group = models.ForeignKey(
        GroupChatSession,
        on_delete=models.CASCADE,
        related_name='messages'
    )
    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='guidy_group_messages_sent'
    )
    content = models.TextField(blank=True)
    message_type = models.CharField(
        max_length=10,
        choices=TYPE_CHOICES,
        default=TYPE_TEXT
    )
    file = models.FileField(
        upload_to='guidy_temp/',
        null=True,
        blank=True
    )
    file_name = models.CharField(max_length=255, blank=True)
    reply_to = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='replies'
    )
    is_pinned = models.BooleanField(default=False)
    is_deleted_for_all = models.BooleanField(default=False)
    media_expired = models.BooleanField(default=False)
    timestamp = models.DateTimeField(auto_now_add=True)
    read_by = models.ManyToManyField(
        User,
        related_name='read_group_messages',
        blank=True
    )
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ManyToManyField(
        User,
        related_name='deleted_groupmessages',
        blank=True
    )
    starred_by = models.ManyToManyField(
        User,
        related_name='starred_groupmessages',
        blank=True
    )

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"[{self.group.name}] {self.sender.username}: {self.content[:50]}"

# -------------------------------------------------------------------
# SIGNALS for Fee System Hardening
# -------------------------------------------------------------------
from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=StudentProfile)
def cleanup_fee_notifications_on_change(sender, instance, **kwargs):
    """
    Handle Expiry Change (Point 5): 
    If expiry_date is removed (NULL) OR moved to future, 
    DELETE all existing fee notifications for that student.
    """
    today = timezone.localtime(timezone.now()).date()
    if instance.fee_expiry_date is None or instance.fee_expiry_date > today:
        # Delete for Student
        Notification.objects.filter(user=instance.user, category="fee").delete()
        # Delete for Teacher/Staff (alerts about this student)
        Notification.objects.filter(category="fee", meta__student_id=instance.id).delete()
        # Clean up dismissed fee alerts for this student when fee is extended/changed
        DismissedFeeAlert.objects.filter(student=instance).exclude(expiry_date=instance.fee_expiry_date).delete()


# ─────────────────────────────────────────────────────────────────────────────
# TO-DO HUB MODELS
# ─────────────────────────────────────────────────────────────────────────────

class TodoTask(models.Model):
    """
    Isolated Memory Buffer System (To-Do Hub).
    100% independent from financial models.
    """
    CATEGORY_CHOICES = [
        ('FEES', 'To Add Fees'),
        ('BREAKDOWN', 'Breakdown Tasks'),
        ('TODO', 'TO-DOs'),
        ('REMINDER', 'Reminders'),
        ('NOTE', 'Notebook'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='todo_hub_tasks'
    )
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    
    # Store ALL task data here. For Fees: [{"id": 1, "name": "Vikas", "amount": "500", "detail": "Library/F-44"}]
    metadata = models.JSONField(default=list, blank=True)
    
    auto_delete = models.BooleanField(default=True)
    delete_at = models.DateTimeField(null=True, blank=True)
    is_trash = models.BooleanField(default=False)
    trashed_at = models.DateTimeField(null=True, blank=True)
    is_done = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False)
    
    # For notification engine tracking
    last_notified_at = models.DateTimeField(null=True, blank=True)
    initial_notified = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        app_label = 'users'

    def __str__(self):
        return f"{self.user.username} | {self.category} | {self.created_at.date()}"


@receiver(post_save, sender=User)
def send_welcome_email_on_registration(sender, instance, created, **kwargs):
    if created and instance.email:
        try:
            from users.email_service import send_html_email
            from django.urls import reverse
            
            login_url = f"{settings.SITE_URL}{reverse('users:login')}"
            
            send_html_email(
                subject="Welcome to ABCD Coaching & Library!",
                to_email=instance.email,
                template="emails/welcome_email.html",
                context={
                    "username": instance.username,
                    "login_url": login_url,
                },
                fail_silently=True
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send welcome email to {instance.email}: {e}")


@receiver(post_delete, sender=Message)
@receiver(post_delete, sender=GroupMessage)
def auto_delete_chat_media_on_delete(sender, instance, **kwargs):
    """Physically deletes the file from storage (Local / Cloudinary) when the message row is deleted."""
    if instance.file:
        try:
            instance.file.delete(save=False)
        except Exception:
            try:
                if hasattr(instance.file, 'path') and os.path.isfile(instance.file.path):
                    os.remove(instance.file.path)
            except Exception:
                pass


class TeacherProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='teacher_profile')
    display_name = models.CharField(max_length=100, blank=True)
    role_title = models.CharField(max_length=100, blank=True, default='Teacher')
    mobile_number = models.CharField(max_length=15, blank=True)
    detail1 = models.CharField(max_length=150, blank=True)
    detail2 = models.CharField(max_length=150, blank=True)
    detail3 = models.CharField(max_length=150, blank=True)
    about = models.TextField(blank=True)
    photo = models.ImageField(upload_to='teacher_photos/', blank=True, null=True)
    emails = models.TextField(blank=True, default='')
    mobile_numbers = models.TextField(blank=True, default='')
    whatsapp_numbers = models.TextField(blank=True, default='')

    class Meta:
        app_label = 'users'

    def __str__(self):
        return f"Teacher: {self.display_name or self.user.username}"


@receiver(post_save, sender=User)
def create_teacher_profile(sender, instance, created, **kwargs):
    if instance.is_staff or instance.is_superuser:
        profile, created_profile = TeacherProfile.objects.get_or_create(user=instance)
        if created_profile:
            if instance.email == 'abcd2013baq@gmail.com':
                profile.display_name = 'Sandeep Sir'
                profile.role_title = 'Teacher'
                profile.detail1 = 'Founder & Head Faculty'
                profile.detail2 = 'English Grammar & Spoken Teacher'
                profile.detail3 = 'Library Owner'
                profile.about = 'Sandeep Sir is known for his clear explanations, disciplined teaching style and friendly nature. Since 2013, hundreds of students from Basoda and nearby areas have improved their grammar, written English and confidence with his guidance.'
            elif instance.email == 'vd19055@gmail.com':
                profile.display_name = 'ABCD Asst.'
                profile.role_title = 'Vikas Dangi'
                profile.detail1 = 'Software Engg.'
                profile.detail2 = 'Tech Support / helpline of ABCD'
                profile.detail3 = 'Support Helpline'
                profile.about = 'Technical support and helpline assistant for ABCD. Contact for software, platform, or account issues.'
            else:
                profile.display_name = instance.get_full_name() or instance.username
                profile.role_title = 'Teacher'
            profile.save()


@receiver(pre_save, sender=StudentProfile)
@receiver(pre_save, sender=StudentAchievement)
@receiver(pre_save, sender=GroupChatSession)
@receiver(pre_save, sender=TeacherProfile)
@receiver(pre_save, sender=Course)
@receiver(pre_save, sender=StudyMaterial)
@receiver(pre_save, sender=BroadcastMessage)
def auto_delete_file_on_change(sender, instance, **kwargs):
    """Deletes old physical file from storage (Local / Cloudinary) when a new file is uploaded or cleared."""
    if not instance.pk:
        return False

    try:
        old_instance = sender.objects.get(pk=instance.pk)
    except sender.DoesNotExist:
        return False

    file_fields = ['photo', 'thumbnail', 'file', 'attachment', 'banner_image']
    for field_name in file_fields:
        old_file = getattr(old_instance, field_name, None)
        new_file = getattr(instance, field_name, None)
        if old_file and old_file != new_file:
            try:
                old_file.delete(save=False)
            except Exception:
                try:
                    if hasattr(old_file, 'path') and os.path.isfile(old_file.path):
                        os.remove(old_file.path)
                except Exception:
                    pass


@receiver(post_delete, sender=StudentProfile)
@receiver(post_delete, sender=StudentAchievement)
@receiver(post_delete, sender=GroupChatSession)
@receiver(post_delete, sender=TeacherProfile)
@receiver(post_delete, sender=StudyMaterial)
@receiver(post_delete, sender=BroadcastMessage)
def auto_delete_file_on_delete(sender, instance, **kwargs):
    """Deletes physical file from storage (Local / Cloudinary) when the instance is completely deleted."""
    file_fields = ['photo', 'thumbnail', 'file', 'attachment', 'banner_image']
    for field_name in file_fields:
        file = getattr(instance, field_name, None)
        if file:
            try:
                file.delete(save=False)
            except Exception:
                try:
                    if hasattr(file, 'path') and os.path.isfile(file.path):
                        os.remove(file.path)
                except Exception:
                    pass


@receiver(post_delete, sender=Course)
def auto_delete_course_files_on_delete(sender, instance, **kwargs):
    """Deletes course thumbnail and all associated study material files from storage (Local / Cloudinary)."""
    if instance.thumbnail:
        try:
            instance.thumbnail.delete(save=False)
        except Exception:
            try:
                if hasattr(instance.thumbnail, 'path') and os.path.isfile(instance.thumbnail.path):
                    os.remove(instance.thumbnail.path)
            except Exception:
                pass

    for mat in instance.materials.all():
        for field in [mat.file, mat.thumbnail]:
            if field:
                try:
                    field.delete(save=False)
                except Exception:
                    try:
                        if hasattr(field, 'path') and os.path.isfile(field.path):
                            os.remove(field.path)
                    except Exception:
                        pass


class GuidyBlock(models.Model):
    blocker = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_users')
    blocked = models.ForeignKey(User, on_delete=models.CASCADE, related_name='blocked_by_users')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('blocker', 'blocked')
        verbose_name = "Guidy Block"
        verbose_name_plural = "Guidy Block Records"

    def __str__(self):
        return f"{self.blocker.username} blocked {self.blocked.username}"


@receiver(post_save, sender=Notification)
def dispatch_realtime_notification_on_save(sender, instance, created, **kwargs):
    """
    Dispatches instant real-time WebSocket event and Web Push notification whenever
    any Notification record is created in the entire application.
    """
    if not created or not instance.user:
        return

    # 1. Real-time WebSocket event via Django Channels
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        cl = get_channel_layer()
        if cl:
            # Send to user's personal channel group
            async_to_sync(cl.group_send)(
                f"user_{instance.user.id}",
                {
                    "type": "notification",
                    "title": instance.title,
                    "message": instance.message,
                    "link": instance.link or "/",
                    "category": instance.category,
                }
            )

            # If user is staff/teacher or notification is related to admissions/holds/complaints
            if instance.user.is_staff or instance.user.is_superuser:
                async_to_sync(cl.group_send)(
                    "teachers",
                    {
                        "type": "dashboard_stats_update",
                        "title": instance.title,
                        "message": instance.message,
                    }
                )
                async_to_sync(cl.group_send)(
                    "staff_group",
                    {
                        "type": "dashboard_stats_update",
                        "title": instance.title,
                        "message": instance.message,
                    }
                )
    except Exception as e:
        logger.debug("Realtime notification channel broadcast error: %s", e)

    # 2. Asynchronous Web Push notification to user devices
    try:
        import threading
        from .notifications import send_push
        threading.Thread(
            target=send_push,
            args=(instance.user, instance.title, instance.message, instance.link or "/"),
            daemon=True
        ).start()
    except Exception as e:
        logger.debug("Realtime notification web push dispatch error: %s", e)




