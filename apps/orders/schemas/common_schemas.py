"""
Common Schemas - Shared serialization utilities
"""

from typing import Dict, List, Optional
from decimal import Decimal


def serialize_pagination_metadata(pagination_meta: Dict) -> Dict:
    """Serialize pagination metadata for API response"""
    return {
        "current_page": pagination_meta["current_page"],
        "per_page": pagination_meta["per_page"],
        "total": pagination_meta["total"],
        "total_pages": pagination_meta["total_pages"],
        "has_next": pagination_meta["has_next"],
        "has_previous": pagination_meta["has_previous"],
        "next_page": pagination_meta["next_page"],
        "previous_page": pagination_meta["previous_page"],
        "start_index": pagination_meta["start_index"],
        "end_index": pagination_meta["end_index"],
    }