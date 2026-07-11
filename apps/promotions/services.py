"""
Promotion Service - Business logic for promotions
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal, ROUND_HALF_UP
from django.conf import settings
from django.db import transaction
from django.db import IntegrityError
from django.utils.text import slugify
from django.utils import timezone
from django.db.models import Q, F, Sum

from apps.promotions.models import (
    Promotion,
    PromotionItem,
    PromotionImage,
    DiscountCode,
    AffiliateCommission,
)
from apps.products.selectors import get_variant_by_id, get_product_by_id
from apps.products.models import ProductVariant
from apps.users.models import User
from apps.users.models.affiliate import Affiliate
from apps.common.logging import log_action, LogSeverity, get_user_info

logger = logging.getLogger(__name__)
APP_NAME = "promotions"


class PromotionService:
    """Promotion management business logic"""

    from django.utils import timezone

    @staticmethod
    @transaction.atomic
    def create_promotion(
        data: Dict[str, Any],
        image_files: List = None,
        user: User = None
    ) -> Tuple[Optional[Promotion], Optional[Dict]]:
        """Create a new promotion with items"""
        start_time = time.time()
        action = "promotion_create"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating promotion: {data.get('name')}",
            status_code=0,
            user=user,
            request=None,  # No request object here, will be passed from view
            app_name=APP_NAME,
            extra={"name": data.get("name"), "item_count": len(data.get("items", []))}
        )
        
        try:
            # Resolve every variant up-front so a bad variant_id fails BEFORE we
            # write anything. A caught exception inside @transaction.atomic does
            # NOT roll back, so a partial create would otherwise commit.
            items_data = data.get("items", [])
            resolved_items = []
            for item_data in items_data:
                variant = get_variant_by_id(item_data["variant_id"])
                if not variant:
                    return None, {"items": f"Variant not found: {item_data['variant_id']}"}
                resolved_items.append((variant, item_data))

            # Generate unique slug
            base_slug = slugify(data["name"])
            slug = base_slug
            counter = 1
            while Promotion.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            # Make datetimes timezone-aware
            starts_at = data["starts_at"]
            ends_at = data.get("ends_at")
            
            # If datetime is naive, make it aware with current timezone
            if isinstance(starts_at, str):
                from dateutil import parser
                starts_at = parser.parse(starts_at)
            
            if timezone.is_naive(starts_at):
                starts_at = timezone.make_aware(starts_at)
            
            if ends_at:
                if isinstance(ends_at, str):
                    ends_at = parser.parse(ends_at)
                if timezone.is_naive(ends_at):
                    ends_at = timezone.make_aware(ends_at)
            
            # Create promotion
            promotion = Promotion.objects.create(
                name=data["name"],
                slug=slug,
                description=data.get("description", ""),
                bundle_price=Decimal(str(data["bundle_price"])),
                status=Promotion.STATUS_DRAFT,
                starts_at=starts_at,
                ends_at=ends_at,
                meta_title=data.get("meta_title", ""),
                meta_description=data.get("meta_description", ""),
                created_by=user,
            )
            
            # Create promotion items (variants already resolved above)
            for variant, item_data in resolved_items:
                PromotionItem.objects.create(
                    promotion=promotion,
                    variant=variant,
                    quantity=item_data["quantity"],
                    original_price=variant.price,
                    cost_price_snapshot=variant.cost_price,
                    is_free=item_data.get("is_free", False),
                    is_available=variant.stock >= item_data["quantity"],
                )
            
            # Add images if provided
            if image_files:
                for i, image_file in enumerate(image_files):
                    image_type = "banner" if i == 0 else "gallery"
                    PromotionImage.objects.create(
                        promotion=promotion,
                        image=image_file,
                        image_type=image_type,
                        order=i,
                        is_active=True,
                    )
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Promotion created: {promotion.name}",
                status_code=201,
                user=user,
                request=None,
                app_name=APP_NAME,
                extra={
                    "promotion_id": str(promotion.id),
                    "name": promotion.name,
                    "slug": promotion.slug,
                    "bundle_price": float(promotion.bundle_price),
                    "items_count": len(items_data),
                    "images_count": len(image_files) if image_files else 0,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return promotion, None
            
        except Exception as e:
            # Caught exceptions inside @transaction.atomic do not auto-rollback;
            # flag it so the partial write is discarded on block exit.
            transaction.set_rollback(True)
            duration_ms = (time.time() - start_time) * 1000
            logger.exception("Failed to create promotion")
            return None, {"general": "Failed to create promotion. Please try again."}
        
        
        
    @staticmethod
    @transaction.atomic
    def activate_promotion(
        promotion_id: str, user: User
    ) -> Tuple[bool, Optional[Dict]]:
        """Activate a promotion - no start date restriction"""
        start_time = time.time()
        action = "promotion_activate"
        
        try:
            promotion = Promotion.objects.get(id=promotion_id)
            
            # Check if already active
            if promotion.status == Promotion.STATUS_ACTIVE:
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Promotion already active: {promotion.name}",
                    status_code=400,
                    user=user,
                    app_name=APP_NAME,
                    extra={"promotion_id": str(promotion_id), "status": promotion.status}
                )
                return False, {"status": "Promotion is already active"}
            
            # REMOVED: Start date check - promotions can be activated at any time
            # Stock validation only happens during checkout, not at activation
            
            # Update status
            old_status = promotion.status
            promotion.status = Promotion.STATUS_ACTIVE
            promotion.save()

            from apps.social.services import SocialPostService
            SocialPostService.queue_for_approval("promotion", promotion)

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Promotion activated: {promotion.name} (was {old_status})",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "promotion_id": str(promotion.id),
                    "name": promotion.name,
                    "old_status": old_status,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return True, None
            
        except Promotion.DoesNotExist:
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Promotion not found: {promotion_id}",
                status_code=404,
                user=user,
                app_name=APP_NAME,
                extra={"promotion_id": str(promotion_id)}
            )
            return False, {"promotion": "Promotion not found"}
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to activate promotion: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"promotion_id": str(promotion_id), "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return False, {"general": f"Failed to activate promotion: {str(e)}"}
        
        
    @staticmethod
    @transaction.atomic
    def pause_promotion(
        promotion_id: str, user: User
    ) -> Tuple[bool, Optional[Dict]]:
        """Pause an active promotion"""
        start_time = time.time()
        action = "promotion_pause"
        
        try:
            promotion = Promotion.objects.get(id=promotion_id)
            
            if promotion.status != Promotion.STATUS_ACTIVE:
                return False, {"status": "Only active promotions can be paused"}
            
            promotion.status = Promotion.STATUS_PAUSED
            promotion.save()
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Promotion paused: {promotion.name}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "promotion_id": str(promotion.id),
                    "name": promotion.name,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return True, None
            
        except Promotion.DoesNotExist:
            return False, {"promotion": "Promotion not found"}
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to pause promotion: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"promotion_id": promotion_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return False, {"general": f"Failed to pause promotion: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def deduct_stock_for_promotion(
        promotion_id: str
    ) -> Tuple[bool, Optional[str]]:
        """Deduct stock for all items in a promotion (called during checkout)"""
        try:
            promotion = Promotion.objects.get(id=promotion_id)
            
            if not promotion.is_currently_active:
                return False, "Promotion is not active"
            
            # Use select_for_update to lock rows
            items = promotion.items.select_related('variant').select_for_update()
            
            for item in items:
                if item.variant.stock < item.quantity:
                    return False, f"Insufficient stock for {item.variant.sku}"
                
                item.variant.stock -= item.quantity
                item.variant.save(update_fields=["stock"])
                
                # Refresh availability
                item.refresh_availability()
            
            # Check if any item became unavailable after deduction
            unavailable = promotion.unavailable_items
            if unavailable:
                promotion.status = Promotion.STATUS_PAUSED
                promotion.save(update_fields=["status"])
            
            return True, None
            
        except Promotion.DoesNotExist:
            return False, "Promotion not found"
        except Exception as e:
            logger.error(f"Stock deduction failed: {str(e)}")
            return False, str(e)

    @staticmethod
    def refresh_promotion_availability(
        promotion_id: str, user: User = None
    ) -> Tuple[bool, Optional[Dict]]:
        """Refresh availability for all items in a promotion"""
        start_time = time.time()
        action = "promotion_refresh"
        
        try:
            promotion = Promotion.objects.get(id=promotion_id)
            any_unavailable = False
            
            for item in promotion.items.all():
                was_available = item.is_available
                item.refresh_availability()
                
                if not item.is_available:
                    any_unavailable = True
            
            # If any item became unavailable, pause the promotion
            if any_unavailable and promotion.status == Promotion.STATUS_ACTIVE:
                promotion.status = Promotion.STATUS_PAUSED
                promotion.save(update_fields=["status"])
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Promotion availability refreshed: {promotion.name}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "promotion_id": str(promotion.id),
                    "name": promotion.name,
                    "any_unavailable": any_unavailable,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return True, None
            
        except Promotion.DoesNotExist:
            return False, {"promotion": "Promotion not found"}
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to refresh promotion: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"promotion_id": promotion_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return False, {"general": str(e)}
        
        
    @staticmethod
    @transaction.atomic
    def bulk_action_promotions(
        promotion_ids: List[str], action: str, user: User
    ) -> Tuple[Dict, Optional[Dict]]:
        """
        Perform bulk actions on promotions
        
        Actions: activate, pause, delete
        
        Returns:
            Tuple of (results dict, error dict)
            results: {
                'success': [{'id': str, 'name': str}],
                'failed': [{'id': str, 'name': str, 'reason': str}],
                'total': int
            }
        """
        start_time = time.time()
        action_name = f"bulk_promotion_{action}"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action_name,
            description=f"Starting bulk {action} on {len(promotion_ids)} promotions",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"action": action, "total_promotions": len(promotion_ids)}
        )
        
        results = {"success": [], "failed": [], "total": len(promotion_ids)}
        
        if action == "activate":
            for promotion_id in promotion_ids:
                try:
                    promotion = Promotion.objects.get(id=promotion_id)
                    
                    # Check if already active
                    if promotion.status == Promotion.STATUS_ACTIVE:
                        results["failed"].append({
                            "id": promotion_id,
                            "name": promotion.name,
                            "reason": "Already active"
                        })
                        continue
                    
                    # Validate stock before activation
                    has_issue = False
                    for item in promotion.items.all():
                        if not item.is_free and not item.has_sufficient_stock:
                            results["failed"].append({
                                "id": promotion_id,
                                "name": promotion.name,
                                "reason": f"Insufficient stock for {item.variant.sku}"
                            })
                            has_issue = True
                            break
                    
                    if has_issue:
                        continue
                    
                    promotion.status = Promotion.STATUS_ACTIVE
                    promotion.save()
                    results["success"].append({
                        "id": str(promotion.id),
                        "name": promotion.name
                    })
                    
                except Promotion.DoesNotExist:
                    results["failed"].append({
                        "id": promotion_id,
                        "name": "Unknown",
                        "reason": "Promotion not found"
                    })
                except Exception as e:
                    results["failed"].append({
                        "id": promotion_id,
                        "name": getattr(promotion, "name", "Unknown"),
                        "reason": str(e)
                    })
        
        elif action == "pause":
            for promotion_id in promotion_ids:
                try:
                    promotion = Promotion.objects.get(id=promotion_id)
                    
                    if promotion.status != Promotion.STATUS_ACTIVE:
                        results["failed"].append({
                            "id": promotion_id,
                            "name": promotion.name,
                            "reason": f"Cannot pause - current status: {promotion.status}"
                        })
                        continue
                    
                    promotion.status = Promotion.STATUS_PAUSED
                    promotion.save()
                    results["success"].append({
                        "id": str(promotion.id),
                        "name": promotion.name
                    })
                    
                except Promotion.DoesNotExist:
                    results["failed"].append({
                        "id": promotion_id,
                        "name": "Unknown",
                        "reason": "Promotion not found"
                    })
                except Exception as e:
                    results["failed"].append({
                        "id": promotion_id,
                        "name": getattr(promotion, "name", "Unknown"),
                        "reason": str(e)
                    })
        
        elif action == "delete":
            for promotion_id in promotion_ids:
                try:
                    promotion = Promotion.objects.get(id=promotion_id)
                    promotion_name = promotion.name
                    
                    # Only allow deletion of draft or ended promotions
                    if promotion.status not in [Promotion.STATUS_DRAFT, Promotion.STATUS_ENDED]:
                        results["failed"].append({
                            "id": promotion_id,
                            "name": promotion.name,
                            "reason": f"Cannot delete {promotion.status} promotion"
                        })
                        continue
                    
                    promotion.delete()
                    results["success"].append({
                        "id": promotion_id,
                        "name": promotion_name
                    })
                    
                except Promotion.DoesNotExist:
                    results["failed"].append({
                        "id": promotion_id,
                        "name": "Unknown",
                        "reason": "Promotion not found"
                    })
                except Exception as e:
                    results["failed"].append({
                        "id": promotion_id,
                        "name": getattr(promotion, "name", "Unknown"),
                        "reason": str(e)
                    })
        
        else:
            return None, {"action": f"Unknown action: {action}"}
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action_name,
            description=f"Bulk {action} completed: {len(results['success'])} succeeded, {len(results['failed'])} failed",
            status_code=200,
            user=user,
            app_name=APP_NAME,
            extra={
                "action": action,
                "total_promotions": len(promotion_ids),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "failed_reasons": list(set([f["reason"] for f in results["failed"]])),
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return results, None
    
    
    @staticmethod
    @transaction.atomic
    def update_promotion(
        promotion_id: str,
        data: Dict[str, Any],
        image_files: List = None,
        user: User = None
    ) -> Tuple[Optional[Promotion], Optional[Dict]]:
        """Update an existing promotion"""
        start_time = time.time()
        action = "promotion_update"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Updating promotion: {promotion_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"promotion_id": promotion_id, "name": data.get("name")}
        )
        
        try:
            promotion = Promotion.objects.get(id=promotion_id)
            
            # Only allow editing of draft or paused promotions
            if promotion.status not in [Promotion.STATUS_DRAFT, Promotion.STATUS_PAUSED]:
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Cannot edit {promotion.status} promotion: {promotion.name}",
                    status_code=400,
                    user=user,
                    app_name=APP_NAME,
                    extra={"promotion_id": promotion_id, "status": promotion.status}
                )
                return None, {"status": f"Cannot edit {promotion.status} promotion. Only draft or paused promotions can be edited."}

            # Resolve any new variants BEFORE mutating the promotion, so an
            # invalid variant_id fails cleanly without committing a partial edit.
            resolved_items = None
            if "items" in data:
                resolved_items = []
                for item_data in data["items"]:
                    variant = get_variant_by_id(item_data["variant_id"])
                    if not variant:
                        return None, {"items": f"Variant not found: {item_data['variant_id']}"}
                    resolved_items.append((variant, item_data))

            # Update slug if name changed
            if "name" in data and data["name"] != promotion.name:
                base_slug = slugify(data["name"])
                slug = base_slug
                counter = 1
                while Promotion.objects.filter(slug=slug).exclude(id=promotion.id).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                promotion.slug = slug
                promotion.name = data["name"]
            
            # Update other fields
            if "description" in data:
                promotion.description = data["description"]
            
            if "bundle_price" in data:
                promotion.bundle_price = Decimal(str(data["bundle_price"]))
            
            if "starts_at" in data:
                starts_at = data["starts_at"]
                if isinstance(starts_at, str):
                    from dateutil import parser
                    starts_at = parser.parse(starts_at)
                if timezone.is_naive(starts_at):
                    starts_at = timezone.make_aware(starts_at)
                promotion.starts_at = starts_at
            
            if "ends_at" in data:
                ends_at = data.get("ends_at")
                if ends_at:
                    if isinstance(ends_at, str):
                        from dateutil import parser
                        ends_at = parser.parse(ends_at)
                    if timezone.is_naive(ends_at):
                        ends_at = timezone.make_aware(ends_at)
                promotion.ends_at = ends_at
            
            if "meta_title" in data:
                promotion.meta_title = data["meta_title"]
            
            if "meta_description" in data:
                promotion.meta_description = data["meta_description"]
            
            promotion.save()
            
            # Update items - remove existing and add new (variants pre-resolved)
            if resolved_items is not None:
                # Delete existing items, then create the new set
                promotion.items.all().delete()
                for variant, item_data in resolved_items:
                    PromotionItem.objects.create(
                        promotion=promotion,
                        variant=variant,
                        quantity=item_data["quantity"],
                        original_price=variant.price,
                        cost_price_snapshot=variant.cost_price,
                        is_free=item_data.get("is_free", False),
                        is_available=variant.stock >= item_data["quantity"],
                    )
            
            # Handle images
            # Keep specified images
            keep_image_ids = data.get("keep_image_ids", [])
            if keep_image_ids:
                promotion.images.exclude(id__in=keep_image_ids).delete()
            else:
                # If no keep_image_ids, delete all existing images
                promotion.images.all().delete()
            
            # Add new images
            if image_files:
                for i, image_file in enumerate(image_files):
                    # Get the current count of images after deletion
                    current_count = promotion.images.count()
                    image_type = "banner" if current_count == 0 and i == 0 else "gallery"
                    PromotionImage.objects.create(
                        promotion=promotion,
                        image=image_file,
                        image_type=image_type,
                        order=current_count + i,
                        is_active=True,
                    )
            
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Promotion updated: {promotion.name}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "promotion_id": str(promotion.id),
                    "name": promotion.name,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return promotion, None
            
        except Promotion.DoesNotExist:
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"Promotion not found: {promotion_id}",
                status_code=404,
                user=user,
                app_name=APP_NAME,
                extra={"promotion_id": promotion_id}
            )
            return None, {"promotion": "Promotion not found"}
        except Exception as e:
            # See create_promotion: discard any partial write on unexpected error.
            transaction.set_rollback(True)
            logger.exception("Failed to update promotion")
            return None, {"general": "Failed to update promotion. Please try again."}


class DiscountCodeService:
    """Validation and commission lifecycle for checkout discount codes."""

    DEFAULT_AFFILIATE_DISCOUNT_TYPE = getattr(
        settings, "AFFILIATE_CODE_DISCOUNT_TYPE", DiscountCode.TYPE_PERCENTAGE
    )
    DEFAULT_AFFILIATE_DISCOUNT_VALUE = Decimal(
        str(getattr(settings, "AFFILIATE_CODE_DISCOUNT_VALUE", "5.00"))
    )

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    @transaction.atomic
    def ensure_affiliate_discount_code(
        cls,
        affiliate: Affiliate,
        created_by: User = None,
    ) -> DiscountCode:
        """Legacy helper for generating an affiliate-linked discount code."""
        defaults = {
            "code": "",
            "name": f"{affiliate.user.full_name or affiliate.user.email} referral code",
            "description": "Affiliate referral discount code",
            "discount_type": cls.DEFAULT_AFFILIATE_DISCOUNT_TYPE,
            "value": cls.DEFAULT_AFFILIATE_DISCOUNT_VALUE,
            "affiliate": affiliate,
            "created_by": created_by,
            "is_active": True,
        }
        base_code = f"AFF-{affiliate.referral_code}"
        code = base_code
        counter = 1
        while DiscountCode.objects.exclude(affiliate=affiliate).filter(code=code).exists():
            counter += 1
            code = f"{base_code}-{counter}"
        defaults["code"] = code

        discount_code = DiscountCode.objects.filter(affiliate=affiliate).order_by("created_at").first()
        created = False
        if discount_code is None:
            discount_code = DiscountCode.objects.create(**defaults)
            created = True

        updated_fields = []
        if discount_code.affiliate_id != affiliate.id:
            discount_code.affiliate = affiliate
            updated_fields.append("affiliate")
        if discount_code.code != code:
            discount_code.code = code
            updated_fields.append("code")
        if discount_code.name != defaults["name"]:
            discount_code.name = defaults["name"]
            updated_fields.append("name")
        if created_by and discount_code.created_by_id is None:
            discount_code.created_by = created_by
            updated_fields.append("created_by")
        if not discount_code.is_active and affiliate.is_active and affiliate.is_approved:
            discount_code.is_active = True
            updated_fields.append("is_active")

        if updated_fields:
            discount_code.save(update_fields=updated_fields)

        return discount_code

    @classmethod
    def _get_discount_code(
        cls,
        code: str,
    ) -> Tuple[Optional[DiscountCode], Optional[Affiliate], bool]:
        normalized_code = (code or "").strip().upper()
        if not normalized_code:
            return None, None, False

        discount_code = (
            DiscountCode.objects.select_related("affiliate", "affiliate__user")
            .filter(code=normalized_code)
            .first()
        )
        if discount_code:
            return discount_code, discount_code.affiliate, False

        affiliate = (
            Affiliate.objects.select_related("user")
            .prefetch_related("discount_codes")
            .filter(referral_code=normalized_code)
            .first()
        )
        if not affiliate:
            return None, None, False

        discount_code = affiliate.discount_codes.order_by("created_at").first()
        if not discount_code:
            return None, affiliate, True

        return discount_code, affiliate, True

    @classmethod
    def validate_discount_code(
        cls,
        code: str,
        subtotal: Decimal,
        items: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[Optional[DiscountCode], Optional[Dict[str, Any]], Optional[Dict[str, str]]]:
        """Validate a code and compute the discount/commission snapshots.

        `items` (order_items_data dicts with variant/quantity/unit_price) is
        required to compute profit-based commissions; without it the
        sale-amount basis is used as a fallback.
        """
        normalized_code = (code or "").strip().upper()
        subtotal = cls._money(subtotal)

        if not normalized_code:
            return None, None, {"discount_code": "Discount code is required"}

        discount_code, resolved_affiliate, resolved_from_referral_code = cls._get_discount_code(
            normalized_code
        )
        if not discount_code:
            if resolved_from_referral_code and resolved_affiliate:
                return None, None, {
                    "discount_code": "Affiliate reference code is not linked to a discount code"
                }
            return None, None, {"discount_code": "Discount code not found"}

        if not discount_code.is_currently_active:
            return None, None, {"discount_code": "Discount code is not active"}

        if subtotal < discount_code.min_subtotal:
            return None, None, {
                "discount_code": (
                    f"This code requires a minimum subtotal of {discount_code.min_subtotal}"
                )
            }

        if discount_code.discount_type == DiscountCode.TYPE_PERCENTAGE:
            discount_amount = subtotal * (discount_code.value / Decimal("100"))
        else:
            discount_amount = discount_code.value

        if discount_code.max_discount_amount is not None:
            discount_amount = min(discount_amount, discount_code.max_discount_amount)

        discount_amount = min(cls._money(discount_amount), subtotal)

        if discount_amount <= Decimal("0.00"):
            return None, None, {"discount_code": "Discount code does not apply to this order"}

        affiliate = resolved_affiliate or discount_code.affiliate
        commissionable_amount = subtotal
        commission_amount = Decimal("0.00")
        commission_rate = Decimal("0.00")

        if affiliate:
            from apps.users.models import Affiliate

            if affiliate.commission_basis == Affiliate.BASIS_PROFIT and items:
                # Profit after discount: what the store actually made on the
                # order once the affiliate's discount came out of the margin.
                gross_margin = sum(
                    (
                        (item["unit_price"] - item["variant"].cost_price)
                        * Decimal(str(item["quantity"]))
                        for item in items
                        if item.get("variant")
                    ),
                    Decimal("0.00"),
                )
                commissionable_amount = gross_margin - discount_amount
            else:
                commission_base = getattr(
                    settings,
                    "AFFILIATE_COMMISSION_BASE",
                    "discounted_subtotal",
                )
                if commission_base == "original_subtotal":
                    commissionable_amount = subtotal
                else:
                    commissionable_amount = subtotal - discount_amount

            commissionable_amount = max(cls._money(commissionable_amount), Decimal("0.00"))
            commission_rate = Decimal(str(affiliate.commission_rate))
            commission_amount = cls._money(
                commissionable_amount * (commission_rate / Decimal("100"))
            )

        details = {
            "entered_code": normalized_code,
            "code": discount_code.code,
            "name": discount_code.name,
            "discount_type": discount_code.discount_type,
            "discount_value": float(discount_code.value),
            "discount_amount": discount_amount,
            "subtotal_after_discount": cls._money(subtotal - discount_amount),
            "affiliate_id": str(affiliate.id) if affiliate else None,
            "is_affiliate_code": bool(affiliate),
            "resolved_from_referral_code": resolved_from_referral_code,
            "affiliate_referral_code": affiliate.referral_code if affiliate else None,
            "commission_rate": commission_rate,
            "commissionable_amount": commissionable_amount,
            "commission_amount": commission_amount,
        }
        return discount_code, details, None

    @classmethod
    @transaction.atomic
    def register_order_discount(
        cls,
        order,
        discount_code: Optional[DiscountCode],
        discount_details: Optional[Dict[str, Any]],
    ) -> None:
        """Persist discount/affiliate attribution and commission records."""
        if not discount_code or not discount_details:
            return

        order.discount_code = discount_code
        order.discount_code_text = discount_code.code
        order.entered_discount_code_text = discount_details.get("entered_code", discount_code.code)
        order.affiliate = discount_code.affiliate
        order.affiliate_commission_amount = discount_details["commission_amount"]
        order.save(
            update_fields=[
                "discount_code",
                "discount_code_text",
                "entered_discount_code_text",
                "affiliate",
                "affiliate_commission_amount",
                "updated_at",
            ]
        )

        if not discount_code.affiliate or discount_details["commission_amount"] <= Decimal("0.00"):
            return

        AffiliateCommission.objects.update_or_create(
            order=order,
            defaults={
                "affiliate": discount_code.affiliate,
                "discount_code": discount_code,
                "commission_rate": discount_details["commission_rate"],
                "commissionable_amount": discount_details["commissionable_amount"],
                "commission_amount": discount_details["commission_amount"],
                "status": AffiliateCommission.STATUS_PENDING,
            },
        )

    @classmethod
    def _order_is_commission_eligible(cls, order) -> bool:
        if not order.affiliate_id or order.affiliate_commission_amount <= Decimal("0.00"):
            return False

        if order.payment_method in ("pod", "cash_on_delivery"):
            return order.status in (order.STATUS_DELIVERED, order.STATUS_COMPLETED)

        return order.payment_status == order.PAYMENT_PAID

    @classmethod
    def _order_should_reverse_commission(cls, order) -> bool:
        return (
            order.status in {order.STATUS_CANCELLED, order.STATUS_REFUNDED}
            or order.payment_status in {order.PAYMENT_FAILED, order.PAYMENT_REFUNDED}
        )

    @classmethod
    def _append_commission_note(cls, commission_pk, reason: str) -> None:
        if not reason:
            return
        commission = AffiliateCommission.objects.get(pk=commission_pk)
        commission.notes = f"{commission.notes}\n{reason}".strip()
        commission.save(update_fields=["notes", "updated_at"])

    @classmethod
    @transaction.atomic
    def sync_order_commission(cls, order, reason: str = "") -> None:
        """Move an order commission between pending, accrued, and reversed.

        Concurrency-safe: the payment webhook and the browser payment callback
        routinely fire near-simultaneously, so the status flips below are
        conditional UPDATEs — only the caller whose UPDATE actually matched
        touches the affiliate's earnings. Row locks narrow the race window on
        PostgreSQL; on SQLite (tests) select_for_update is a no-op and the
        conditional UPDATEs alone provide the guarantee.
        """
        if not order.affiliate_id:
            return

        commission = (
            AffiliateCommission.objects.select_for_update()
            .select_related("affiliate")
            .filter(order=order)
            .first()
        )
        if commission is None:
            return
        affiliate = Affiliate.objects.select_for_update().get(pk=commission.affiliate_id)

        now = timezone.now()

        if cls._order_should_reverse_commission(order):
            # Reverse an accrued commission (and claw back the earnings)…
            updated = AffiliateCommission.objects.filter(
                pk=commission.pk, status=AffiliateCommission.STATUS_ACCRUED
            ).update(status=AffiliateCommission.STATUS_REVERSED, reversed_at=now, updated_at=now)
            if updated:
                affiliate.reverse_earnings(commission.commission_amount)
                cls._append_commission_note(commission.pk, reason)
                return
            # …or flip a still-pending one (no earnings were ever added).
            updated = AffiliateCommission.objects.filter(
                pk=commission.pk, status=AffiliateCommission.STATUS_PENDING
            ).update(status=AffiliateCommission.STATUS_REVERSED, reversed_at=now, updated_at=now)
            if updated:
                cls._append_commission_note(commission.pk, reason)
            return

        if cls._order_is_commission_eligible(order):
            # PENDING → ACCRUED, and also REVERSED → ACCRUED: a commission
            # reversed on a failed payment must recover when the customer
            # retries and pays (this branch is unreachable while the order is
            # cancelled/refunded/failed).
            updated = AffiliateCommission.objects.filter(
                pk=commission.pk,
                status__in=[
                    AffiliateCommission.STATUS_PENDING,
                    AffiliateCommission.STATUS_REVERSED,
                ],
            ).update(
                status=AffiliateCommission.STATUS_ACCRUED,
                accrued_at=now,
                reversed_at=None,
                updated_at=now,
            )
            if updated:
                affiliate.add_earnings(commission.commission_amount)
                cls._append_commission_note(commission.pk, reason)

    @classmethod
    @transaction.atomic
    def create_discount_code(cls, data: Dict[str, Any], user: User) -> Tuple[Optional[DiscountCode], Optional[Dict]]:
        try:
            if DiscountCode.objects.filter(code=data["code"]).exists():
                return None, {"code": "Discount code already exists"}
            if Affiliate.objects.filter(referral_code=data["code"]).exists():
                return None, {"code": "Code is already used as an affiliate reference"}

            discount_code = DiscountCode.objects.create(
                code=data["code"],
                name=data["name"],
                description=data.get("description", ""),
                discount_type=data["discount_type"],
                value=data["value"],
                min_subtotal=data.get("min_subtotal", Decimal("0.00")),
                max_discount_amount=data.get("max_discount_amount"),
                starts_at=data.get("starts_at"),
                ends_at=data.get("ends_at"),
                is_active=data.get("is_active", True),
                created_by=user,
            )
            return discount_code, None
        except Exception as e:
            transaction.set_rollback(True)
            logger.error(f"Create discount code error: {str(e)}")
            return None, {"general": "Failed to create discount code"}

    @classmethod
    @transaction.atomic
    def update_discount_code(
        cls,
        discount_code: DiscountCode,
        data: Dict[str, Any],
    ) -> Tuple[Optional[DiscountCode], Optional[Dict]]:
        try:
            if discount_code.affiliate_id and "code" in data and data["code"] != discount_code.code:
                return None, {"code": "Affiliate-linked code cannot be renamed"}
            if "code" in data and data["code"] != discount_code.code:
                if DiscountCode.objects.exclude(id=discount_code.id).filter(code=data["code"]).exists():
                    return None, {"code": "Discount code already exists"}
                if Affiliate.objects.filter(referral_code=data["code"]).exists():
                    return None, {"code": "Code is already used as an affiliate reference"}

            for field in (
                "code",
                "name",
                "description",
                "discount_type",
                "value",
                "min_subtotal",
                "max_discount_amount",
                "starts_at",
                "ends_at",
                "is_active",
            ):
                if field in data:
                    setattr(discount_code, field, data[field])

            discount_code.save()
            return discount_code, None
        except Exception as e:
            transaction.set_rollback(True)
            logger.error(f"Update discount code error: {str(e)}")
            return None, {"general": "Failed to update discount code"}

    @classmethod
    @transaction.atomic
    def assign_discount_code_to_affiliate(
        cls,
        discount_code: DiscountCode,
        affiliate: Affiliate,
    ) -> Tuple[Optional[DiscountCode], Optional[Dict]]:
        try:
            if discount_code.affiliate_id and discount_code.affiliate_id != affiliate.id:
                return None, {"discount_code_id": "Discount code is already assigned to another affiliate"}

            discount_code.affiliate = affiliate
            if affiliate.is_active and affiliate.is_approved:
                discount_code.is_active = True
            discount_code.save(update_fields=["affiliate", "is_active", "updated_at"])
            return discount_code, None
        except Exception as e:
            transaction.set_rollback(True)
            logger.error(f"Assign discount code to affiliate error: {str(e)}")
            return None, {"general": "Failed to assign discount code"}

    @classmethod
    @transaction.atomic
    def toggle_discount_code_status(
        cls,
        discount_code: DiscountCode,
        is_active: bool,
    ) -> Tuple[Optional[DiscountCode], Optional[Dict]]:
        try:
            discount_code.is_active = is_active
            discount_code.save(update_fields=["is_active", "updated_at"])
            return discount_code, None
        except Exception as e:
            transaction.set_rollback(True)
            logger.error(f"Toggle discount code status error: {str(e)}")
            return None, {"general": "Failed to update discount code status"}
