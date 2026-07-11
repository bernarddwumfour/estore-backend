"""
Promotions URLs
"""

from django.urls import path
from apps.promotions.views import (
    promotion_list,
    promotion_detail,
    preview_discount_code,
    affiliate_dashboard,
    admin_discount_code_list,
    admin_discount_code_create,
    admin_discount_code_detail,
    admin_discount_code_update,
    admin_discount_code_toggle_status,
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
    path("/discount-codes/preview", preview_discount_code, name="discount-code-preview"),
    path("/affiliate/dashboard", affiliate_dashboard, name="affiliate-dashboard"),
    path("/<slug:slug>", promotion_detail, name="promotion-detail"),
    
    # Admin endpoints
    path("/admin/discount-codes", admin_discount_code_list, name="admin-discount-code-list"),
    path("/admin/discount-codes/create", admin_discount_code_create, name="admin-discount-code-create"),
    path("/admin/discount-codes/<uuid:code_id>", admin_discount_code_detail, name="admin-discount-code-detail"),
    path("/admin/discount-codes/<uuid:code_id>/update", admin_discount_code_update, name="admin-discount-code-update"),
    path("/admin/discount-codes/<uuid:code_id>/status", admin_discount_code_toggle_status, name="admin-discount-code-toggle-status"),
    path("/admin/promotions", admin_promotion_list, name="admin-promotion-list"),
    path("/admin/promotions/create", admin_promotion_create, name="admin-promotion-create"),
    path("/admin/promotions/<uuid:promotion_id>", admin_promotion_detail, name="admin-promotion-detail"),
    path("/admin/promotions/<uuid:promotion_id>/activate", admin_promotion_activate, name="admin-promotion-activate"),
    path("/admin/promotions/<uuid:promotion_id>/pause", admin_promotion_pause, name="admin-promotion-pause"),
    path("/admin/promotions/<uuid:promotion_id>/refresh-stock", admin_promotion_refresh_stock, name="admin-promotion-refresh-stock"),
    path("/admin/promotions/bulk-action", admin_promotion_bulk_action, name="admin-promotion-bulk-action"),
    path("/admin/promotions/<uuid:promotion_id>/update", admin_promotion_update, name="admin-promotion-update"),
]
