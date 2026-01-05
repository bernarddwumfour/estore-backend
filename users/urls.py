from django.urls import path
from . import views

urlpatterns = [
    # ==================== AUTHENTICATION ====================
    path("register/customer/", views.register_customer, name="register-customer"),
    path("register/user/", views.register_user, name="register-user"),
    path("login/", views.login, name="login"),
    path("logout/", views.logout, name="logout"),
    path("refresh-token/", views.refresh_token, name="refresh-token"),
    # ==================== PASSWORD RESET ====================
    path(
        "password-reset/request/",
        views.password_reset_request,
        name="password-reset-request",
    ),
    path(
        "password-reset/validate/",
        views.password_reset_validate,
        name="password-reset-validate",
    ),
    path(
        "password-reset/confirm/",
        views.password_reset_confirm,
        name="password-reset-confirm",
    ),
    # ==================== EMAIL VERIFICATION ====================
    # CHANGED: Added token parameter to verify-email
    path("verify-email/<str:token>/", views.verify_email, name="verify-email"),
    path(
        "validate-verification-token/",
        views.validate_verification_token,
        name="validate-verification-token",
    ),
    path("resend-verification/", views.resend_verification, name="resend-verification"),
    path(
        "request-verification/", views.request_verification, name="request-verification"
    ),
    path(
        "check-verification/",
        views.check_verification_status,
        name="check-verification",
    ),
    # ==================== PROFILE MANAGEMENT ====================
    path("profile/", views.get_profile, name="get-profile"),
    path("profile/update/", views.update_profile, name="update-profile"),
    path("profile/change-password/", views.change_password, name="change-password"),
    # ==================== ADMIN ENDPOINTS ====================
    path("admin/users/", views.list_users, name="list-users"),
    path("admin/users/<uuid:user_id>/", views.user_detail, name="user-detail"),
    # NEW: Added admin verification check endpoint
    path(
        "admin/users/<uuid:user_id>/verification/",
        views.admin_check_verification,
        name="admin-check-verification",
    ),
    # ==================== TODO: ADDRESS MANAGEMENT ====================
    # path('addresses/', views.get_addresses, name='get-addresses'),
    # path('addresses/create/', views.create_address, name='create-address'),
    # path('addresses/<uuid:address_id>/update/', views.update_address, name='update-address'),
    # path('addresses/<uuid:address_id>/delete/', views.delete_address, name='delete-address'),
]
