"""
Variant Schemas - Serialization for variants and images
"""

from typing import Dict, Any, List, Optional
from apps.products.models import ProductVariant, VariantImage
from .helpers import _mask_sku, _get_stock_status


def serialize_variant_image(image: VariantImage, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize variant image"""
    if not image:
        return None

    data = {
        "id": str(image.id),
        "url": image.image.url if image.image else None,
        "alt_text": image.alt_text,
        "image_type": image.image_type,
        "order": image.order,
    }

    if is_admin:
        data["is_active"] = image.is_active
        data["created_at"] = image.created_at.isoformat() if image.created_at else None

    return data


def serialize_variant(
    variant: ProductVariant, is_admin: bool = False, include_images: bool = True
) -> Dict[str, Any]:
    """Serialize variant - sensitive data only for admins"""
    if not variant:
        return None

    # Base fields (visible to everyone)
    data = {
        "id": str(variant.id),
        "sku": variant.sku if is_admin else _mask_sku(variant.sku),
        "attributes": variant.attributes,
        "price": float(variant.price),
        "discounted_price": float(variant.discounted_price),
        "discount_percentage": float(variant.discount_percentage),
        "is_in_stock": variant.is_in_stock,
        "stock": variant.stock,
        "discount_amount": float(variant.discount_amount),
        "is_default": variant.is_default,
    }

    # Admin-only fields
    if is_admin:
        data.update(
            {
                "is_active": variant.is_active,
                "is_low_stock": variant.is_low_stock,
                "low_stock_threshold": variant.low_stock_threshold,
                "dimensions": {
                    "weight": float(variant.weight) if variant.weight else None,
                    "height": float(variant.height) if variant.height else None,
                    "width": float(variant.width) if variant.width else None,
                    "depth": float(variant.depth) if variant.depth else None,
                },
                "created_at": variant.created_at.isoformat() if variant.created_at else None,
                "updated_at": variant.updated_at.isoformat() if variant.updated_at else None,
            }
        )
    else:
        # Public-facing stock info
        data["stock_status"] = _get_stock_status(variant)

    if include_images:
        data["images"] = [
            serialize_variant_image(img, is_admin)
            for img in variant.images.filter(is_active=True).order_by("order")
        ]

    return data


def serialize_variant_list(variant: ProductVariant, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize variant for list view with product info"""
    if not variant:
        return None

    # Get base variant data
    variant_data = serialize_variant(variant, is_admin=is_admin, include_images=True)

    # Add product information
    product = variant.product
    variant_data["product"] = {
        "id": str(product.id),
        "title": product.title,
        "slug": product.slug,
        "status": product.status if is_admin else None,
        "category": (
            {
                "id": str(product.category.id) if product.category else None,
                "name": product.category.name if product.category else None,
            }
            if is_admin
            else None
        ),
    }

    return variant_data


def serialize_variant_list_response(variants: List[ProductVariant], is_admin: bool = False) -> List[Dict]:
    """Serialize list of variants for response"""
    return [serialize_variant_list(v, is_admin) for v in variants]