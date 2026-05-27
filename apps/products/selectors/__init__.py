"""
Selectors module - Database read operations
"""

from .product_selectors import (
    get_product_by_id,
    get_product_by_slug,
    get_admin_products_filtered,
    get_products_filtered,
    get_related_products,
)

from .variant_selectors import (
    get_all_variants,
    get_variant_by_id,
    get_variant_by_sku,
    get_variants_by_product,
)

from .category_selectors import (
    get_category_by_id,
    get_category_by_slug,
    get_all_categories,
    get_subcategories,
    get_visible_categories_tree,
)

from .review_selectors import (
    get_reviews_by_product,
    get_product_rating_stats,
)

from .wishlist_selectors import (
    get_wishlist_items,
    get_wishlist_items_flat,
    is_in_wishlist,
)

__all__ = [
    # Product selectors
    'get_product_by_id',
    'get_product_by_slug',
    'get_admin_products_filtered',
    'get_products_filtered',
    'get_related_products',
    # Variant selectors
    'get_all_variants',
    'get_variant_by_id',
    'get_variant_by_sku',
    'get_variants_by_product',
    # Category selectors
    'get_category_by_id',
    'get_category_by_slug',
    'get_all_categories',
    'get_subcategories',
    'get_visible_categories_tree',
    # Review selectors
    'get_reviews_by_product',
    'get_product_rating_stats',
    # Wishlist selectors
    'get_wishlist_items',
    'get_wishlist_items_flat',
    'is_in_wishlist',
]