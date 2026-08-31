# users/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import StudentProfile, Complaint, Seat, SeatAssignment, StudentAchievement
import re
from django.db.models import Q
from django.core.exceptions import ValidationError


class InitialRegisterForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email'})
    )

    class Meta(UserCreationForm.Meta):
        model = User
        # include email so form.cleaned_data has it
        fields = ('username', 'email')

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "This email is already registered. Please login or use Forgot Password."
            )
        return email

# -------------------------------------------------------------------
# STUDENT PROFILE FORM
class StudentProfileForm(forms.ModelForm):
    
    first_name = forms.CharField(
        max_length=50, required=True, 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your first name'})
    )
    last_name = forms.CharField(
        max_length=50, required=True, 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your last name'})
    )
    email = forms.EmailField(
        required=False, 
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter email address (optional)'})
    )
    is_new_registration = forms.ChoiceField(
        choices=[('True', 'New Student'), ('False', 'Already Admitted Student')], 
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    confirmation = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={'id': 'id_confirmation'})
    )
    same_as_mobile = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'id': 'id_same_as_mobile'})
    )
    dob = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={
                'type': 'date',
                'class': 'form-control dob-input'
            }
        )
    )

    photo = forms.ImageField(
        required=False,
        widget=forms.ClearableFileInput(
            attrs={
                'class': 'form-control photo-input',
                'accept': 'image/*'
            }
        )
    )

    # Hidden fields for JS to populate
    floor = forms.CharField(required=False, widget=forms.HiddenInput())
    selected_seat = forms.CharField(required=False, widget=forms.HiddenInput())
    
    # --- NEW: Hidden fields for Shift & Temporary Requests ---
    shift_preference = forms.CharField(required=False, widget=forms.HiddenInput())
    is_temporary_request = forms.CharField(required=False, widget=forms.HiddenInput())
    temp_hold_days = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = StudentProfile
        # Added 'dob' and 'photo' here
        fields = [
            'sex', 'sex_other', 'dob', 'service_type', 'batch', 
            'mobile_number', 'whatsapp_number', 'photo'
        ]
        widgets = {
            'sex': forms.Select(attrs={'class': 'form-control'}),
            'sex_other': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Please specify your gender'}),
                       
            'service_type': forms.Select(attrs={'class': 'form-control'}),
            'batch': forms.Select(attrs={'class': 'form-control'}),
            'mobile_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter 10-digit mobile number',
                'pattern': '[6-9][0-9]{9}',
                'maxlength': '10'
            }),
            'whatsapp_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter 10-digit WhatsApp number',
                'pattern': '[6-9][0-9]{9}',
                'maxlength': '10'
            }),
        }

    def __init__(self, *args, **kwargs):
        disabled_services = kwargs.pop('disabled_services', [])
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Modify service_type choices dynamically
        if 'service_type' in self.fields:
            orig_choices = self.fields['service_type'].choices
            new_choices = [c for c in orig_choices if c[0] not in disabled_services]
            self.fields['service_type'].choices = new_choices

        if user:
            # Check if user already has an achievement profile or existing student profile
            # to lock common fields
            from .models import StudentAchievement, StudentProfile
            existing_ach = StudentAchievement.objects.filter(user=user).first()
            existing_prof = StudentProfile.objects.filter(user=user).first()
            
            existing = existing_ach or existing_prof
            if existing:
                # Pre-populate and disable name, sex, dob fields
                if existing_ach:
                    first_name = existing_ach.first_name
                    last_name = existing_ach.last_name
                    sex = existing_ach.gender.capitalize() if existing_ach.gender else 'Male'
                    if sex not in ['Male', 'Female', 'Other']:
                        sex = 'Male'
                    dob = existing_ach.dob
                else:
                    first_name, *rest = (existing_prof.full_name or '').split(' ', 1)
                    last_name = rest[0] if rest else ''
                    sex = existing_prof.sex
                    dob = existing_prof.dob

                self.initial['first_name'] = first_name
                self.initial['last_name'] = last_name
                self.initial['sex'] = sex
                self.initial['dob'] = dob

                self.fields['first_name'].disabled = True
                self.fields['last_name'].disabled = True
                self.fields['sex'].disabled = True
                self.fields['dob'].disabled = True

        # Pre-populate email from existing profile, achievement, or user model
        if 'email' in self.fields and not self.initial.get('email'):
            if self.instance and getattr(self.instance, 'email', None):
                self.initial['email'] = self.instance.email
            elif user:
                from .models import StudentAchievement, StudentProfile
                existing_prof = StudentProfile.objects.filter(user=user).first()
                existing_ach = StudentAchievement.objects.filter(user=user).first()
                self.initial['email'] = (existing_prof.email if existing_prof and existing_prof.email else None) or \
                                        (existing_ach.email if existing_ach and existing_ach.email else None) or \
                                        (user.email if user.email else '')

    def clean_first_name(self):
        first_name = self.cleaned_data['first_name']
        if not re.match(r'^[A-Za-z ]+$', first_name):
            raise forms.ValidationError('First name can only contain letters and spaces.')
        return first_name

    def clean_last_name(self):
        last_name = self.cleaned_data['last_name']
        if not re.match(r'^[A-Za-z ]+$', last_name):
            raise forms.ValidationError('Last name can only contain letters and spaces.')
        return last_name
        
    def clean_mobile_number(self):
        mobile_number = self.cleaned_data.get('mobile_number', '')
        if not re.match(r'^[6-9]\d{9}$', mobile_number):
            raise forms.ValidationError('Mobile number must be 10 digits starting with 6-9.')
        return mobile_number

    def clean_whatsapp_number(self):
        whatsapp_number = self.cleaned_data.get('whatsapp_number', '')
        if not re.match(r'^[6-9]\d{9}$', whatsapp_number):
            raise forms.ValidationError('Whatsapp number must be 10 digits starting with 6-9.')
        return whatsapp_number

    def clean(self):
        cleaned_data = super().clean()

        sex = cleaned_data.get('sex')
        sex_other = cleaned_data.get('sex_other')
        service_type = cleaned_data.get('service_type')
        batch = cleaned_data.get('batch')

        floor = (cleaned_data.get('floor') or '').strip()
        selected_seat = (cleaned_data.get('selected_seat') or '').strip()

        # Fallback to POST data if hidden fields failed to bind
        if not floor:
            floor = (self.data.get('floor') or self.data.get('floor_radio') or '').strip()
        if not selected_seat:
            selected_seat = (self.data.get('selected_seat') or '').strip()
            
        # Capture shift preference
        shift_pref = (self.data.get('shift_preference') or self.data.get('shift_hidden') or 'full').strip()

        cleaned_data['floor'] = floor
        cleaned_data['selected_seat'] = selected_seat
        cleaned_data['shift_preference'] = shift_pref

        if sex == 'Other' and not sex_other:
            self.add_error('sex_other', 'Please specify gender when selecting "Other".')

        if service_type == 'Coaching' and not batch:
            self.add_error('batch', 'Please select a batch for coaching.')

        if service_type == 'Library':
            if not floor or not selected_seat:
                self.add_error(None, 'Please select a library floor and seat to proceed.')

        # --------------------------------------------------
        # STEP 3.2 — BACKEND SEAT + SHIFT VALIDATION
        # --------------------------------------------------
        if service_type == 'Library' and floor and selected_seat:

            try:
                seat = Seat.objects.get(
                    floor=floor,
                    seat_number=str(selected_seat)
                )
            except Seat.DoesNotExist:
                raise ValidationError("Selected seat does not exist on this floor.")

            # Hold seats are now allowed IF student requests temporary allotment
            # Backend views.py will handle temporary request flag
            # Form only validates that seat exists

            # Validate shift value
            if seat.is_shift_enabled:
                if shift_pref not in ('full', 'morning', 'evening'):
                    raise ValidationError("Invalid shift selection for this seat.")
            else:
                if shift_pref != 'full':
                    raise ValidationError(
                        "This seat does not support shift-based selection."
                    )

            # Enforce shift conflicts using SeatAssignment rules
            try:
                # Check if this is a temporary request
                is_temp_req = cleaned_data.get('is_temporary_request') == 'true'

                dummy_assignment = SeatAssignment(
                    seat=seat,
                    student=None,      # placeholder (no DB save)
                    shift_type=shift_pref,
                    is_active=True,
                    is_partial=is_temp_req
                )
                dummy_assignment.clean()
            except ValidationError as e:
                raise ValidationError(e.messages[0])


        if not cleaned_data.get('confirmation'):
            self.add_error('confirmation', 'Please confirm that the information is correct.')

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.full_name = f"{self.cleaned_data['first_name']} {self.cleaned_data['last_name']}"
        email_val = self.cleaned_data.get('email')
        if email_val:
            instance.email = email_val
        elif not instance.email and hasattr(instance, 'user') and instance.user and instance.user.email:
            instance.email = instance.user.email
        if commit:
            instance.save()
        return instance
    
