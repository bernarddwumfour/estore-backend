"""
Common Schemas - Shared serialization utilities
"""

from typing import Dict, Any


def serialize_pagination_metadata(pagination_meta: Dict) -> Dict:
    """Serialize pagination metadata"""
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


def serialize_user_statistics(stats: Dict) -> Dict:
    """Serialize user statistics for dashboard"""
    return {
        "total_users": stats["total_users"],
        "total_customers": stats["total_customers"],
        "total_guests": stats["total_guests"],
        "total_staff": stats["total_staff"],
        "total_admins": stats["total_admins"],
        "total_affiliates": stats["total_affiliates"],
        "active_users": stats["active_users"],
        "inactive_users": stats["inactive_users"],
        "verified_emails": stats["verified_emails"],
        "unverified_emails": stats["unverified_emails"],
    }


def serialize_guest_checkout_data(user, order_data: Dict = None) -> Dict[str, Any]:
    """Serialize guest checkout response"""
    data = {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_guest": user.is_guest,
    }
    
    if order_data:
        data["order"] = order_data
    
    return data