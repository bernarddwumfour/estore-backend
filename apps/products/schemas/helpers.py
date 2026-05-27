"""
Helper functions for schemas
"""

from apps.products.models import ProductVariant


def _mask_sku(sku: str) -> str:
    """Mask SKU for non-admin users"""
    if len(sku) <= 8:
        return "****"
    return f"{sku[:4]}****{sku[-4:]}"


def _get_stock_status(variant: ProductVariant) -> str:
    """Get human-readable stock status for customers"""
    if variant.stock > 10:
        return "in_stock"
    elif variant.stock > 0:
        return "low_stock"
    else:
        return "out_of_stock"


def _get_user_display_name(user) -> str:
    """Get user display name"""
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    return user.email.split("@")[0]


def _get_user_initials(user) -> str:
    """Get user initials for avatar"""
    if user.first_name and user.last_name:
        return f"{user.first_name[0]}{user.last_name[0]}".upper()
    return user.email[0].upper()