"""
Wishlist Schemas - Serialization for wishlists
"""

from typing import Dict, Any, List
from .product_schemas import serialize_product
from .variant_schemas import serialize_variant


def serialize_wishlist_product(
    product, variants: List[Dict], is_admin: bool = False
) -> Dict[str, Any]:
    """Serialize product with specific variants from wishlist"""
    if not product:
        return None

    # Get base product data (without variants)
    base_product = serialize_product(product, is_admin=is_admin)

    # Add the wishlist-specific variants
    base_product["variants"] = variants

    # Set default variant from the variants list
    default_variant = None
    for variant in variants:
        if variant.get("is_default"):
            default_variant = variant
            break

    if not default_variant and variants:
        default_variant = variants[0]

    base_product["default_variant"] = default_variant
    base_product["variant"] = default_variant  # For backward compatibility

    return base_product


def serialize_wishlist_item(item, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize a wishlist item with product and variant info"""
    if not item:
        return None

    variant = item.variant
    product = variant.product

    # Serialize the variant
    variant_data = serialize_variant(variant, is_admin=is_admin, include_images=True)

    product_data = serialize_product(product, is_admin=is_admin)

    product_data["variant"] = variant_data

    if variant.is_default:
        product_data["default_variant"] = variant_data
    else:
        default_variant = product.variants.filter(is_default=True).first()
        if default_variant:
            product_data["default_variant"] = serialize_variant(
                default_variant, is_admin=is_admin, include_images=True
            )
        else:
            product_data["default_variant"] = variant_data

    return {
        "wishlist_id": str(item.id),
        "added_at": item.created_at.isoformat() if item.created_at else None,
        "product": product_data,
    }


def serialize_wishlist_grouped(
    products_dict: Dict, is_admin: bool = False
) -> List[Dict]:
    """Serialize grouped wishlist products with their variants"""
    result = []

    for product_id, group_data in products_dict.items():
        product = group_data["product"]
        variants = group_data["variants"]

        product_data = serialize_product(
            product, is_admin=is_admin
        )

        product_data["variants"] = variants

        default_variant = None
        for variant in variants:
            if variant.get("is_default"):
                default_variant = variant
                break

        if not default_variant and variants:
            default_variant = variants[0]

        product_data["default_variant"] = default_variant
        product_data["variant"] = default_variant

        result.append(product_data)

    return result