# -------------------------------------------------------------------
# EDIT STUDENT PROFILE FORM
class EditStudentProfileForm(forms.ModelForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = StudentProfile
        fields = [
            'full_name', 'sex', 'dob', 'status', 'service_type',
            'batch', 'mobile_number', 'whatsapp_number', 'photo', 'email'
        ]
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        self.user_editing = kwargs.pop('user_editing', None)
        super().__init__(*args, **kwargs)
        
        # Initialize email from StudentProfile or fallback to User model
        if self.instance:
            self.initial['email'] = self.instance.email or (self.instance.user.email if self.instance.user else '')

        # If student is editing, restrict sensitive fields
        if self.user_editing and not self.user_editing.is_staff:
            restricted_fields = ['status', 'service_type', 'batch']
            for field_name in restricted_fields:
                if field_name in self.fields:
                    self.fields[field_name].disabled = True
            if 'email' in self.fields:
                self.fields['email'].disabled = True

            # Lock common details if any profile is pending approval
            from .models import StudentProfile, StudentAchievement
            profile_pending = StudentProfile.objects.filter(user=self.user_editing, status='pending').exists()
            ach_pending = StudentAchievement.objects.filter(user=self.user_editing, status='pending').exists()
            if profile_pending or ach_pending:
                if 'full_name' in self.fields:
                    self.fields['full_name'].disabled = True
                if 'sex' in self.fields:
                    self.fields['sex'].disabled = True
                if 'dob' in self.fields:
                    self.fields['dob'].disabled = True

        # Common styling
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-control'})
        
        # Specific widgets
        self.fields['dob'].widget = forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
        self.fields['photo'].widget = forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'})

    def clean_full_name(self):
        name = self.cleaned_data.get('full_name')
        if name and not re.match(r'^[A-Za-z ]+$', name):
            raise forms.ValidationError('Name can only contain letters and spaces.')
        return name

    def clean_mobile_number(self):
        mobile = self.cleaned_data.get('mobile_number', '')
        if mobile and not re.match(r'^[6-9]\d{9}$', mobile):
            raise forms.ValidationError('Invalid mobile number.')
        return mobile

    def clean_whatsapp_number(self):
        whatsapp = self.cleaned_data.get('whatsapp_number', '')
        if whatsapp and not re.match(r'^[6-9]\d{9}$', whatsapp):
            raise forms.ValidationError('Invalid WhatsApp number.')
        return whatsapp

    def save(self, commit=True):
        student = super().save(commit=False)
        
        email = self.cleaned_data.get('email')
        if email:
            student.email = email
            # Only set user.email if the User model has no email at all (e.g. manual student created without email)
            if student.user and not student.user.email:
                student.user.email = email
                student.user.save(update_fields=['email'])

        # Sync name parts
        if student.user:
            full_name = self.cleaned_data.get('full_name')
            if full_name:
                parts = full_name.split()
                student.user.first_name = parts[0] if len(parts) > 0 else ""
                student.user.last_name = " ".join(parts[1:]) if len(parts) > 1 else ""
                student.user.save(update_fields=['first_name', 'last_name'])

        if commit:
            student.save()
        return student


# -------------------------------------------------------------------
# COMPLAINT MODEL
# -------------------------------------------------------------------
class ComplaintForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = [
            "subject",
            "custom_subject",
            "message",
            "image1",
            "image2",
            "image3",
        ]
        widgets = {
            "subject": forms.Select(attrs={"class": "form-control"}),
            "custom_subject": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Write your complaint subject…",
                }
            ),
            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Describe your issue in a few lines…",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        subject = cleaned.get("subject")
        custom_subject = (cleaned.get("custom_subject") or "").strip()

        if subject == Complaint.SUBJECT_OTHER and not custom_subject:
            self.add_error(
                "custom_subject",
                "Please enter a subject when choosing 'Anything else'.",
            )
        return cleaned


