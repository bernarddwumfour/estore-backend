"""
Blog Category Schemas — serialization helpers.
Pure functions, no DB writes.
"""

from typing import Dict, Any, List
from apps.blog.models import BlogCategory


def serialize_category(category: BlogCategory, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize a single blog category."""
    data: Dict[str, Any] = {
        "id": str(category.id),
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "is_active": category.is_active,
    }
    if is_admin:
        data["created_at"] = category.created_at.isoformat() if category.created_at else None
        data["updated_at"] = category.updated_at.isoformat() if category.updated_at else None
    return data


def serialize_category_list(
    categories: List[BlogCategory], is_admin: bool = False
) -> List[Dict[str, Any]]:
    """Serialize a list of blog categories."""
    return [serialize_category(cat, is_admin) for cat in categories]
