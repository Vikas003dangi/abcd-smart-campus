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
from users.views import robots_txt_view, sitemap_xml_view, cron_maintenance_view, service_worker_view, vapid_public_key_api

def ping_view(request):
    """
    Ultra-lightweight keep-alive & health check endpoint for UptimeRobot and cron-job.org.
    Responds in ~1ms while opportunistically catching up any due tasks in the background.
    """
    try:
        from users.scheduler import last_scheduler_run, run_scheduler_cycle
        from django.utils import timezone
        import threading
        now = timezone.now()
        # If scheduler hasn't ticked in 15 minutes (e.g. Render server was sleeping), catch up in thread
        if not last_scheduler_run or (now - last_scheduler_run).total_seconds() > 900:
            threading.Thread(target=run_scheduler_cycle, kwargs={'mode': 'all'}, daemon=True).start()
    except Exception:
        pass

    return JsonResponse({"status": "ok", "service": "ABCD Smart Campus", "uptime": "active"})

urlpatterns = [
    # Root PWA Service Worker (with Service-Worker-Allowed: /)
    path('sw.js', service_worker_view, name='service_worker'),

    # VAPID Public Key API endpoint
    path('api/vapid-public-key/', vapid_public_key_api, name='vapid_public_key_api'),

    # 24/7 Keep-Alive & Health Check Endpoints (Lightweight ~30 bytes)
    path('ping/', ping_view, name='ping'),
    path('healthz/', ping_view, name='healthz'),

    # 24/7 Dedicated External Cron Maintenance Webhook (cron-job.org / Admin)
    path('api/cron/maintenance/', cron_maintenance_view, name='cron_maintenance'),

    path('admin/', admin.site.urls),

    # Browser default favicon & SEO
    path('favicon.ico', RedirectView.as_view(url='/static/data/favicon/favicon.ico', permanent=True)),
    path('robots.txt', robots_txt_view, name='robots_txt'),
    path('sitemap.xml', sitemap_xml_view, name='sitemap_xml'),

    # Media files serving (works in both DEBUG and Production)
    re_path(r'^media/(?P<path>.*)$', serve, {'document_root': settings.MEDIA_ROOT}),

    # All your app's URLs, including the home page, are now handled here
    path('', include('users.urls')),
    path('auth/', include('social_django.urls', namespace='social')),
]