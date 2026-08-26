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
from django.urls import path, include
from django.views.generic import RedirectView
from users.views import robots_txt_view, sitemap_xml_view

urlpatterns = [
    path('admin/', admin.site.urls),

    # Browser default favicon & SEO
    path('favicon.ico', RedirectView.as_view(url='/static/data/favicon/favicon.ico', permanent=True)),
    path('robots.txt', robots_txt_view, name='robots_txt'),
    path('sitemap.xml', sitemap_xml_view, name='sitemap_xml'),

    # All your app's URLs, including the home page, are now handled here
    path('', include('users.urls')),
    path('auth/', include('social_django.urls', namespace='social')),
]