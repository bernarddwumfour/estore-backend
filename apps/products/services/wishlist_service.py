"""
Wishlist Service - Business logic for wishlists
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction

from apps.products.models import Wishlist
from apps.products.selectors import get_variant_by_id, get_wishlist_items, get_wishlist_items_flat
from apps.users.models import User

logger = logging.getLogger(__name__)


class WishlistService:
    """Wishlist business logic"""

    @staticmethod
    def get_user_wishlist(
        user: User,
        page: int = 1,
        limit: int = 20,
        is_admin: bool = False,
        grouped: bool = True,
    ) -> Tuple[List[Dict], int]:
        """Get user's wishlist items"""

        if grouped:
            # Grouped by product (multiple variants under one product)
            return get_wishlist_items(user, page, limit, is_admin)
        else:
            # Flat list (each variant as separate item)
            return get_wishlist_items_flat(user, page, limit, is_admin)

    @staticmethod
    @transaction.atomic
    def add_to_wishlist(
        user: User, variant_id: str
    ) -> Tuple[Optional[Wishlist], Optional[str]]:
        """Add variant to user's wishlist"""
        try:
            variant = get_variant_by_id(variant_id)
            if not variant:
                return None, "Variant not found"

            # Check if already in wishlist
            if Wishlist.objects.filter(user=user, variant=variant).exists():
                return None, "Item already in wishlist"

            # Add to wishlist
            wishlist_item = Wishlist.objects.create(user=user, variant=variant)

            logger.info(f"Added {variant.sku} to wishlist for user {user.email}")
            return wishlist_item, None

        except Exception as e:
            logger.error(f"Wishlist add error: {str(e)}")
            return None, f"Failed to add to wishlist: {str(e)}"

    @staticmethod
    @transaction.atomic
    def remove_from_wishlist(user: User, variant_id: str) -> Tuple[bool, Optional[str]]:
        """Remove variant from user's wishlist"""
        try:
            deleted_count, _ = Wishlist.objects.filter(
                user=user, variant_id=variant_id
            ).delete()

            if deleted_count > 0:
                logger.info(
                    f"Removed variant {variant_id} from wishlist for user {user.email}"
                )
                return True, None
            else:
                return False, "Item not found in wishlist"

        except Exception as e:
            logger.error(f"Wishlist remove error: {str(e)}")
            return False, f"Failed to remove from wishlist: {str(e)}"