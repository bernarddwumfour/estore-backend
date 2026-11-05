
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path("admin/", admin.site.urls),

    path(
        "api/",
        include(
            [
                # Authentication & Users
                path("users", include("apps.users.urls")),
                path("products", include("apps.products.urls")),
                path("promotions", include("apps.promotions.urls")),
                path("orders", include("apps.orders.urls")),
                path("common", include("apps.common.urls")),
                path("marketing", include("apps.marketing.urls")),
                path("social", include("apps.social.urls")),
                path("blog", include("apps.blog.urls")),

                # AI Shopping Assistant
                path(
                    "assistant/",
                    include("apps.ai_assistant.urls"),
                ),
            ]
        ),
    ),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
