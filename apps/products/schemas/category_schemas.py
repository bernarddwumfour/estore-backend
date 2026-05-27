"""
Category Schemas - Serialization for categories
"""

from typing import Dict, Any, List
from apps.products.models import Category


def serialize_category(category: Category, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize a single category"""
    data = {
        "id": str(category.id),
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "parent_id": str(category.parent_id) if category.parent_id else None,
        "parent_name": category.parent.name if category.parent else None,
        "image": category.image.url if category.image else None,
        "full_path": category.full_path,
        "is_active": category.is_active,
    }
    
    # Only include admin-only fields for admin users
    if is_admin:
        data["is_hidden"] = category.is_hidden
        data["meta_title"] = category.meta_title
        data["meta_description"] = category.meta_description
        data["created_at"] = category.created_at.isoformat() if category.created_at else None
        data["updated_at"] = category.updated_at.isoformat() if category.updated_at else None
    
    return data


def serialize_category_list(
    categories: List[Category], is_admin: bool = False
) -> List[Dict]:
    """Serialize list of categories"""
    return [serialize_category(cat, is_admin) for cat in categories]