"""
Blog Category Service — business logic for blog category management.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.utils.text import slugify

from apps.blog.models import BlogCategory
from apps.common.logging import LogSeverity, get_user_info, log_action

logger = logging.getLogger(__name__)
APP_NAME = "blog"


class BlogCategoryService:
    """Blog category management business logic."""

    @staticmethod
    @transaction.atomic
    def create_category(
        name: str,
        description: str = "",
        is_active: bool = True,
        user=None,
    ) -> Tuple[Optional[BlogCategory], Optional[Dict]]:
        """Create a new blog category."""
        start_time = time.time()
        action = "blog_category_create"

        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating blog category: {name}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"category_name": name},
        )

        try:
            # Unique slug
            base_slug = slugify(name)
            slug = base_slug
            counter = 1
            while BlogCategory.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1

            category = BlogCategory.objects.create(
                name=name,
                slug=slug,
                description=description,
                is_active=is_active,
            )

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Blog category created: {category.name}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_id": str(category.id),
                    "category_name": category.name,
                    "slug": category.slug,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user),
                },
            )
            return category, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to create blog category: {e}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_name": name,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return None, {"general": f"Failed to create category: {e}"}

    @staticmethod
    @transaction.atomic
    def update_category(
        category_id: str,
        data: Dict,
        user=None,
    ) -> Tuple[Optional[BlogCategory], Optional[Dict]]:
        """Update an existing blog category."""
        start_time = time.time()
        action = "blog_category_update"

        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Updating blog category: {category_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"category_id": category_id, "update_fields": list(data.keys())},
        )

        try:
            from apps.blog.selectors import get_category_by_id

            category = get_category_by_id(category_id)
            if not category:
                return None, {"category": "Category not found"}

            old_name = category.name

            if "name" in data and data["name"] != category.name:
                category.name = data["name"]
                base_slug = slugify(data["name"])
                slug = base_slug
                counter = 1
                while (
                    BlogCategory.objects.filter(slug=slug)
                    .exclude(id=category.id)
                    .exists()
                ):
                    slug = f"{base_slug}-{counter}"
                    counter += 1
                category.slug = slug

            for field in ("description", "is_active"):
                if field in data:
                    setattr(category, field, data[field])

            category.save()

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Blog category updated: {category.name}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_id": str(category.id),
                    "category_name": category.name,
                    "old_name": old_name,
                    "updated_fields": list(data.keys()),
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user),
                },
            )
            return category, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to update blog category: {e}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_id": category_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return None, {"general": f"Failed to update category: {e}"}

    @staticmethod
    @transaction.atomic
    def delete_category(category_id: str, user=None) -> Tuple[bool, Optional[Dict]]:
        """Delete a blog category."""
        start_time = time.time()
        action = "blog_category_delete"

        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Deleting blog category: {category_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"category_id": category_id},
        )

        try:
            from apps.blog.selectors import get_category_by_id

            category = get_category_by_id(category_id)
            if not category:
                return False, {"category": "Category not found"}

            # Guard: don't delete categories that have posts
            post_count = category.posts.count()
            if post_count > 0:
                return False, {"category": f"Cannot delete category with {post_count} posts"}

            category_name = category.name
            category.delete()

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Blog category deleted: {category_name}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_id": category_id,
                    "category_name": category_name,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user),
                },
            )
            return True, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to delete blog category: {e}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "category_id": category_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return False, {"general": f"Failed to delete category: {e}"}