class ComplaintRatingForm(forms.ModelForm):
    class Meta:
        model = Complaint
        fields = ["rating", "feedback"]
        widgets = {
            "rating": forms.NumberInput(
                attrs={"min": 1, "max": 5, "class": "form-control"}
            ),
            "feedback": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 3,
                    "placeholder": "Optional feedback about how your issue was handled",
                }
            ),
        }

class StudentAchievementForm(forms.ModelForm):
    class Meta:
        model = StudentAchievement
        fields = [
            'first_name', 'last_name', 'about_yourself', 'current_post', 'selection_year',
            'working_city', 'short_achievement', 'gender', 'dob', 'photo',
            'services_used', 'duration_years', 'duration_days',
            'mobile_number', 'whatsapp_number', 'email',
            'experience_feedback', 'rating', 'abcd_feedback'
        ]
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'about_yourself': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Write something positive about yourself...'}),
            'experience_feedback': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'How was your experience with us?'}),
            'abcd_feedback': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Your feedback for ABCD...'}),
            'rating': forms.HiddenInput(attrs={'id': 'id_rating_value'}), 
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'services_used': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            from .models import StudentAchievement, StudentProfile
            existing_ach = StudentAchievement.objects.filter(user=user).first()
            existing_prof = StudentProfile.objects.filter(user=user).first()
            
            existing = existing_ach or existing_prof
            if existing:
                # Pre-populate and disable name, sex, dob fields
                if existing_ach:
                    first_name = existing_ach.first_name
                    last_name = existing_ach.last_name
                    gender = existing_ach.gender
                    dob = existing_ach.dob
                else:
                    first_name, *rest = (existing_prof.full_name or '').split(' ', 1)
                    last_name = rest[0] if rest else ''
                    gender = existing_prof.sex.capitalize() if existing_prof.sex else 'Male'
                    if gender not in ['Male', 'Female', 'Other']:
                        gender = 'Male'
                    dob = existing_prof.dob

                if not first_name:
                    first_name = user.first_name or user.username
                if not last_name:
                    last_name = user.last_name or ''

                self.initial['first_name'] = first_name
                self.initial['last_name'] = last_name
                self.initial['gender'] = gender
                self.initial['dob'] = dob

                self.fields['first_name'].disabled = True
                self.fields['last_name'].disabled = True
                self.fields['gender'].disabled = True
                self.fields['dob'].disabled = True

            # Pre-populate email from existing profile, achievement, or user model
            if 'email' in self.fields and not self.initial.get('email'):
                if self.instance and getattr(self.instance, 'email', None):
                    self.initial['email'] = self.instance.email
                else:
                    self.initial['email'] = (existing_ach.email if existing_ach and existing_ach.email else None) or \
                                            (existing_prof.email if existing_prof and existing_prof.email else None) or \
                                            (user.email if user.email else '')
        # Apply form-control to all fields except photo
        for field_name, field in self.fields.items():
            if field_name != 'photo':
                existing_classes = field.widget.attrs.get('class', '')
                if 'form-control' not in existing_classes:
                    field.widget.attrs['class'] = (existing_classes + ' form-control').strip()
            
            # Placeholders
            if field_name == 'first_name':
                field.widget.attrs['placeholder'] = 'Enter your first name'
            elif field_name == 'last_name':
                field.widget.attrs['placeholder'] = 'Enter your last name'
            elif field_name == 'current_post':
                field.widget.attrs['placeholder'] = 'e.g. Sub-Inspector (2023)'
            elif field_name == 'working_city':
                field.widget.attrs['placeholder'] = 'City where you are working'
            elif field_name == 'short_achievement':
                field.widget.attrs['placeholder'] = 'e.g. SI Delhi Police'
            elif field_name == 'mobile_number':
                field.widget.attrs['placeholder'] = '10-digit Mobile Number'
            elif field_name == 'whatsapp_number':
                field.widget.attrs['placeholder'] = '10-digit WhatsApp Number'
            elif field_name == 'email':
                field.widget.attrs['placeholder'] = 'Your Email Address'


