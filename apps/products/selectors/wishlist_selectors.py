"""
Wishlist Selectors - Database read operations for wishlists
No business logic - just queries
"""

from typing import List, Dict, Tuple
from apps.products.models import Wishlist
from ..schemas import serialize_product, serialize_variant


# ==================== WISHLIST SELECTORS ====================

def get_wishlist_items(
    user, page: int = 1, limit: int = 20, is_admin: bool = False
) -> Tuple[List[Dict], int]:
    """Get user's wishlist items grouped by product with variants"""

    # Get all wishlist items with eager loading
    wishlist_items = (
        Wishlist.objects.filter(user=user)
        .order_by("-created_at")
        .select_related("variant")
        .prefetch_related(
            "variant__product",
            "variant__product__category",
            "variant__images",
        )
    )

    # Group by product
    products_dict = {}

    for item in wishlist_items:
        variant = item.variant
        product = variant.product
        product_id = str(product.id)

        # Serialize variant using your schema
        variant_data = serialize_variant(variant, is_admin=is_admin)

        if product_id not in products_dict:
            products_dict[product_id] = {
                "product": product,
                "variants": [],
                "wishlist_items": [],  # Store original items if needed
            }

        products_dict[product_id]["variants"].append(variant_data)
        products_dict[product_id]["wishlist_items"].append(item)

    # Convert to list of serialized products
    result = []
    for group_data in products_dict.values():
        product_data = serialize_product(group_data["product"], is_admin=is_admin)
        product_data["variants"] = group_data["variants"]

        # Set default variant from the variants list
        default_variant = None
        for variant in group_data["variants"]:
            if variant.get("is_default"):
                default_variant = variant
                break

        if not default_variant and group_data["variants"]:
            default_variant = group_data["variants"][0]

        product_data["default_variant"] = default_variant
        product_data["variant"] = default_variant

        result.append(product_data)

    # Apply pagination
    total = len(result)
    offset = (page - 1) * limit
    paginated_result = result[offset : offset + limit]

    return paginated_result, total


def get_wishlist_items_flat(
    user, page: int = 1, limit: int = 20, is_admin: bool = False
) -> Tuple[List[Dict], int]:
    """Get user's wishlist items as flat list (each variant as separate item)"""

    queryset = (
        Wishlist.objects.filter(user=user)
        .order_by("-created_at")
        .select_related("variant")
        .prefetch_related(
            "variant__product",
            "variant__product__category",
            "variant__images",
        )
    )

    total = queryset.count()

    # Paginate
    offset = (page - 1) * limit
    paginated_items = queryset[offset : offset + limit]

    # Serialize using schema
    from apps.products.schemas import serialize_wishlist_item

    items_data = [
        serialize_wishlist_item(item, is_admin=is_admin) for item in paginated_items
    ]

    return items_data, total


def is_in_wishlist(user, variant_id: str) -> bool:
    """Check if variant is in user's wishlist"""
    return Wishlist.objects.filter(user=user, variant_id=variant_id).exists()