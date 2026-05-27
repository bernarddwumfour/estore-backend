"""
Product Schemas - Serialization for products
"""

from typing import Dict, Any, List, Optional, Tuple
from apps.products.models import Product
from .variant_schemas import serialize_variant

def serialize_product(product: Product, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize a single product with variants and images"""
    
    # Get all variants with their images
    variants = []
    for variant in product.variants.all():
        variant_data = serialize_variant(variant, is_admin=is_admin, include_images=True)
        variants.append(variant_data)
    
    # Get default variant
    default_variant = None
    if product.default_variant:
        default_variant = serialize_variant(product.default_variant, is_admin=is_admin, include_images=True)
    
    data = {
        "id": str(product.id),
        "title": product.title,
        "slug": product.slug,
        "description": product.description,
        "features": product.features,
        "options": product.options,
        "average_rating": float(product.average_rating),
        "total_reviews": product.total_reviews,
        "min_price": float(product.min_price),
        "max_price": float(product.max_price),
        "has_stock": product.has_stock,
        "total_stock": product.total_stock,
        "is_featured": product.is_featured,
        "is_bestseller": product.is_bestseller,
        "is_new": product.is_new,
        "default_variant": default_variant,
        "variants": variants,
        "category": {
            "id": str(product.category.id) if product.category else None,
            "name": product.category.name if product.category else None,
            "slug": product.category.slug if product.category else None,
        } if product.category else None,
    }
    
    # Only include admin-only fields for admin users
    if is_admin:
        data["status"] = product.status
        data["meta_title"] = product.meta_title
        data["meta_description"] = product.meta_description
        data["created_at"] = product.created_at.isoformat() if product.created_at else None
        data["updated_at"] = product.updated_at.isoformat() if product.updated_at else None
        data["published_at"] = product.published_at.isoformat() if product.published_at else None
    
    return data


def serialize_product_list(products: List[Product], is_admin: bool = False) -> List[Dict]:
    """Serialize list of products"""
    return [serialize_product(product, is_admin) for product in products]