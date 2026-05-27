"""
Schemas module - Serialization and validation
"""

from .helpers import (
    _mask_sku,
    _get_stock_status,
    _get_user_display_name,
    _get_user_initials,
)

from .category_schemas import (
    serialize_category,
    serialize_category_list,
)

from .product_schemas import (
    serialize_product,
    serialize_product_list,
)

from .variant_schemas import (
    serialize_variant_image,
    serialize_variant,
    serialize_variant_list,
    serialize_variant_list_response,
)

from .review_schemas import (
    serialize_review,
)

from .wishlist_schemas import (
    serialize_wishlist_product,
    serialize_wishlist_item,
    serialize_wishlist_grouped,
)

from .common_schemas import (
    serialize_pagination_metadata,
    serialize_bulk_action_result,
    serialize_product_bulk_action_result,
)

from .validators import (
    validate_bulk_action,
    validate_product_bulk_action,
    validate_product_create,
    validate_product_update,
    validate_variant_create,
    validate_review_create,
)

__all__ = [
    # Category schemas
    'serialize_category',
    'serialize_category_list',
    # Product schemas
    'serialize_product',
    'serialize_product_list',
    # Variant schemas
    'serialize_variant_image',
    'serialize_variant',
    'serialize_variant_list',
    'serialize_variant_list_response',
    # Review schemas
    'serialize_review',
    # Wishlist schemas
    'serialize_wishlist_product',
    'serialize_wishlist_item',
    'serialize_wishlist_grouped',
    # Common schemas
    'serialize_pagination_metadata',
    'serialize_bulk_action_result',
    'serialize_product_bulk_action_result',
    # Validators
    'validate_bulk_action',
    'validate_product_bulk_action',
    'validate_product_create',
    'validate_product_update',
    'validate_variant_create',
    'validate_review_create',
]