"""
products/urls.py - Updated with review endpoints (product and order reviews)
"""

from django.urls import path
from apps.products.views.analytics_views import (
    product_analytics_overview,
    top_products_analytics,
    category_performance_analytics,
    variant_analytics,
    inventory_status_analytics,
    price_distribution_analytics,
    review_analytics,
    category_analytics,
    sales_performance_analytics,
    product_funnel_analytics,
    inventory_health_analytics,
    pricing_analytics
)

from apps.products.views.product_views import (
    product_detail,
    product_list,
    admin_product_bulk_action,
    admin_product_create,
    admin_product_detail,
    admin_product_list,
    admin_product_update,
    product_search,
)
from apps.products.views.category_views import (
    category_list,
    category_detail,
    admin_category_bulk_action,
    admin_category_create,
    admin_category_delete,
    admin_category_detail,
    admin_category_list,
    admin_category_update,
)
from apps.products.views.variant_views import (
    admin_variant_bulk_action,
    admin_variant_create,
    admin_variant_delete,
    admin_variant_detail,
    admin_variant_image_upload,
    admin_variant_list,
    admin_variant_update,
    wishlist_list,
    wishlist_remove,
    variant_detail,
)

# Import new review views
from apps.products.views.review_views import (
    # Public endpoints
    product_reviews_list,
    product_review_create,
    product_review_helpful,
    order_review_create,
    order_review_detail,
    order_review_helpful,
    user_reviews,
    # Admin endpoints
    admin_reviews_list,
    admin_review_approve,
    admin_review_reject,
    admin_reviews_bulk_action,
    admin_order_review_response,
)

app_name = "products"

