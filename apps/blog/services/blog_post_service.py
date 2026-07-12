"""
Blog Post Service — business logic for blog post CRUD and bulk actions.
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.blog.models import BlogPost
from apps.common.logging import LogSeverity, get_user_info, log_action

logger = logging.getLogger(__name__)
APP_NAME = "blog"


class BlogPostService:
    """Blog post management business logic."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def create_post(data: Dict, user=None) -> Tuple[Optional[BlogPost], Optional[Dict]]:
        """Create a new blog post."""
        start_time = time.time()
        action = "blog_post_create"

        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Creating blog post: {data.get('title', '')}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"title": data.get("title", "")},
        )

        try:
            from apps.blog.models import BlogCategory

            title = data["title"]
            content = data["content"]

            # Slug
            slug = data.get("slug")
            if not slug:
                base_slug = slugify(title)
                slug = base_slug
                counter = 1
                while BlogPost.objects.filter(slug=slug).exists():
                    slug = f"{base_slug}-{counter}"
                    counter += 1

            # Category
            category = None
            if data.get("category_id"):
                try:
                    category = BlogCategory.objects.get(id=data["category_id"])
                except BlogCategory.DoesNotExist:
                    return None, {"category_id": "Category not found"}

            # Author
            author_user_id = data.get("author_user_id")
            author_name = data.get("author_name", "")

            status = data.get("status", BlogPost.STATUS_DRAFT)
            published_at = None
            if status == BlogPost.STATUS_PUBLISHED:
                published_at = timezone.now()

            post = BlogPost.objects.create(
                title=title,
                slug=slug,
                excerpt=data.get("excerpt", ""),
                content=content,
                cover_image_url=data.get("cover_image_url", ""),
                category=category,
                author_user_id=author_user_id,
                author_name=author_name,
                status=status,
                published_at=published_at,
                is_featured=data.get("is_featured", False),
                meta_title=data.get("meta_title", ""),
                meta_description=data.get("meta_description", ""),
            )

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Blog post created: {post.title}",
                status_code=201,
                user=user,
                app_name=APP_NAME,
                extra={
                    "post_id": str(post.id),
                    "title": post.title,
                    "slug": post.slug,
                    "status": post.status,
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user),
                },
            )
            return post, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to create blog post: {e}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return None, {"general": f"Failed to create post: {e}"}

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def update_post(post_id: str, data: Dict, user=None) -> Tuple[Optional[BlogPost], Optional[Dict]]:
        """Update an existing blog post."""
        start_time = time.time()
        action = "blog_post_update"

        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Updating blog post: {post_id}",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"post_id": post_id, "update_fields": list(data.keys())},
        )

        try:
            from apps.blog.selectors import get_post_by_id
            from apps.blog.models import BlogCategory

            post = get_post_by_id(post_id, admin=True)
            if not post:
                return None, {"post": "Post not found"}

            old_title = post.title
            old_status = post.status

            if "title" in data:
                post.title = data["title"]
                if "slug" not in data:
                    base_slug = slugify(data["title"])
                    slug = base_slug
                    counter = 1
                    while (
                        BlogPost.objects.filter(slug=slug)
                        .exclude(id=post.id)
                        .exists()
                    ):
                        slug = f"{base_slug}-{counter}"
                        counter += 1
                    post.slug = slug

            if "slug" in data and data["slug"]:
                post.slug = data["slug"]

            if "content" in data:
                post.content = data["content"]
            if "excerpt" in data:
                post.excerpt = data.get("excerpt", "")
            if "cover_image_url" in data:
                post.cover_image_url = data.get("cover_image_url", "")

            if "category_id" in data:
                cat_id = data["category_id"]
                if cat_id is None:
                    post.category = None
                else:
                    try:
                        post.category = BlogCategory.objects.get(id=cat_id)
                    except BlogCategory.DoesNotExist:
                        return None, {"category_id": "Category not found"}

            if "author_user_id" in data:
                post.author_user_id = data["author_user_id"]
            if "author_name" in data:
                post.author_name = data.get("author_name", "")

            if not post.author_user_id and not (post.author_name or "").strip():
                return None, {"author": "Either author_user_id or author_name is required"}

            if "status" in data:
                new_status = data["status"]
                if new_status == BlogPost.STATUS_PUBLISHED and not post.published_at:
                    post.published_at = timezone.now()
                post.status = new_status

            for field in ("is_featured", "meta_title", "meta_description"):
                if field in data:
                    setattr(post, field, data[field])

            post.save()

            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action=action,
                description=f"Blog post updated: {post.title}",
                status_code=200,
                user=user,
                app_name=APP_NAME,
                extra={
                    "post_id": str(post.id),
                    "title": post.title,
                    "old_title": old_title,
                    "old_status": old_status,
                    "new_status": post.status,
                    "updated_fields": list(data.keys()),
                    "duration_ms": round(duration_ms, 2),
                    "requested_by": get_user_info(user),
                },
            )
            return post, None

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.ERROR,
                action=action,
                description=f"Failed to update blog post: {e}",
                status_code=500,
                user=user,
                app_name=APP_NAME,
                extra={
                    "post_id": post_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return None, {"general": f"Failed to update post: {e}"}

    # ------------------------------------------------------------------
    # Publish / Archive / Delete
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def publish_post(post_id: str, user=None) -> Tuple[Optional[BlogPost], Optional[Dict]]:
        """Publish a blog post."""
        from apps.blog.selectors import get_post_by_id

        post = get_post_by_id(post_id, admin=True)
        if not post:
            return None, {"post": "Post not found"}

        post.status = BlogPost.STATUS_PUBLISHED
        if not post.published_at:
            post.published_at = timezone.now()
        post.save()

        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action="blog_post_publish",
            description=f"Blog post published: {post.title}",
            status_code=200,
            user=user,
            app_name=APP_NAME,
            extra={
                "post_id": str(post.id),
                "title": post.title,
                "requested_by": get_user_info(user),
            },
        )
        return post, None

    @staticmethod
    @transaction.atomic
    def archive_post(post_id: str, user=None) -> Tuple[Optional[BlogPost], Optional[Dict]]:
        """Archive a blog post."""
        from apps.blog.selectors import get_post_by_id

        post = get_post_by_id(post_id, admin=True)
        if not post:
            return None, {"post": "Post not found"}

        post.status = BlogPost.STATUS_ARCHIVED
        post.save()

        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action="blog_post_archive",
            description=f"Blog post archived: {post.title}",
            status_code=200,
            user=user,
            app_name=APP_NAME,
            extra={
                "post_id": str(post.id),
                "title": post.title,
                "requested_by": get_user_info(user),
            },
        )
        return post, None

    @staticmethod
    @transaction.atomic
    def delete_post(post_id: str, user=None) -> Tuple[bool, Optional[Dict]]:
        """Delete a blog post."""
        from apps.blog.selectors import get_post_by_id

        post = get_post_by_id(post_id, admin=True)
        if not post:
            return False, {"post": "Post not found"}

        post_title = post.title
        post.delete()

        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action="blog_post_delete",
            description=f"Blog post deleted: {post_title}",
            status_code=200,
            user=user,
            app_name=APP_NAME,
            extra={
                "post_id": post_id,
                "title": post_title,
                "requested_by": get_user_info(user),
            },
        )
        return True, None

    # ------------------------------------------------------------------
    # Bulk actions
    # ------------------------------------------------------------------

    @staticmethod
    @transaction.atomic
    def bulk_action_posts(
        post_ids: List[str], action: str, user=None
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Perform bulk actions on blog posts (publish / archive / delete)."""
        start_time = time.time()
        action_name = f"blog_post_bulk_{action}"

        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action_name,
            description=f"Bulk {action} on {len(post_ids)} posts",
            status_code=0,
            user=user,
            app_name=APP_NAME,
            extra={"action": action, "count": len(post_ids)},
        )

        results: Dict[str, List] = {"success": [], "failed": [], "total": len(post_ids)}

        for post_id in post_ids:
            try:
                post = BlogPost.objects.get(id=post_id)
                if action == "publish":
                    post.status = BlogPost.STATUS_PUBLISHED
                    if not post.published_at:
                        post.published_at = timezone.now()
                    post.save()
                elif action == "archive":
                    post.status = BlogPost.STATUS_ARCHIVED
                    post.save()
                elif action == "delete":
                    post.delete()
                    results["success"].append({"id": post_id, "title": post.title})
                    continue
                else:
                    results["failed"].append({"id": post_id, "title": post.title, "reason": f"Unknown action: {action}"})
                    continue

                results["success"].append({"id": post_id, "title": post.title})

            except BlogPost.DoesNotExist:
                results["failed"].append({"id": post_id, "title": "Unknown", "reason": "Not found"})
            except Exception as e:
                results["failed"].append({"id": post_id, "title": "Unknown", "reason": str(e)})

        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action_name,
            description=f"Bulk {action} done: {len(results['success'])} ok, {len(results['failed'])} failed",
            status_code=200,
            user=user,
            app_name=APP_NAME,
            extra={
                "action": action,
                "total": len(post_ids),
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user),
            },
        )
        return results, None
