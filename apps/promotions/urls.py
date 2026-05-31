"""
Promotions URLs
"""

from django.urls import path
from apps.promotions.views import (
    promotion_list,
    promotion_detail,
    admin_promotion_list,
    admin_promotion_create,
    admin_promotion_activate,
    admin_promotion_pause,
    admin_promotion_refresh_stock,
    admin_promotion_bulk_action,
    admin_promotion_update,
    admin_promotion_detail
)

app_name = "promotions"

urlpatterns = [
    # Public endpoints
    path("", promotion_list, name="promotion-list"),
    path("/<slug:slug>", promotion_detail, name="promotion-detail"),
    
    # Admin endpoints
    path("/admin/promotions", admin_promotion_list, name="admin-promotion-list"),
    path("/admin/promotions/create", admin_promotion_create, name="admin-promotion-create"),
    path("/admin/promotions/<uuid:promotion_id>", admin_promotion_detail, name="admin-promotion-detail"),
    path("/admin/promotions/<uuid:promotion_id>/activate", admin_promotion_activate, name="admin-promotion-activate"),
    path("/admin/promotions/<uuid:promotion_id>/pause", admin_promotion_pause, name="admin-promotion-pause"),
    path("/admin/promotions/<uuid:promotion_id>/refresh-stock", admin_promotion_refresh_stock, name="admin-promotion-refresh-stock"),
    path("/admin/promotions/bulk-action", admin_promotion_bulk_action, name="admin-promotion-bulk-action"),
    path("/admin/promotions/<uuid:promotion_id>/update", admin_promotion_update, name="admin-promotion-update"),
]