urlpatterns = [
    # ==================== ANALYTICS ENDPOINTS ====================
    path(
        "/admin/products/analytics/overview",
        product_analytics_overview,
        name="product-analytics-overview",
    ),
    path(
        "/admin/products/analytics/sales-performance",
        sales_performance_analytics,
        name="product-analytics-sales-performance",
    ),
    path(
        "/admin/products/analytics/product-funnel",
        product_funnel_analytics,
        name="product-analytics-product-funnel",
    ),
    path(
        "/admin/products/analytics/inventory-health",
        inventory_health_analytics,
        name="product-analytics-inventory-health",
    ),
    path(
        "/admin/products/analytics/pricing",
        pricing_analytics,
        name="product-analytics-pricing",
    ),
    path(
        "/admin/products/analytics/categories",
        category_analytics,
        name="product-analytics-categories",
    ),
    path(
        "/admin/products/analytics/top-products",
        top_products_analytics,
        name="product-analytics-top-products",
    ),
    path(
        "/admin/products/analytics/category-performance",
        category_performance_analytics,
        name="product-analytics-category-performance",
    ),
    path(
        "/admin/products/analytics/variants",
        variant_analytics,
        name="product-analytics-variants",
    ),
    path(
        "/admin/products/analytics/inventory",
        inventory_status_analytics,
        name="product-analytics-inventory",
    ),
    path(
        "/admin/products/analytics/price-distribution",
        price_distribution_analytics,
        name="product-analytics-price-distribution",
    ),
    path(
        "/admin/products/analytics/reviews",
        review_analytics,
        name="product-analytics-reviews",
    ),
    
    # ==================== PUBLIC PRODUCT REVIEW ENDPOINTS ====================
    
    path(
        "/<slug:slug>/reviews/create",
        product_review_create,
        name="product-review-create",
    ),
    path(
        "/reviews/product/<uuid:review_id>/helpful",
        product_review_helpful,
        name="product-review-helpful",
    ),
    
    # ==================== PUBLIC ORDER REVIEW ENDPOINTS ====================
    path(
        "/orders/<uuid:order_id>/reviews/create",
        order_review_create,
        name="order-review-create",
    ),
    path(
        "/orders/reviews/<uuid:review_id>",
        order_review_detail,
        name="order-review-detail",
    ),
    path(
        "/orders/reviews/<uuid:review_id>/helpful",
        order_review_helpful,
        name="order-review-helpful",
    ),
    
    # ==================== USER REVIEWS ENDPOINT ====================
    path(
        "/user/reviews",
        user_reviews,
        name="user-reviews",
    ),
    
    # ==================== PUBLIC ENDPOINTS ====================
    path("", product_list, name="product-list"),
    path("/variants/<uuid:variant_id>", variant_detail, name="variant-detail"),
    path("/categories", category_list, name="category-list"),
    path("/search", product_search, name="product-search"),
    path("/categories/<slug:slug>", category_detail, name="category-detail"),
    
    # ==================== AUTHENTICATED USER ENDPOINTS ====================
    path("/wishlist", wishlist_list, name="wishlist-list"),
    path("/wishlist/<uuid:variant_id>", wishlist_remove, name="wishlist-remove"),
    path("/<slug:slug>", product_detail, name="product-detail"),
    
    # ==================== ADMIN REVIEW ENDPOINTS ====================
   path(
    "/admin/reviews",
    admin_reviews_list,
    name="admin-reviews-list",
),
    path(
        "/admin/reviews/<uuid:review_id>/approve",
        admin_review_approve,
        name="admin-review-approve",
    ),
    path(
        "/admin/reviews/<uuid:review_id>/reject",
        admin_review_reject,
        name="admin-review-reject",
    ),
    path(
        "/admin/reviews/bulk-action",
        admin_reviews_bulk_action,
        name="admin-reviews-bulk-action",
    ),
    path(
        "/admin/reviews/order/<uuid:review_id>/response",
        admin_order_review_response,
        name="admin-order-review-response",
    ),
    
    path(
        "/<slug:slug>/reviews",
        product_reviews_list,
        name="product-reviews-list",
    ),
    
    # ==================== ADMIN PRODUCT ENDPOINTS ====================
    path("/admin/products", admin_product_list, name="admin-product-list"),
    path(
        "/admin/products/create",
        admin_product_create,
        name="admin-product-create",
    ),
    path(
        "/admin/products/<uuid:product_id>",
        admin_product_detail,
        name="admin-product-detail",
    ),
    path(
        "/admin/products/<uuid:product_id>/update",
        admin_product_update,
        name="admin-product-update",
    ),
    path(
        "/admin/products/bulk-action",
        admin_product_bulk_action,
        name="admin-product-bulk-action",
    ),
    
    # ==================== ADMIN VARIANT ENDPOINTS ====================
    path("/admin/variants", admin_variant_list, name="admin-variant-list"),
    path(
        "/admin/products/<uuid:product_id>/variants",
        admin_variant_create,
        name="admin-variant-create",
    ),
    path(
        "/admin/variants/<uuid:variant_id>/update",
        admin_variant_update,
        name="admin-variant-update",
    ),
    path(
        "/admin/variants/<uuid:variant_id>/images",
        admin_variant_image_upload,
        name="admin-variant-image-upload",
    ),
    path(
        "/admin/variants/<uuid:variant_id>",
        admin_variant_detail,
        name="admin-variant-detail",
    ),
    path(
        "/admin/variants/<uuid:variant_id>/delete",
        admin_variant_delete,
        name="admin-variant-delete",
    ),
    path(
        "/admin/variants/bulk-action",
        admin_variant_bulk_action,
        name="admin-variant-bulk-action",
    ),
    
    # ==================== ADMIN CATEGORY ENDPOINTS ====================
    path("/admin/categories", admin_category_list, name="admin-category-list"),
    path(
        "/admin/categories/create",
        admin_category_create,
        name="admin-category-create",
    ),
    path(
        "/admin/categories/<uuid:category_id>/update",
        admin_category_update,
        name="admin-category-update",
    ),
    path(
        "/admin/categories/<uuid:category_id>",
        admin_category_detail,
        name="admin-category-details",
    ),
    path(
        "/admin/categories/<uuid:category_id>/delete",
        admin_category_delete,
        name="admin-category-delete",
    ),
    path(
        "/admin/categories/bulk-action",
        admin_category_bulk_action,
        name="admin-category-bulk-action",
    ),
]