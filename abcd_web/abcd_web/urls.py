# this is abcd_web/urls.py

"""
URL configuration for abcd_web project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.http import JsonResponse
from django.views.generic import RedirectView
from django.conf import settings
from django.views.static import serve
from users.views import robots_txt_view, sitemap_xml_view, cron_maintenance_view, service_worker_view, vapid_public_key_api, assetlinks_json_view, email_diagnostics_view

def ping_view(request):
    """
    Ultra-lightweight keep-alive & health check endpoint for UptimeRobot.
    Supports ?debug=student for checking student profile & user database state.
    """
    data = {
        "status": "ok",
        "service": "ABCD Smart Campus",
        "uptime": "active"
    }
    if request.GET.get('debug') == 'student':
        try:
            from django.contrib.auth.models import User
            from users.models import StudentProfile
            st_list = list(StudentProfile.objects.filter(full_name__icontains='Google').values(
                'id', 'user_id', 'full_name', 'status', 'service_type', 'batch', 'seat_id', 'hold_start_date', 'hold_end_date'
            ))
            if not st_list:
                st_list = list(StudentProfile.objects.filter(id__in=[52, 56]).values(
                    'id', 'user_id', 'full_name', 'status', 'service_type', 'batch', 'seat_id', 'hold_start_date', 'hold_end_date'
                ))
            u_list = list(User.objects.filter(username__icontains='google').values('id', 'username', 'email', 'first_name', 'last_name'))
            if not u_list:
                u_list = list(User.objects.filter(id__in=[52, 56]).values('id', 'username', 'email', 'first_name', 'last_name'))
            data["google_profiles"] = st_list
            data["google_users"] = u_list
        except Exception as e:
            data["debug_error"] = str(e)
    return JsonResponse(data)

urlpatterns = [
    # Root PWA Service Worker (with Service-Worker-Allowed: /)
    path('sw.js', service_worker_view, name='service_worker'),

    # VAPID Public Key API endpoint
    path('api/vapid-public-key/', vapid_public_key_api, name='vapid_public_key_api'),

    # Android TWA & Google Play Store Digital Asset Links
    path('.well-known/assetlinks.json', assetlinks_json_view, name='assetlinks_json'),

    # 24/7 Keep-Alive & Light Health Check Endpoints (Zero-DB, ~30 bytes)
    re_path(r'^(?:healthz|health|ping)/?$', ping_view, name='healthz'),


    # 24/7 Dedicated External Cron Maintenance Webhook (cron-job.org / Admin)
    path('api/cron/maintenance/', cron_maintenance_view, name='cron_maintenance'),

    # Real-Time Production Email Diagnostics Endpoint
    path('api/diag/email-test/', email_diagnostics_view, name='email_diagnostics'),

    path('admin/', admin.site.urls),

    # Browser default favicon & SEO icons
    path('favicon.ico', RedirectView.as_view(url='/static/data/favicon/favicon.ico', permanent=True)),
    path('favicon.png', RedirectView.as_view(url='/static/data/favicon/favicon-96x96.png', permanent=True)),
    path('apple-touch-icon.png', RedirectView.as_view(url='/static/data/favicon/apple-touch-icon.png', permanent=True)),
    path('apple-touch-icon-precomposed.png', RedirectView.as_view(url='/static/data/favicon/apple-touch-icon.png', permanent=True)),
    path('site.webmanifest', RedirectView.as_view(url='/static/data/favicon/site.webmanifest', permanent=True)),
    path('manifest.json', RedirectView.as_view(url='/static/data/favicon/site.webmanifest', permanent=True)),
    path('web-app-manifest-192x192.png', RedirectView.as_view(url='/static/data/favicon/web-app-manifest-192x192.png', permanent=True)),
    path('web-app-manifest-512x512.png', RedirectView.as_view(url='/static/data/favicon/web-app-manifest-512x512.png', permanent=True)),
    path('robots.txt', robots_txt_view, name='robots_txt'),
    path('sitemap.xml', sitemap_xml_view, name='sitemap_xml'),

    # All your app's URLs, including the home page, are now handled here
    path('', include('users.urls')),
    path('auth/', include('social_django.urls', namespace='social')),
]

# Media files serving (Local development or fallback when Cloudinary is not configured)
# In production with Cloudinary, media files load directly from Cloudinary CDN to protect Render bandwidth.
if settings.DEBUG or not getattr(settings, 'CLOUDINARY_CLOUD_NAME', None):
    urlpatterns.insert(len(urlpatterns) - 2, re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}))