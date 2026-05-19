"""
products/urls.py - Updated with admin endpoints
"""

from django.urls import path
from . import views

app_name = "products"

urlpatterns = [
    # ==================== PUBLIC ENDPOINTS ====================
    path("", views.product_list, name="product-list"),
    path("variants/<uuid:variant_id>/", views.variant_detail, name="variant-detail"),
    path("categories/", views.category_list, name="category-list"),
    path("search/", views.product_search, name="product-search"),
    path("categories/<slug:slug>/", views.category_detail, name="category-detail"),
    # ==================== AUTHENTICATED USER ENDPOINTS ====================
    path("wishlist/", views.wishlist_list, name="wishlist-list"),
    path("wishlist/<uuid:variant_id>/", views.wishlist_remove, name="wishlist-remove"),
    path("<slug:slug>/reviews/create/", views.create_review, name="create-review"),
    path("<slug:slug>/", views.product_detail, name="product-detail"),
    path("<slug:slug>/reviews/", views.product_reviews, name="product-reviews"),
    
    # ==================== ADMIN ENDPOINTS ====================
    path("admin/products/", views.admin_product_list, name="admin-product-list"),
    path(
        "admin/products/create/",
        views.admin_product_create,
        name="admin-product-create",
    ),
    path(
        "admin/products/<uuid:product_id>/",
        views.admin_product_detail,
        name="admin-product-detail",
    ),
    path(
        "admin/products/<uuid:product_id>/update/",
        views.admin_product_update,
        name="admin-product-update",
    ),
    path(
        "admin/products/bulk-action/",
        views.admin_product_bulk_action,
        name="admin-product-bulk-action",
    ),
    path(
        "admin/products/<uuid:product_id>/variants/",
        views.admin_variant_create,
        name="admin-variant-create",
    ),
    path(
        "admin/variants/<uuid:variant_id>/update/",
        views.admin_variant_update,
        name="admin-variant-update",
    ),
    path(
        "admin/variants/<uuid:variant_id>/images/",
        views.admin_variant_image_upload,
        name="admin-variant-image-upload",
    ),
    path(
        "admin/variants/<uuid:variant_id>/",
        views.admin_variant_detail,
        name="admin-variant-detail",
    ),
    path(
        "admin/variants/<uuid:variant_id>/delete/",
        views.admin_variant_delete,
        name="admin-variant-delete",
    ),
    path("admin/categories/", views.admin_category_list, name="admin-category-list"),
    path(
        "admin/categories/create/",
        views.admin_category_create,
        name="admin-category-create",
    ),
    path(
        "admin/categories/<uuid:category_id>/update/",
        views.admin_category_update,
        name="admin-category-update",
    ),
    path(
        "admin/categories/<uuid:category_id>/",
        views.admin_category_detail,
        name="admin-category-details",
    ),
    path(
        "admin/categories/<uuid:category_id>/delete/",
        views.admin_category_delete,
        name="admin-category-delete",
    ),
    path(
        "admin/analytics/",
        views.product_analytics,
        name="admin-product-analytics",
    ),
    path(
        "admin/categories/bulk-action/",
        views.admin_category_bulk_action,
        name="admin-category-bulk-action",
    ),
]
