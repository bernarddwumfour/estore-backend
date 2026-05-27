"""
Review Schemas - Serialization for reviews
"""

from typing import Dict, Any
from .helpers import _get_user_display_name, _get_user_initials


def serialize_review(
    review, is_admin: bool = False, include_user: bool = True
) -> Dict[str, Any]:
    """Serialize review - admin sees more details"""
    if not review:
        return None

    # Base fields
    data = {
        "id": str(review.id),
        "rating": review.rating,
        "title": review.title,
        "comment": review.comment,
        "helpful_yes": review.helpful_yes,
        "helpful_no": review.helpful_no,
        "is_verified_purchase": review.is_verified_purchase,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }

    # Admin-only fields
    if is_admin:
        data.update(
            {
                "is_edited": review.is_edited,
                "is_approved": review.is_approved,
                "updated_at": review.updated_at.isoformat() if review.updated_at else None,
                "user_id": str(review.user.id) if review.user else None,
                "user_email": review.user.email if review.user else None,
            }
        )

    # User info
    if include_user and review.user:
        data["user"] = {
            "name": _get_user_display_name(review.user),
            "initials": _get_user_initials(review.user),
        }
        if is_admin:
            data["user"]["id"] = str(review.user.id)
            data["user"]["email"] = review.user.email

    return data