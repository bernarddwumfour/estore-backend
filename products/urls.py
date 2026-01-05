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
    path("<slug:slug>/", views.product_detail, name="product-detail"),
    path("<slug:slug>/reviews/", views.product_reviews, name="product-reviews"),
    # ==================== AUTHENTICATED USER ENDPOINTS ====================
    path("wishlist/", views.wishlist_list, name="wishlist-list"),
    path("wishlist/<uuid:variant_id>/", views.wishlist_remove, name="wishlist-remove"),
    path("<slug:slug>/reviews/create/", views.create_review, name="create-review"),
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
    path("admin/categories/", views.admin_category_list, name="admin-category-list"),
    path(
        "admin/categories/create/",
        views.admin_category_create,
        name="admin-category-create",
    ),
    path(
        "admin/categories/<uuid:category_id>/",
        views.admin_category_update_delete,
        name="dmin-category-update-delete",
    ),
]
