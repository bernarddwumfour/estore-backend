"""
Wishlist Service - Business logic for wishlists
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction

from apps.products.models import Wishlist
from apps.products.selectors import get_variant_by_id, get_wishlist_items, get_wishlist_items_flat
from apps.users.models import User
from apps.common.logging import log_action, LogSeverity, get_user_info

logger = logging.getLogger(__name__)

# App name constant for filtering in UI
APP_NAME = "products"


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
        start_time = time.time()
        action = "get_user_wishlist"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Retrieving user wishlist",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "page": page,
                "limit": limit,
                "grouped": grouped,
                "is_admin": is_admin
            }
        )

        try:
            if grouped:
                items, total = get_wishlist_items(user, page, limit, is_admin)
            else:
                items, total = get_wishlist_items_flat(user, page, limit, is_admin)

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.DEBUG,
                action=action,
                description="Wishlist retrieved successfully",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "total_items": total,
                    "items_returned": len(items),
                    "page": page,
                    "limit": limit,
                    "grouped": grouped,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )

            return items, total

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to retrieve wishlist: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            raise

    @staticmethod
    @transaction.atomic
    def add_to_wishlist(
        user: User, variant_id: str
    ) -> Tuple[Optional[Wishlist], Optional[str]]:
        """Add variant to user's wishlist"""
        start_time = time.time()
        action = "add_to_wishlist"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Adding variant to wishlist: {variant_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "variant_id": variant_id,
                "user_email": get_user_info(user)
            }
        )
        
        try:
            variant = get_variant_by_id(variant_id)
            if not variant:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Variant not found: {variant_id}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "variant_id": variant_id,
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return None, "Variant not found"

            # Check if already in wishlist
            existing_item = Wishlist.objects.filter(user=user, variant=variant).first()
            if existing_item:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Item already in wishlist: {variant.sku}",
                    status_code=409,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "variant_id": variant_id,
                        "variant_sku": variant.sku,
                        "product_title": variant.product.title,
                        "existing_wishlist_id": str(existing_item.id),
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return None, "Item already in wishlist"

            # Add to wishlist
            wishlist_item = Wishlist.objects.create(user=user, variant=variant)

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Added to wishlist: {variant.sku}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "wishlist_id": str(wishlist_item.id),
                    "variant_id": variant_id,
                    "variant_sku": variant.sku,
                    "product_id": str(variant.product.id),
                    "product_title": variant.product.title,
                    "price": float(variant.price),
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return wishlist_item, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to add to wishlist: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "variant_id": variant_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return None, f"Failed to add to wishlist: {str(e)}"

    @staticmethod
    @transaction.atomic
    def remove_from_wishlist(user: User, variant_id: str) -> Tuple[bool, Optional[str]]:
        """Remove variant from user's wishlist"""
        start_time = time.time()
        action = "remove_from_wishlist"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Removing variant from wishlist: {variant_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "variant_id": variant_id,
                "user_email": get_user_info(user)
            }
        )
        
        try:
            # Get the item before deleting for logging
            wishlist_item = Wishlist.objects.filter(
                user=user, variant_id=variant_id
            ).select_related('variant__product').first()
            
            if not wishlist_item:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Item not found in wishlist: {variant_id}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "variant_id": variant_id,
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return False, "Item not found in wishlist"

            variant_sku = wishlist_item.variant.sku
            product_title = wishlist_item.variant.product.title
            wishlist_id = str(wishlist_item.id)
            
            deleted_count, _ = Wishlist.objects.filter(
                user=user, variant_id=variant_id
            ).delete()

            if deleted_count > 0:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.INFO,
                    action=action,
                    description=f"Removed from wishlist: {variant_sku}",
                    status_code=200,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "wishlist_id": wishlist_id,
                        "variant_id": variant_id,
                        "variant_sku": variant_sku,
                        "product_title": product_title,
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return True, None
            else:
                # This shouldn't happen since we checked above, but just in case
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Delete failed - item not found: {variant_id}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "variant_id": variant_id,
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return False, "Item not found in wishlist"

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to remove from wishlist: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "variant_id": variant_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return False, f"Failed to remove from wishlist: {str(e)}"

    @staticmethod
    @transaction.atomic
    def clear_wishlist(user: User) -> Tuple[int, Optional[str]]:
        """
        Clear all items from user's wishlist
        
        Returns:
            Tuple of (deleted_count, error_message)
        """
        start_time = time.time()
        action = "clear_wishlist"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Clearing user wishlist",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"user_email": get_user_info(user)}
        )
        
        try:
            # Get count before deletion for logging
            count_before = Wishlist.objects.filter(user=user).count()
            
            if count_before == 0:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description="Wishlist already empty",
                    status_code=200,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "items_deleted": 0,
                        "duration_ms": round(duration_ms, 2),
                        "requested_by": get_user_info(user)
                    }
                )
                return 0, None
            
            deleted_count, _ = Wishlist.objects.filter(user=user).delete()
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Wishlist cleared: {deleted_count} items removed",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "items_deleted": deleted_count,
                    "items_before": count_before,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return deleted_count, None
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to clear wishlist: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return 0, f"Failed to clear wishlist: {str(e)}"

    @staticmethod
    def is_in_wishlist(user: User, variant_id: str) -> bool:
        """Check if variant is in user's wishlist"""
        start_time = time.time()
        action = "is_in_wishlist"
        
        try:
            exists = Wishlist.objects.filter(user=user, variant_id=variant_id).exists()
            
            duration_ms = (time.time() - start_time) * 1000
            # Use debug level for this common check to avoid log noise
            log_action(
                logger=logger,
                severity=LogSeverity.DEBUG,
                action=action,
                description="Wishlist check completed",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "variant_id": variant_id,
                    "exists": exists,
                    "duration_ms": round(duration_ms, 2)
                }
            )
            return exists
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to check wishlist: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "variant_id": variant_id,
                    "error": str(e),
                    "duration_ms": round(duration_ms, 2)
                }
            )
            return False

    @staticmethod
    def get_wishlist_summary(user: User) -> Dict[str, Any]:
        """Get wishlist summary statistics for the user"""
        start_time = time.time()
        action = "get_wishlist_summary"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description="Retrieving wishlist summary",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"user_email": get_user_info(user)}
        )
        
        try:
            from django.db.models import  Sum
            
            wishlist_items = Wishlist.objects.filter(user=user).select_related('variant')
            
            total_items = wishlist_items.count()
            
            # Count variants that are in stock
            in_stock_count = wishlist_items.filter(variant__stock__gt=0).count()
            
            # Count variants that are out of stock
            out_of_stock_count = wishlist_items.filter(variant__stock=0).count()
            
            # Count variants that are on discount
            on_discount_count = wishlist_items.filter(variant__discount_amount__gt=0).count()
            
            # Get total potential savings (sum of discounts)
            total_potential_savings = wishlist_items.aggregate(
                total=Sum('variant__discount_amount')
            )['total'] or 0
            
            # Get unique products count
            unique_products_count = wishlist_items.values('variant__product').distinct().count()
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.DEBUG,
                action=action,
                description="Wishlist summary retrieved",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "total_items": total_items,
                    "unique_products": unique_products_count,
                    "in_stock_count": in_stock_count,
                    "out_of_stock_count": out_of_stock_count,
                    "on_discount_count": on_discount_count,
                    "total_potential_savings": float(total_potential_savings),
                    "duration_ms": round(duration_ms, 2)
                }
            )
            
            return {
                "total_items": total_items,
                "unique_products": unique_products_count,
                "in_stock_count": in_stock_count,
                "out_of_stock_count": out_of_stock_count,
                "on_discount_count": on_discount_count,
                "total_potential_savings": float(total_potential_savings),
            }
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to get wishlist summary: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "error": str(e),
                    "duration_ms": round(duration_ms, 2)
                }
            )
            return {
                "total_items": 0,
                "unique_products": 0,
                "in_stock_count": 0,
                "out_of_stock_count": 0,
                "on_discount_count": 0,
                "total_potential_savings": 0.0,
            }