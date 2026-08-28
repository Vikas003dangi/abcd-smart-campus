# users/templatetags/admin_live_stats.py
from django import template
from django.contrib.auth.models import User
from users.models import (
    StudentProfile, Seat, Course, StudyMaterial, 
    Complaint, Payment, ChatSession, BroadcastMessage
)

register = template.Library()

@register.simple_tag
def get_admin_live_stats():
    """
    Fetches real-time live database statistics and metadata
    for the Master Admin Control Center dashboard.
    """
    try:
        total_users = User.objects.count()
        total_staff = User.objects.filter(is_staff=True).count()
        
        # Student Breakdown
        total_students = StudentProfile.objects.count()
        admitted_students = StudentProfile.objects.filter(status='admitted').count()
        pending_students = StudentProfile.objects.filter(status='pending').count()
        on_hold_students = StudentProfile.objects.filter(status='on_hold').count()
        coaching_students = StudentProfile.objects.filter(service_type='Coaching').count()
        library_students = StudentProfile.objects.filter(service_type='Library').count()

        # Seat Statistics
        total_seats = Seat.objects.count()
        available_seats = Seat.objects.filter(status='available').count()
        occupied_seats = Seat.objects.filter(status='occupied').count()
        on_hold_seats = Seat.objects.filter(status='on_hold').count()

        # Courses & Academy
        total_courses = Course.objects.count()
        total_materials = StudyMaterial.objects.count()

        # Complaints & Support
        pending_complaints = Complaint.objects.filter(status='pending').count()
        total_complaints = Complaint.objects.count()
        total_chats = ChatSession.objects.count()

        # Payments
        total_payments = Payment.objects.count()
        total_broadcasts = BroadcastMessage.objects.count()

        return {
            'total_users': total_users,
            'total_staff': total_staff,
            'total_students': total_students,
            'admitted_students': admitted_students,
            'pending_students': pending_students,
            'on_hold_students': on_hold_students,
            'coaching_students': coaching_students,
            'library_students': library_students,
            'total_seats': total_seats,
            'available_seats': available_seats,
            'occupied_seats': occupied_seats,
            'on_hold_seats': on_hold_seats,
            'total_courses': total_courses,
            'total_materials': total_materials,
            'pending_complaints': pending_complaints,
            'total_complaints': total_complaints,
            'total_chats': total_chats,
            'total_payments': total_payments,
            'total_broadcasts': total_broadcasts,
        }
    except Exception as e:
        # Fallback safe defaults in case of any schema differences
        return {
            'total_users': 0,
            'total_staff': 0,
            'total_students': 0,
            'admitted_students': 0,
            'pending_students': 0,
            'on_hold_students': 0,
            'coaching_students': 0,
            'library_students': 0,
            'total_seats': 106,
            'available_seats': 0,
            'occupied_seats': 0,
            'on_hold_seats': 0,
            'total_courses': 0,
            'total_materials': 0,
            'pending_complaints': 0,
            'total_complaints': 0,
            'total_chats': 0,
            'total_payments': 0,
            'total_broadcasts': 0,
        }
