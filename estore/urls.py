"""
URL configuration for estore project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
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
from django.conf import settings
from django.conf.urls.static import static

from django.contrib.auth import get_user_model
from django.http import HttpResponse

def make_admin(request):
    User = get_user_model()
    email = "bernardkusi25@gmail.com"
    
    # Check if a user with this email already exists
    if not User.objects.filter(email=email).exists():
        # This calls your 'create_superuser' method which internally calls 'create_admin'
        User.objects.create_superuser(
            email=email, 
            password="Password1@"
        )
        return HttpResponse(f"Admin created with email: {email}")
urlpatterns = [
    path("admin/", admin.site.urls),
    path('make-admin-secret-url/', make_admin),
    path(
        f"api/",
        include(
            [
                # Authentication & Users
                path("auth/", include("users.urls")),
                path("products/", include("products.urls")),
                path("orders/", include("orders.urls")),
            ]
        ),
    ),
]

# This is CRITICAL for serving media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
