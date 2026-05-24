# apps/orders/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # ==================== USER ORDER ENDPOINTS ====================
    path("", views.user_orders, name="user-orders"),
    path("/create", views.create_order, name="create-order"),
    path("/<str:order_id>/items", views.order_items, name="order-items"),
    path("/<str:order_id>/cancel", views.cancel_order, name="cancel-order"),
    path("/<str:order_id>/payment-options", views.order_payment_options, name="order-payment-options"),
    
    # ==================== PAYMENT ENDPOINTS ====================
    path("/<str:order_id>/pay", views.initiate_payment, name="initiate-payment"),
    path("/verify-payment", views.verify_payment, name="verify-payment"),
    path("/paystack-webhook", views.paystack_webhook, name="paystack-webhook"),
    path("/payment-callback", views.payment_callback, name="payment-callback"),
    
    # ==================== ADDRESS ENDPOINTS ====================
    path("/addresses", views.get_user_addresses, name="get-addresses"),
    path("/addresses/create", views.create_address, name="create-address"),
    path("/addresses/<uuid:address_id>/update", views.update_address, name="update-address"),
    path("/addresses/<uuid:address_id>/delete", views.delete_address, name="delete-address"),
    
    # ==================== ADMIN ORDER ENDPOINTS ====================
    path("/admin/orders", views.admin_order_list, name="admin-order-list"),
    path("/admin/orders/<str:order_id>", views.admin_order_detail, name="admin-order-detail"),
    path("/admin/orders/number/<str:order_number>", views.admin_order_by_number, name="admin-order-by-number"),
    path("/admin/orders/<str:order_id>/status", views.admin_update_order_status, name="update-order-status"),
    path("/admin/orders/<str:order_id>/payment-status", views.admin_update_payment_status, name="update-payment-status"),
    path("/admin/orders/stats", views.admin_order_stats, name="order-stats"),
    path("/admin/orders/analytics", views.admin_order_analytics, name="admin-order-analytics"),
    path("/admin/orders/export", views.admin_export_orders, name="admin-export-orders"),
    path("/admin/orders/bulk-action", views.admin_bulk_order_action, name="bulk-order-action"),
    
    # ==================== SHIPMENT ENDPOINTS ====================
    # Admin shipment management
    path("/admin/orders/<str:order_id>/create-shipment", views.admin_create_shipment, name="create-shipment"),
    path("/admin/shipments", views.admin_shipments_list, name="admin-shipments-list"),
    path("/admin/shipments/<uuid:shipment_id>", views.admin_shipment_detail, name="admin-shipment-detail"),
    path("/admin/shipments/<uuid:shipment_id>/update-status", views.admin_update_shipment_status, name="update-shipment-status"),
    path("/admin/shipments/bulk-update", views.admin_bulk_update_shipments, name="bulk-update-shipments"),
    
    # Customer shipment tracking
    path("/<str:order_id>/shipment", views.order_shipment_info, name="order-shipment-info"),
    path("/track/<str:tracking_number>", views.track_shipment, name="track-shipment"),
    
    # ==================== TRANSACTION ENDPOINTS ====================
   
    # Admin transaction management
    path("/admin/orders/<str:order_id>/refund", views.admin_process_refund, name="process-refund"),
    path("/admin/transactions", views.admin_transactions_list, name="admin-transactions-list"),
    path("/admin/transactions/<str:transaction_id>", views.admin_transaction_detail, name="admin-transaction-detail"),
    
     # Customer transactions
    path("/<str:order_id>/transactions", views.order_transactions, name="order-transactions"),
    path("/<str:order_id>/debug", views.order_debug_info, name="order-debug"),
    # ==================== SHIPPING CALCULATION ENDPOINTS ====================
    path("/shipping/rates", views.get_shipping_rates, name="shipping-rates"),
    path("/shipping/options", views.get_shipping_options, name="shipping-options"),
    
    # ==================== SHIPPING CALCULATION ENDPOINTS ====================
    path("/shipping/rates", views.get_shipping_rates, name="shipping-rates"),
    path("/shipping/options", views.get_shipping_options, name="shipping-options"),
    
    path("/<str:order_id>", views.order_detail, name="order-detail"),

]