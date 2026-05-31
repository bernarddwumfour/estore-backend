"""
Promotion Service - Business logic for promotions
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction
from django.utils.text import slugify
from django.utils import timezone
from django.db.models import Q, F, Sum

from apps.promotions.models import Promotion, PromotionItem, PromotionImage
from apps.products.selectors import get_variant_by_id, get_product_by_id
from apps.products.models import ProductVariant
from apps.users.models import User
from apps.common.logging import log_action, LogSeverity, get_user_info
from decimal import Decimal

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
            
            # Create promotion items
            items_data = data.get("items", [])
            for item_data in items_data:
                variant = get_variant_by_id(item_data["variant_id"])
                if not variant:
                    raise ValueError(f"Variant not found: {item_data['variant_id']}")
                
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
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to create promotion: {str(e)}",
                status_code=500,
                user=user,
                request=None,
                app_name=APP_NAME,
                extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return None, {"general": f"Failed to create promotion: {str(e)}"}
        
        
        
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
            
            # Update items - remove existing and add new
            if "items" in data:
                # Delete existing items
                promotion.items.all().delete()
                
                # Create new items
                for item_data in data["items"]:
                    variant = get_variant_by_id(item_data["variant_id"])
                    if not variant:
                        raise ValueError(f"Variant not found: {item_data['variant_id']}")
                    
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
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to update promotion: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={"promotion_id": promotion_id, "error": str(e), "duration_ms": round(duration_ms, 2)}
            )
            return None, {"general": f"Failed to update promotion: {str(e)}"}