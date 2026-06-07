# apps/orders/urls.py

from django.urls import path
from . import views
from apps.orders.views.analytics_views import (
    order_analytics_summary,
    sales_trends_analytics,
    order_status_distribution_analytics,
    payment_status_distribution_analytics,
    top_customers_analytics,
    fulfillment_analytics,
    refund_analytics,
    customer_retention_analytics,
    hourly_order_distribution_analytics,
    day_of_week_distribution_analytics,
)


urlpatterns = [
    
     path(
        "/admin/orders/analytics/summary",
        order_analytics_summary,
        name="order-analytics-summary",
    ),
    path(
        "/admin/orders/analytics/sales-trends",
        sales_trends_analytics,
        name="order-analytics-sales-trends",
    ),
    path(
        "/admin/orders/analytics/status-distribution",
        order_status_distribution_analytics,
        name="order-analytics-status-distribution",
    ),
    path(
        "/admin/orders/analytics/payment-status-distribution",
        payment_status_distribution_analytics,
        name="order-analytics-payment-status-distribution",
    ),
    path(
        "/admin/orders/analytics/top-customers",
        top_customers_analytics,
        name="order-analytics-top-customers",
    ),
    path(
        "/admin/orders/analytics/fulfillment",
        fulfillment_analytics,
        name="order-analytics-fulfillment",
    ),
    path(
        "/admin/orders/analytics/refunds",
        refund_analytics,
        name="order-analytics-refunds",
    ),
    path(
        "/admin/orders/analytics/customer-retention",
        customer_retention_analytics,
        name="order-analytics-customer-retention",
    ),
    path(
        "/admin/orders/analytics/hourly-distribution",
        hourly_order_distribution_analytics,
        name="order-analytics-hourly-distribution",
    ),
    path(
        "/admin/orders/analytics/day-of-week-distribution",
        day_of_week_distribution_analytics,
        name="order-analytics-day-of-week-distribution",
    ),
    
    # ==================== USER ORDER ENDPOINTS ====================
    path("", views.user_orders, name="user-orders"),
    path("/create", views.create_order, name="create-order"),
    path("/<str:order_id>/items", views.order_items, name="order-items"),
    path("/<str:order_id>/cancel", views.cancel_order, name="cancel-order"),
    path(
        "/<str:order_id>/payment-options",
        views.order_payment_options,
        name="order-payment-options",
    ),
    # ==================== PAYMENT ENDPOINTS ====================
    path("/<str:order_id>/pay", views.initiate_payment, name="initiate-payment"),
    path("/verify-payment", views.verify_payment, name="verify-payment"),
    path("/paystack-webhook", views.paystack_webhook, name="paystack-webhook"),
    path("/payment-callback", views.payment_callback, name="payment-callback"),
    # ==================== ADDRESS ENDPOINTS ====================
    path("/addresses", views.get_user_addresses, name="get-addresses"),
    path("/addresses/create", views.create_address, name="create-address"),
    path(
        "/addresses/<uuid:address_id>/update",
        views.update_address,
        name="update-address",
    ),
    path(
        "/addresses/<uuid:address_id>/delete",
        views.delete_address,
        name="delete-address",
    ),
    # ==================== ADMIN ORDER ENDPOINTS ====================
    path("/admin/orders", views.admin_order_list, name="admin-order-list"),
    path(
        "/admin/orders/<str:order_id>",
        views.admin_order_detail,
        name="admin-order-detail",
    ),
    path(
        "/admin/orders/number/<str:order_number>",
        views.admin_order_by_number,
        name="admin-order-by-number",
    ),
    path(
        "/admin/orders/<str:order_id>/status",
        views.admin_update_order_status,
        name="update-order-status",
    ),
    path(
        "/admin/orders/<str:order_id>/payment-status",
        views.admin_update_payment_status,
        name="update-payment-status",
    ),
    path("/admin/orders/stats", views.admin_order_stats, name="order-stats"),
    path(
        "/admin/orders/analytics",
        views.admin_order_analytics,
        name="admin-order-analytics",
    ),
    path("/admin/orders/export", views.admin_export_orders, name="admin-export-orders"),
    path(
        "/admin/orders/bulk-action",
        views.admin_bulk_order_action,
        name="bulk-order-action",
    ),
    # ==================== SHIPMENT ENDPOINTS ====================
    # Admin shipment management
    path(
        "/admin/orders/<str:order_id>/create-shipment",
        views.admin_create_shipment,
        name="create-shipment",
    ),
    path("/admin/shipments", views.admin_shipments_list, name="admin-shipments-list"),
    path(
        "/admin/shipments/<uuid:shipment_id>",
        views.admin_shipment_detail,
        name="admin-shipment-detail",
    ),
    path(
        "/admin/shipments/<uuid:shipment_id>/update-status",
        views.admin_update_shipment_status,
        name="update-shipment-status",
    ),
    path(
        "/admin/shipments/bulk-update",
        views.admin_bulk_update_shipments,
        name="bulk-update-shipments",
    ),
    # Customer shipment tracking
    path(
        "/<str:order_id>/shipment",
        views.order_shipment_info,
        name="order-shipment-info",
    ),
    path("/track/<str:tracking_number>", views.track_shipment, name="track-shipment"),
    # ==================== TRANSACTION ENDPOINTS ====================
    # Admin transaction management
    path(
        "/admin/orders/<str:order_id>/refund",
        views.admin_process_refund,
        name="process-refund",
    ),
    path(
        "/admin/transactions",
        views.admin_transactions_list,
        name="admin-transactions-list",
    ),
    path(
        "/admin/transactions/<str:transaction_id>",
        views.admin_transaction_detail,
        name="admin-transaction-detail",
    ),
    # Customer transactions
    path(
        "/<str:order_id>/transactions",
        views.order_transactions,
        name="order-transactions",
    ),
    path("/<str:order_id>/debug", views.order_debug_info, name="order-debug"),
    # ==================== SHIPPING CALCULATION ENDPOINTS ====================
    path("/shipping/rates", views.get_shipping_rates, name="shipping-rates"),
    path("/shipping/options", views.get_shipping_options, name="shipping-options"),
    # ==================== SHIPPING CALCULATION ENDPOINTS ====================
    path("/shipping/rates", views.get_shipping_rates, name="shipping-rates"),
    path("/shipping/options", views.get_shipping_options, name="shipping-options"),
    path("/<str:order_id>", views.order_detail, name="order-detail"),
    
    
    # ==================== POS (Point of Sale) ENDPOINTS ====================
    path("/admin/pos/orders/create", views.pos_create_order, name="pos-create-order"),
    path("/admin/pos/customers/search", views.pos_search_customers, name="pos-search-customers"),
    path("/admin/pos/promotions", views.pos_get_active_promotions, name="pos-get-promotions"),
    path("/admin/pos/customers/<uuid:customer_id>/addresses", views.pos_get_customer_addresses, name="pos-customer-addresses"),
    path("/admin/pos/customers/<uuid:customer_id>/addresses/create", views.pos_create_customer_address, name="pos-create-customer-address"),
    path("/admin/pos/customers/<uuid:customer_id>/addresses/<uuid:address_id>/update", views.pos_update_customer_address, name="pos-update-customer-address"),
    path("/admin/pos/customers/<uuid:customer_id>/addresses/<uuid:address_id>/delete", views.pos_delete_customer_address, name="pos-delete-customer-address"),
    
    # POS Shipping Calculation
    path("/admin/pos/shipping/calculate", views.pos_calculate_shipping_for_address, name="pos-calculate-shipping"),
]
