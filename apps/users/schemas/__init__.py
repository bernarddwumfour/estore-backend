"""
Schemas module - Serialization and validation for users
"""

from .address_schemas import (
    serialize_address,
    serialize_addresses,
)

from .user_schemas import (
    serialize_user,
    serialize_user_list,
    serialize_customer,
    serialize_customer_list,
    serialize_guest_user,
    serialize_guest_list,
    validate_user_create,
    validate_bulk_user_action,
)

from .staff_schemas import (
    serialize_staff_user,
    serialize_staff_list,
    validate_staff_create,
)

from .affiliate_schemas import (
    serialize_affiliate_user,
    serialize_affiliate_list,
)

from .common_schemas import (
    serialize_pagination_metadata,
    serialize_user_statistics,
    serialize_guest_checkout_data,
)

__all__ = [
    # Address schemas
    'serialize_address',
    'serialize_addresses',
    # User schemas
    'serialize_user',
    'serialize_user_list',
    'serialize_customer',
    'serialize_customer_list',
    'serialize_guest_user',
    'serialize_guest_list',
    'validate_user_create',
    'validate_bulk_user_action',
    # Staff schemas
    'serialize_staff_user',
    'serialize_staff_list',
    'validate_staff_create',
    # Affiliate schemas
    'serialize_affiliate_user',
    'serialize_affiliate_list',
    # Common schemas
    'serialize_pagination_metadata',
    'serialize_user_statistics',
    'serialize_guest_checkout_data',
]