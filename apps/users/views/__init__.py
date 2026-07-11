"""
Views module - API endpoints for users
"""

from .auth_views import (
    register_customer,
    register_user,
    login,
    logout,
    refresh_token,
)

from .profile_views import (
    get_profile,
    update_profile,
    change_password,
)

from .password_views import (
    password_reset_request,
    password_reset_confirm,
    password_reset_validate,
)

from .verification_views import (
    verify_email,
    validate_verification_token,
    resend_verification,
    request_verification,
    check_verification_status,
    admin_check_verification,
)

from .guest_views import (
    guest_checkout,
    guest_convert,
)

from .admin_user_views import (
    list_all_users,
    user_detail,
    list_customers,
    list_guest_users,
    bulk_user_action,
)

from .staff_views import (
    list_staff_users,
    create_staff_user,
    bulk_staff_action,
    delete_staff_user,
)

from .affiliate_views import (
    list_affiliate_users,
    make_affiliate,
    update_affiliate_commission,
    make_affiliate_by_email,
    remove_affiliate,
    toggle_affiliate_status,
    get_affiliate_profile,
)

from .statistics_views import (
    user_statistics,
)

__all__ = [
    # Auth views
    'register_customer',
    'register_user',
    'login',
    'logout',
    'refresh_token',
    # Profile views
    'get_profile',
    'update_profile',
    'change_password',
    # Password views
    'password_reset_request',
    'password_reset_confirm',
    'password_reset_validate',
    # Verification views
    'verify_email',
    'validate_verification_token',
    'resend_verification',
    'request_verification',
    'check_verification_status',
    'admin_check_verification',
    # Guest views
    'guest_checkout',
    'guest_convert',
    # Admin user views
    'list_all_users',
    'user_detail',
    'list_customers',
    'list_guest_users',
    'bulk_user_action',
    # Staff views
    'list_staff_users',
    'create_staff_user',
    'bulk_staff_action',
    'delete_staff_user',
    # Affiliate views
    'list_affiliate_users',
    'make_affiliate',
    'update_affiliate_commission',
    'make_affiliate_by_email',
    'remove_affiliate',
    'toggle_affiliate_status',
    'get_affiliate_profile',
    # Statistics views
    'user_statistics',
]
