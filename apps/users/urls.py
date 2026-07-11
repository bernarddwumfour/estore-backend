# apps/users/urls.py

from django.urls import path
from . import views
from apps.users.views.analytics_views import (
    user_analytics_overview,
    user_growth_trends,
    user_engagement_analytics,
    user_geographic_distribution,
    user_activity_analytics,
    affiliate_analytics,
    affiliate_growth_trends,
    customer_demographics,
    top_customers_analytics,
)


urlpatterns = [
     # User Analytics Endpoints
    path(
        "/admin/users/analytics/overview",
        user_analytics_overview,
        name="user-analytics-overview",
    ),
    path(
        "/admin/users/analytics/growth-trends",
        user_growth_trends,
        name="user-analytics-growth-trends",
    ),
    path(
        "/admin/users/analytics/engagement",
        user_engagement_analytics,
        name="user-analytics-engagement",
    ),
    path(
        "/admin/users/analytics/geographic",
        user_geographic_distribution,
        name="user-analytics-geographic",
    ),
    path(
        "/admin/users/analytics/activity",
        user_activity_analytics,
        name="user-analytics-activity",
    ),
    path(
        "/admin/users/analytics/affiliates",
        affiliate_analytics,
        name="user-analytics-affiliates",
    ),
    path(
        "/admin/users/analytics/affiliate-growth",
        affiliate_growth_trends,
        name="user-analytics-affiliate-growth",
    ),
    path(
        "/admin/users/analytics/customer-demographics",
        customer_demographics,
        name="user-analytics-customer-demographics",
    ),
    path(
        "/admin/users/analytics/top-customers",
        top_customers_analytics,
        name="user-analytics-top-customers",
    ),
    # ==================== AUTHENTICATION ====================
    path("/register/customer", views.register_customer, name="register-customer"),
    path("/register/user", views.register_user, name="register-user"),
    path("/login", views.login, name="login"),
    path("/logout", views.logout, name="logout"),
    path("/refresh-token", views.refresh_token, name="refresh-token"),
    
    # ==================== PASSWORD RESET ====================
    path("/password-reset/request", views.password_reset_request, name="password-reset-request"),
    path("/password-reset/validate", views.password_reset_validate, name="password-reset-validate"),
    path("/password-reset/confirm", views.password_reset_confirm, name="password-reset-confirm"),
    
    # ==================== EMAIL VERIFICATION ====================
    path("/verify-email/<str:token>", views.verify_email, name="verify-email"),
    path("/validate-verification-token", views.validate_verification_token, name="validate-verification-token"),
    path("/resend-verification", views.resend_verification, name="resend-verification"),
    path("/request-verification", views.request_verification, name="request-verification"),
    path("/check-verification", views.check_verification_status, name="check-verification"),
    
    # ==================== PROFILE MANAGEMENT ====================
    path("/profile", views.get_profile, name="get-profile"),
    path("/profile/update", views.update_profile, name="update-profile"),
    path("/profile/change-password", views.change_password, name="change-password"),
    
    # ==================== USER MANAGEMENT (ADMIN) ====================
    # All Users
    path("/admin/users", views.list_all_users, name="list-all-users"),
    path("/admin/users/statistics", views.user_statistics, name="user-statistics"),
    path("/admin/users/bulk-action", views.bulk_user_action, name="bulk-user-action"),
    path("/admin/users/<uuid:user_id>", views.user_detail, name="user-detail"),
    path("/admin/users/<uuid:user_id>/verification", views.admin_check_verification, name="admin-check-verification"),
    
    # Customers
    path("/admin/customers", views.list_customers, name="list-customers"),
    
    # Staff Management
    path("/admin/staff", views.list_staff_users, name="list-staff-users"),
    path("/admin/staff/create", views.create_staff_user, name="create-staff-user"),
    path("/admin/staff/bulk-action", views.bulk_staff_action, name="bulk-staff-action"),
    path("/admin/staff/<uuid:user_id>/delete", views.delete_staff_user, name="delete-staff-user"),
    
    # Guest Users
    path("/admin/guests", views.list_guest_users, name="list-guest-users"),
    
    # Affiliate Management
    path("/admin/affiliates", views.list_affiliate_users, name="list-affiliate-users"),
    path("/admin/affiliates/<uuid:user_id>/make", views.make_affiliate, name="make-affiliate"),
    path("/admin/affiliates/make-by-email", views.make_affiliate_by_email, name="make-affiliate-by-email"),
    path("/admin/affiliates/<uuid:user_id>/remove", views.remove_affiliate, name="remove-affiliate"),
    path("/admin/affiliates/<uuid:user_id>/status", views.toggle_affiliate_status, name="toggle-affiliate-status"),
    path("/admin/affiliates/<uuid:user_id>/commission", views.update_affiliate_commission, name="update-affiliate-commission"),
    
    # ==================== GUEST CHECKOUT ====================
    path("/guest-checkout", views.guest_checkout, name="guest-checkout"),
    path("/guest-convert", views.guest_convert, name="guest-convert"),
    
    # ==================== AFFILIATE PROFILE ====================
    path("/affiliate/profile", views.get_affiliate_profile, name="affiliate-profile"),
    
    # ==================== TODO: ADDRESS MANAGEMENT ====================
    # path('/addresses', views.get_addresses, name='get-addresses'),
    # path('/addresses/create', views.create_address, name='create-address'),
    # path('/addresses/<uuid:address_id>/update', views.update_address, name='update-address'),
    # path('/addresses/<uuid:address_id>/delete', views.delete_address, name='delete-address'),
]