class EditAlumniProfileForm(forms.ModelForm):
    """Full edit form for alumni — edits all personal and achievement details
    without touching approval status."""

    class Meta:
        model = StudentAchievement
        fields = [
            'first_name', 'last_name', 'about_yourself', 'current_post', 'selection_year',
            'working_city', 'short_achievement', 'gender', 'dob', 'photo',
            'services_used', 'duration_years', 'duration_days',
            'mobile_number', 'whatsapp_number', 'email',
            'experience_feedback', 'rating', 'abcd_feedback'
        ]
        widgets = {
            'dob': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'photo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'about_yourself': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Write something positive about yourself...',
            }),
            'experience_feedback': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'How was your experience with us?',
            }),
            'abcd_feedback': forms.Textarea(attrs={
                'class': 'form-control', 'rows': 3,
                'placeholder': 'Your feedback for ABCD...',
            }),
            'rating': forms.HiddenInput(attrs={'id': 'id_rating_value'}),
            'gender': forms.Select(attrs={'class': 'form-control'}),
            'services_used': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user_editing = kwargs.pop('user_editing', None)
        super().__init__(*args, **kwargs)

        if user_editing and not user_editing.is_staff:
            # Check if any profile is currently pending approval
            from .models import StudentProfile, StudentAchievement
            profile_pending = StudentProfile.objects.filter(user=user_editing, status='pending').exists()
            ach_pending = StudentAchievement.objects.filter(user=user_editing, status='pending').exists()
            if profile_pending or ach_pending:
                if 'first_name' in self.fields:
                    self.fields['first_name'].disabled = True
                if 'last_name' in self.fields:
                    self.fields['last_name'].disabled = True
                if 'gender' in self.fields:
                    self.fields['gender'].disabled = True
                if 'dob' in self.fields:
                    self.fields['dob'].disabled = True
        for field_name, field in self.fields.items():
            if field_name != 'photo':
                existing = field.widget.attrs.get('class', '')
                if 'form-control' not in existing:
                    field.widget.attrs['class'] = (existing + ' form-control').strip()

            # Placeholders
            placeholders = {
                'first_name': 'Enter your first name',
                'last_name': 'Enter your last name',
                'current_post': 'e.g. Sub-Inspector (2023)',
                'working_city': 'City where you are working',
                'short_achievement': 'e.g. SI Delhi Police',
                'mobile_number': '10-digit Mobile Number',
                'whatsapp_number': '10-digit WhatsApp Number',
                'email': 'Your Email Address',
            }
            if field_name in placeholders:
                field.widget.attrs['placeholder'] = placeholders[field_name]

    def clean_first_name(self):
        name = self.cleaned_data.get('first_name')
        if name and not re.match(r'^[A-Za-z ]+$', name):
            raise forms.ValidationError('Name can only contain letters and spaces.')
        return name

    def clean_last_name(self):
        name = self.cleaned_data.get('last_name')
        if name and not re.match(r'^[A-Za-z ]+$', name):
            raise forms.ValidationError('Name can only contain letters and spaces.')
        return name

    def clean_mobile_number(self):
        mobile = self.cleaned_data.get('mobile_number', '')
        if mobile and not re.match(r'^[6-9]\d{9}$', mobile):
            raise forms.ValidationError('Invalid mobile number.')
        return mobile

    def clean_whatsapp_number(self):
        whatsapp = self.cleaned_data.get('whatsapp_number', '')
        if whatsapp and not re.match(r'^[6-9]\d{9}$', whatsapp):
            raise forms.ValidationError('Invalid WhatsApp number.')
        return whatsapp

    def save(self, commit=True):
        achievement = super().save(commit=False)
        email = self.cleaned_data.get('email')
        if email:
            achievement.email = email
            # Only set user.email if User model currently has no email at all
            if achievement.user and not achievement.user.email:
                achievement.user.email = email
                achievement.user.save(update_fields=['email'])

        # Sync User model first/last name
        if achievement.user:
            achievement.user.first_name = achievement.first_name
            achievement.user.last_name = achievement.last_name
            achievement.user.save(update_fields=['first_name', 'last_name'])
        if commit:
            achievement.save()
        return achievement
