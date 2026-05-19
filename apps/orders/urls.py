# apps/orders/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # ==================== USER ORDER ENDPOINTS ====================
    path("", views.user_orders, name="user-orders"),
    path("create/", views.create_order, name="create-order"),
    path("<str:order_id>/items/", views.order_items, name="order-items"),  # Optional
    path("<str:order_id>/cancel/", views.cancel_order, name="cancel-order"),
    path("<str:order_id>/payment-options/", views.order_payment_options, name="order-payment-options"),
    
    # ==================== PAYMENT ENDPOINTS ====================
    path("payment/callback/", views.payment_callback, name="payment-callback"), 
    path("<str:order_id>/pay/", views.initiate_payment, name="initiate-payment"),
    path("verify-payment/", views.verify_payment, name="verify-payment"),
    path("paystack-webhook/", views.paystack_webhook, name="paystack-webhook"),
    path("<str:order_id>/", views.order_detail, name="order-detail"),
    
    path("<str:order_id>/", views.order_detail, name="order-detail"),
    
    
    # ==================== ADDRESS ENDPOINTS ====================
    path("addresses/", views.get_user_addresses, name="get-addresses"),
    path("addresses/create/", views.create_address, name="create-address"),
    path("addresses/<uuid:address_id>/update/", views.update_address, name="update-address"),
    path("addresses/<uuid:address_id>/delete/", views.delete_address, name="delete-address"),
    
    # ==================== ADMIN ORDER ENDPOINTS ====================
    path("admin/orders/", views.admin_order_list, name="admin-order-list"),
    path("admin/orders/number/<str:order_number>/", views.admin_order_by_number, name="admin-order-by-number"),  # Optional
    path("admin/orders/<str:order_id>/status/", views.admin_update_order_status, name="update-order-status"),
    path("admin/orders/<str:order_id>/payment-status/", views.admin_update_payment_status, name="update-payment-status"),
    path("admin/orders/stats/", views.admin_order_stats, name="order-stats"),
    path("admin/orders/analytics/", views.admin_order_analytics, name="admin-order-analytics"),  # Optional
    path("admin/orders/export/", views.admin_export_orders, name="admin-export-orders"),  # Optional
    path("admin/orders/bulk-action/", views.admin_bulk_order_action, name="bulk-order-action"),
    path("admin/orders/<str:order_id>/", views.admin_order_detail, name="admin-order-detail"),
    
]