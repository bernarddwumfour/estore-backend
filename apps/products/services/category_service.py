"""
Category Service - Business logic for category management
"""

import logging
import time
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction
from django.utils.text import slugify

from apps.products.models import Category
from apps.products.selectors import get_category_by_id
from apps.users.models import User
from apps.common.logging import log_action, LogSeverity, get_user_info

logger = logging.getLogger(__name__)

# App name constant for filtering in UI
APP_NAME = "products"


class CategoryService:
    """Category management business logic"""

    @staticmethod
    @transaction.atomic
    def create_category(
        name: str,
        description: str = "",
        parent_id: str = None,
        is_active: bool = True,
        is_hidden: bool = False,
        meta_title: str = "",
        meta_description: str = "",
        image_file=None,
        user: User = None,
    ) -> Tuple[Optional[Category], Optional[Dict]]:
        """Create a new category"""
        start_time = time.time()
        action = "category_create"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating new category: {name}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "category_name": name,
                "is_hidden": is_hidden,
                "is_active": is_active,
                "has_parent": bool(parent_id and parent_id not in ["null", "none"]),
                "has_image": bool(image_file)
            }
        )
        
        try:
            # Generate unique slug
            base_slug = slugify(name)
            slug = base_slug
            counter = 1
            while Category.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            # Get parent if provided
            parent = None
            if parent_id and parent_id != "null" and parent_id != "none":
                parent = get_category_by_id(parent_id, is_admin=True)
                if not parent:
                    duration_ms = (time.time() - start_time) * 1000
                    log_action(
                        logger=logger,
                        severity=LogSeverity.WARNING,
                        action=action,
                        description=f"Parent category not found: {parent_id}",
                        status_code=400,
                        user=user,
                        app_name=APP_NAME,
                        extra={
                            "category_name": name,
                            "parent_id": parent_id,
                            "duration_ms": round(duration_ms, 2)
                        }
                    )
                    return None, {"parent_id": "Parent category not found"}

            # Create category
            category = Category.objects.create(
                name=name,
                slug=slug,
                description=description,
                parent=parent,
                is_active=is_active,
                is_hidden=is_hidden,
                meta_title=meta_title,
                meta_description=meta_description,
            )

            # Handle image upload
            if image_file:
                category.image.save(image_file.name, image_file, save=True)
                has_image = True
            else:
                has_image = False

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Category created successfully: {category.name}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_id": str(category.id),
                    "category_name": category.name,
                    "category_slug": category.slug,
                    "parent_id": str(parent.id) if parent else None,
                    "is_active": category.is_active,
                    "is_hidden": category.is_hidden,
                    "has_image": has_image,
                    "slug_generation_attempts": counter,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )

            return category, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to create category: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_name": name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return None, {"general": f"Failed to create category: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def update_category(
        category_id: str,
        data: Dict[str, Any],
        image_file=None,
        remove_image: bool = False,
        user: User = None,
    ) -> Tuple[Optional[Category], Optional[Dict]]:
        """Update an existing category"""
        start_time = time.time()
        action = "category_update"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Updating category ID: {category_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "category_id": category_id,
                "update_fields": list(data.keys()),
                "has_image_update": bool(image_file),
                "remove_image": remove_image
            }
        )
        
        try:
            category = get_category_by_id(category_id, is_admin=True)
            if not category:
                duration_ms = (time.time() - start_time) * 1000
                log_action(
                    logger=logger,
                    severity=LogSeverity.WARNING,
                    action=action,
                    description=f"Category not found: {category_id}",
                    status_code=404,
                    user=user,
                    app_name=APP_NAME,
                    extra={
                        "category_id": category_id,
                        "duration_ms": round(duration_ms, 2)
                    }
                )
                return None, {"category": "Category not found"}

            old_name = category.name
            old_parent_id = str(category.parent_id) if category.parent_id else None
            old_is_active = category.is_active
            old_is_hidden = category.is_hidden

            # Update name and slug
            if "name" in data and data["name"] != category.name:
                category.name = data["name"]
                base_slug = slugify(data["name"])
                slug = base_slug
                counter = 1
                while (
                    Category.objects.filter(slug=slug).exclude(id=category.id).exists()
                ):
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                category.slug = slug
                slug_updated = True
                slug_attempts = counter
            else:
                slug_updated = False
                slug_attempts = 0

            # Update parent
            if "parent_id" in data:
                if (
                    data["parent_id"] is None
                    or data["parent_id"] == "null"
                    or data["parent_id"] == "none"
                ):
                    category.parent = None
                    new_parent_id = None
                else:
                    parent = get_category_by_id(data["parent_id"], is_admin=True)
                    if not parent:
                        duration_ms = (time.time() - start_time) * 1000
                        log_action(
                            logger=logger,
                            severity=LogSeverity.WARNING,
                            action=action,
                            description=f"Parent category not found: {data['parent_id']}",
                            status_code=400,
                            user=user,
                            app_name=APP_NAME,
                            extra={
                                "category_id": category_id,
                                "parent_id": data['parent_id'],
                                "duration_ms": round(duration_ms, 2)
                            }
                        )
                        return None, {"parent_id": "Parent category not found"}
                    if parent.id == category.id:
                        duration_ms = (time.time() - start_time) * 1000
                        log_action(
                            logger=logger,
                            severity=LogSeverity.WARNING,
                            action=action,
                            description="Category cannot be its own parent",
                            status_code=400,
                            user=user,
                            app_name=APP_NAME,
                            extra={
                                "category_id": category_id,
                                "parent_id": data['parent_id'],
                                "duration_ms": round(duration_ms, 2)
                            }
                        )
                        return None, {"parent_id": "Category cannot be its own parent"}
                    category.parent = parent
                    new_parent_id = str(parent.id)
            else:
                new_parent_id = str(category.parent_id) if category.parent_id else None

            # Update other fields
            for field in [
                "description",
                "is_active",
                "is_hidden",
                "meta_title",
                "meta_description",
            ]:
                if field in data:
                    setattr(category, field, data[field])

            category.save()

            # Handle image
            image_updated = False
            if remove_image and category.image:
                category.image.delete(save=False)
                category.image = None
                category.save()
                image_updated = True
                image_action = "removed"
            elif image_file:
                if category.image:
                    category.image.delete(save=False)
                category.image.save(image_file.name, image_file, save=True)
                image_updated = True
                image_action = "uploaded"

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Category updated successfully: {category.name}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_id": str(category.id),
                    "category_name": category.name,
                    "old_name": old_name,
                    "slug_updated": slug_updated,
                    "slug_attempts": slug_attempts,
                    "old_parent_id": old_parent_id,
                    "new_parent_id": new_parent_id,
                    "old_is_active": old_is_active,
                    "new_is_active": category.is_active,
                    "old_is_hidden": old_is_hidden,
                    "new_is_hidden": category.is_hidden,
                    "image_updated": image_updated,
                    "image_action": image_action if image_updated else None,
                    "updated_fields": list(data.keys()),
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )

            return category, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to update category {category_id}: {str(e)}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_id": category_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user)
                }
            )
            return None, {"general": f"Failed to update category: {str(e)}"}

    @staticmethod
    @transaction.atomic
    def bulk_action_categories(
        category_ids: List[str], action: str, user: User = None
    ) -> Tuple[Dict, Optional[Dict]]:
        """
        Perform bulk actions on categories

        Returns:
            Tuple of (results dict, error dict)
            results: {
                'success': [{'id': str, 'name': str}],
                'failed': [{'id': str, 'name': str, 'reason': str}],
                'total': int
            }
        """
        start_time = time.time()
        action_name = f"bulk_category_{action}"
        
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action_name,
            description=f"Starting bulk {action} action on {len(category_ids)} categories",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={
                "action": action,
                "total_categories": len(category_ids),
                "category_ids": category_ids[:10]  # Log first 10 IDs only
            }
        )
        
        from apps.products.models import Product

        results = {"success": [], "failed": [], "total": len(category_ids)}

        if action == "delete":
            for category_id in category_ids:
                try:
                    category = Category.objects.get(id=category_id)

                    # Check for subcategories
                    subcategory_count = category.children.count()
                    if subcategory_count > 0:
                        results["failed"].append({
                            "id": category_id,
                            "name": category.name,
                            "reason": f"Has {subcategory_count} subcategories",
                        })
                        continue

                    # Check for products
                    product_count = Product.objects.filter(category=category).count()
                    if product_count > 0:
                        results["failed"].append({
                            "id": category_id,
                            "name": category.name,
                            "reason": f"Has {product_count} products",
                        })
                        continue

                    category_name = category.name
                    category.delete()
                    results["success"].append({
                        "id": category_id,
                        "name": category_name
                    })

                except Category.DoesNotExist:
                    results["failed"].append({
                        "id": category_id,
                        "name": "Unknown",
                        "reason": "Not found",
                    })
                except Exception as e:
                    results["failed"].append({
                        "id": category_id,
                        "name": getattr(category, "name", "Unknown"),
                        "reason": str(e),
                    })

        elif action in ["activate", "deactivate", "hide", "unhide"]:
            for category_id in category_ids:
                try:
                    category = Category.objects.get(id=category_id)
                    # old_state = {
                    #     "is_active": category.is_active,
                    #     "is_hidden": category.is_hidden
                    # }

                    if action == "activate":
                        category.is_active = True
                    elif action == "deactivate":
                        category.is_active = False
                    elif action == "hide":
                        category.is_hidden = True
                    elif action == "unhide":
                        category.is_hidden = False

                    category.save()
                    results["success"].append({
                        "id": category_id,
                        "name": category.name
                    })

                except Category.DoesNotExist:
                    results["failed"].append({
                        "id": category_id,
                        "name": "Unknown",
                        "reason": "Not found",
                    })
                except Exception as e:
                    results["failed"].append({
                        "id": category_id,
                        "name": getattr(category, "name", "Unknown"),
                        "reason": str(e),
                    })

        else:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action_name,
                description=f"Unknown bulk action: {action}",
                status_code=400,
                user=user,
                app_name=APP_NAME,
                extra={
                    "action": action,
                    "duration_ms": round(duration_ms, 2)
                }
            )
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
                "total_categories": len(category_ids),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "failed_reasons": list(set([f["reason"] for f in results["failed"]])),
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )

        return results, None