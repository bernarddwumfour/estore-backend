"""
Selectors module - Database read operations for users
"""

from .user_selectors import (
    get_users_filtered,
    get_customers_filtered,
    get_staff_users_filtered,
    get_guest_users_filtered,
    get_user_by_email,
)

from .address_selectors import (
    get_user_addresses,
    get_user_default_address,
)

from .affiliate_selectors import (
    get_affiliates_filtered,
    get_affiliate_by_user,
    get_affiliate_by_referral_code,
)

from .statistics_selectors import (
    get_user_statistics,
)

__all__ = [
    # User selectors
    'get_users_filtered',
    'get_customers_filtered',
    'get_staff_users_filtered',
    'get_guest_users_filtered',
    'get_user_by_email',
    # Address selectors
    'get_user_addresses',
    'get_user_default_address',
    # Affiliate selectors
    'get_affiliates_filtered',
    'get_affiliate_by_user',
    'get_affiliate_by_referral_code',
    # Statistics selectors
    'get_user_statistics',
]