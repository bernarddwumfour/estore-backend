"""
Category Service - Business logic for category management
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from django.db import transaction
from django.utils.text import slugify

from apps.products.models import Category
from apps.products.selectors import get_category_by_id
from apps.users.models import User

logger = logging.getLogger(__name__)


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

            if user:
                logger.info(f"Category created by admin {user.email}: {category.name}")

            return category, None

        except Exception as e:
            logger.error(f"Category creation error: {str(e)}")
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
        try:
            category = get_category_by_id(category_id, is_admin=True)
            if not category:
                return None, {"category": "Category not found"}

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

            # Update parent
            if "parent_id" in data:
                if (
                    data["parent_id"] is None
                    or data["parent_id"] == "null"
                    or data["parent_id"] == "none"
                ):
                    category.parent = None
                else:
                    parent = get_category_by_id(data["parent_id"], is_admin=True)
                    if not parent:
                        return None, {"parent_id": "Parent category not found"}
                    if parent.id == category.id:
                        return None, {"parent_id": "Category cannot be its own parent"}
                    category.parent = parent

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
            if remove_image and category.image:
                category.image.delete(save=False)
                category.image = None
                category.save()
            elif image_file:
                if category.image:
                    category.image.delete(save=False)
                category.image.save(image_file.name, image_file, save=True)

            if user:
                logger.info(f"Category updated by admin {user.email}: {category.name}")

            return category, None

        except Exception as e:
            logger.error(f"Category update error: {str(e)}")
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
        from apps.products.models import Product

        results = {"success": [], "failed": [], "total": len(category_ids)}

        if action == "delete":
            for category_id in category_ids:
                try:
                    category = Category.objects.get(id=category_id)

                    # Check for subcategories
                    if category.children.exists():
                        results["failed"].append(
                            {
                                "id": category_id,
                                "name": category.name,
                                "reason": "Has subcategories",
                            }
                        )
                        continue

                    # Check for products
                    if Product.objects.filter(category=category).exists():
                        results["failed"].append(
                            {
                                "id": category_id,
                                "name": category.name,
                                "reason": "Has products",
                            }
                        )
                        continue

                    category_name = category.name
                    category.delete()
                    results["success"].append(
                        {"id": category_id, "name": category_name}
                    )

                except Category.DoesNotExist:
                    results["failed"].append(
                        {"id": category_id, "name": "Unknown", "reason": "Not found"}
                    )
                except Exception as e:
                    results["failed"].append(
                        {
                            "id": category_id,
                            "name": getattr(category, "name", "Unknown"),
                            "reason": str(e),
                        }
                    )

        elif action in ["activate", "deactivate", "hide", "unhide"]:
            for category_id in category_ids:
                try:
                    category = Category.objects.get(id=category_id)

                    if action == "activate":
                        category.is_active = True
                    elif action == "deactivate":
                        category.is_active = False
                    elif action == "hide":
                        category.is_hidden = True
                    elif action == "unhide":
                        category.is_hidden = False

                    category.save()
                    results["success"].append(
                        {"id": category_id, "name": category.name}
                    )

                except Category.DoesNotExist:
                    results["failed"].append(
                        {"id": category_id, "name": "Unknown", "reason": "Not found"}
                    )
                except Exception as e:
                    results["failed"].append(
                        {
                            "id": category_id,
                            "name": getattr(category, "name", "Unknown"),
                            "reason": str(e),
                        }
                    )

        else:
            return None, {"action": f"Unknown action: {action}"}

        if user:
            logger.info(
                f"Bulk {action} action performed by {user.email}: {len(results['success'])} succeeded, {len(results['failed'])} failed"
            )

        return results, None