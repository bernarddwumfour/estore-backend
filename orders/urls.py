# orders/urls.py
from django.urls import path
from . import views

urlpatterns = [
    # User order management
    path("", views.user_orders, name="user-orders"),
    path("create/", views.create_order, name="create-order"),
    path("<str:order_id>/", views.order_detail, name="order-detail"),
    path("<str:order_id>/cancel/", views.cancel_order, name="cancel-order"),
    # Address management
    path("addresses/", views.get_user_addresses, name="get-addresses"),
    path("addresses/create/", views.create_address, name="create-address"),
    path(
        "addresses/<uuid:address_id>/update/",
        views.update_address,
        name="update-address",
    ),
    path(
        "addresses/<uuid:address_id>/delete/",
        views.delete_address,
        name="delete-address",
    ),
    # Admin order management
    path("admin/orders/", views.admin_order_list, name="admin-order-list"),
    path(
        "admin/orders/<str:order_id>/status/",
        views.update_order_status,
        name="update-order-status",
    ),
    path(
        "admin/orders/<str:order_id>/payment-status/",
        views.update_payment_status,
        name="update-payment-status",
    ),
    path("admin/orders/stats/", views.order_stats, name="order-stats"),
    # Payment verification
    path("verify-payment/", views.verify_payment, name="verify-payment"),
]
