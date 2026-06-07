"""
Review Schemas - Serialization for product and order reviews
"""

from typing import Dict, Any
from .helpers import _get_user_display_name, _get_user_initials


def serialize_review(
    review, is_admin: bool = False, include_user: bool = True
) -> Dict[str, Any]:
    """Serialize product review - admin sees more details"""
    if not review:
        return None

    # Base fields
    data = {
        "id": str(review.id),
        "type": "product",
        "rating": review.rating,
        "title": review.title,
        "comment": review.comment,
        "helpful_yes": review.helpful_yes,
        "helpful_no": review.helpful_no,
        "is_verified_purchase": review.is_verified_purchase,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }

    # Product-specific fields
    data["product"] = {
        "id": str(review.product.id),
        "title": review.product.title,
        "slug": review.product.slug,
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


def serialize_order_review(
    review, is_admin: bool = False, include_user: bool = True
) -> Dict[str, Any]:
    """Serialize order review - admin sees more details"""
    if not review:
        return None

    # Base fields
    data = {
        "id": str(review.id),
        "type": "order",
        "overall_rating": review.overall_rating,
        "shipping_rating": review.shipping_rating,
        "packaging_rating": review.packaging_rating,
        "delivery_speed_rating": review.delivery_speed_rating,
        "customer_service_rating": review.customer_service_rating,
        "average_rating": round(review.average_rating, 2),
        "title": review.title,
        "comment": review.comment,
        "images": review.images,
        "helpful_yes": review.helpful_yes,
        "helpful_no": review.helpful_no,
        "admin_response": review.admin_response,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }

    # Order-specific fields
    data["order"] = {
        "id": str(review.order.id),
        "order_number": review.order.order_number,
        "total": float(review.order.total) if hasattr(review.order, 'total') else 0,
    }

    # Admin-only fields
    if is_admin:
        data.update(
            {
                "is_edited": review.is_edited,
                "is_approved": review.is_approved,
                "admin_response_at": review.admin_response_at.isoformat() if review.admin_response_at else None,
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


def serialize_admin_review_list(review, is_admin: bool = True) -> Dict[str, Any]:
    """Serialize review for admin list view (works for both product and order reviews)"""
    if not review:
        return None

    # Determine review type
    review_type = "product" if hasattr(review, 'product') else "order"

    if review_type == "product":
        return {
            "id": str(review.id),
            "type": "product",
            "product_title": review.product.title,
            "product_id": str(review.product.id),
            "user_email": review.user.email,
            "rating": review.rating,
            "comment_preview": review.comment[:100] + "..." if len(review.comment) > 100 else review.comment,
            "is_approved": review.is_approved,
            "is_verified_purchase": review.is_verified_purchase,
            "helpful_yes": review.helpful_yes,
            "created_at": review.created_at.isoformat() if review.created_at else None,
        }
    else:
        return {
            "id": str(review.id),
            "type": "order",
            "order_number": review.order.order_number,
            "user_email": review.user.email,
            "overall_rating": review.overall_rating,
            "comment_preview": review.comment[:100] + "..." if len(review.comment) > 100 else review.comment,
            "is_approved": review.is_approved,
            "helpful_yes": review.helpful_yes,
            "created_at": review.created_at.isoformat() if review.created_at else None,
        }