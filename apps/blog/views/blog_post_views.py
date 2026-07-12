"""
Blog Post Views — public + admin endpoints for blog posts.
"""

import json
import logging
import time

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.blog.schemas import serialize_post, serialize_post_list, serialize_bulk_action_result, validate_post, validate_bulk_action
from apps.blog.selectors import get_post_by_id, get_post_by_slug, list_posts
from apps.blog.services import BlogPostService
from apps.common.logging import LogSeverity, get_user_info, log_action
from apps.common.utils import sanitize_search_query
from apps.users.decorators.auth import jwt_required, json_request_required, role_required
from estore.utils.responses import APIResponse

logger = logging.getLogger(__name__)
APP_NAME = "blog"


def _log_request(request, action, start_time, status_code, extra=None):
    """Consistent request-level logging."""
    duration_ms = (time.time() - start_time) * 1000
    user = request.user if hasattr(request, "user") else None
    log_data = {
        "duration_ms": round(duration_ms, 2),
        "path": request.path,
        "method": request.method,
    }
    if extra:
        log_data.update(extra)

    if status_code < 400:
        severity, desc = LogSeverity.INFO, f"{action} successful"
    elif status_code == 429:
        severity, desc = LogSeverity.WARNING, f"{action} rate limited"
    elif status_code < 500:
        severity, desc = LogSeverity.WARNING, f"{action} failed — invalid parameters"
    else:
        severity, desc = LogSeverity.ERROR, f"{action} failed with server error"

    log_action(
        logger=logger,
        severity=severity,
        action=action,
        description=desc,
        status_code=status_code,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra=log_data,
    )


# ==========================================================================
# PUBLIC ENDPOINTS
# ==========================================================================

@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key="ip", rate="200/h", method="GET", block=True)
def list_posts_view(request):
    """Public: list published blog posts with filters and pagination."""
    start_time = time.time()
    action = "blog_post_list"

    try:
        category_slug = request.GET.get("category")
        search = sanitize_search_query(request.GET.get("search", ""))
        is_featured_param = request.GET.get("is_featured")

        try:
            page = int(request.GET.get("page", 1))
            limit = int(request.GET.get("limit", 20))
        except ValueError:
            page, limit = 1, 20
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20

        is_featured = None
        if is_featured_param is not None and is_featured_param != "":
            is_featured = is_featured_param.lower() == "true"

        posts, total, pagination = list_posts(
            admin=False,
            category_slug=category_slug,
            search=search,
            is_featured=is_featured,
            page=page,
            limit=limit,
        )

        _log_request(request, action, start_time, 200, extra={"total": total})
        return APIResponse.success(
            {"posts": serialize_post_list(posts), "total": total, "pagination": pagination},
            "Posts retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Blog post list error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key="ip", rate="200/h", method="GET", block=True)
def post_detail(request, slug):
    """Public: single published post by slug."""
    start_time = time.time()
    action = "blog_post_detail"

    try:
        post = get_post_by_slug(slug, admin=False)
        if not post:
            _log_request(request, action, start_time, 404, extra={"slug": slug})
            return APIResponse.not_found("Post not found")

        _log_request(request, action, start_time, 200, extra={"post_id": str(post.id), "slug": slug})
        return APIResponse.success(serialize_post(post), "Post retrieved successfully")

    except Exception as e:
        logger.error(f"Blog post detail error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"slug": slug, "error": str(e)})
        return APIResponse.server_error()


# ==========================================================================
# ADMIN ENDPOINTS
# ==========================================================================

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key="user", rate="100/h", method="GET", block=True)
def admin_list_posts(request):
    """Admin: list all blog posts regardless of status."""
    start_time = time.time()
    action = "admin_blog_post_list"

    try:
        search = sanitize_search_query(request.GET.get("search", ""))
        status = request.GET.get("status")
        category_slug = request.GET.get("category")
        is_featured_param = request.GET.get("is_featured")

        try:
            page = int(request.GET.get("page", 1))
            limit = int(request.GET.get("limit", 20))
        except ValueError:
            page, limit = 1, 20
        if limit > 100:
            limit = 100

        is_featured = None
        if is_featured_param is not None and is_featured_param != "":
            is_featured = is_featured_param.lower() == "true"

        posts, total, pagination = list_posts(
            admin=True,
            category_slug=category_slug,
            status=status,
            search=search,
            is_featured=is_featured,
            page=page,
            limit=limit,
        )

        _log_request(request, action, start_time, 200, extra={"total": total})
        return APIResponse.success(
            {"posts": serialize_post_list(posts, is_admin=True), "total": total, "pagination": pagination},
            "Posts retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Admin blog post list error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key="user", rate="100/h", method="GET", block=True)
def admin_post_detail(request, id):
    """Admin: single post by id (any status)."""
    start_time = time.time()
    action = "admin_blog_post_detail"

    try:
        post = get_post_by_id(id, admin=True)
        if not post:
            _log_request(request, action, start_time, 404, extra={"post_id": id})
            return APIResponse.not_found("Post not found")

        _log_request(request, action, start_time, 200, extra={"post_id": str(post.id)})
        return APIResponse.success(serialize_post(post, is_admin=True), "Post retrieved successfully")

    except Exception as e:
        logger.error(f"Admin blog post detail error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"post_id": id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def admin_create_post(request):
    """Admin: create a new blog post."""
    start_time = time.time()
    action = "admin_blog_post_create"

    try:
        cleaned, errors = validate_post(request.json_data)
        if errors:
            _log_request(request, action, start_time, 400, extra={"errors": errors})
            return APIResponse.validation_error(errors)

        post, errors = BlogPostService.create_post(cleaned, user=request.user)
        if errors:
            _log_request(request, action, start_time, 400, extra={"errors": errors})
            return APIResponse.validation_error(errors)

        _log_request(request, action, start_time, 201, extra={"post_id": str(post.id), "title": post.title})
        return APIResponse.created(
            {"post_id": str(post.id), "slug": post.slug, "title": post.title},
            "Post created successfully",
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin blog post create error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def admin_update_post(request, id):
    """Admin: update an existing blog post."""
    start_time = time.time()
    action = "admin_blog_post_update"

    try:
        cleaned, errors = validate_post(request.json_data, is_update=True)
        if errors:
            _log_request(request, action, start_time, 400, extra={"post_id": id, "errors": errors})
            return APIResponse.validation_error(errors)

        post, errors = BlogPostService.update_post(id, cleaned, user=request.user)
        if errors:
            if errors.get("post"):
                _log_request(request, action, start_time, 404, extra={"post_id": id})
                return APIResponse.not_found(errors["post"])
            _log_request(request, action, start_time, 400, extra={"post_id": id, "errors": errors})
            return APIResponse.validation_error(errors)

        _log_request(request, action, start_time, 200, extra={"post_id": str(post.id), "title": post.title})
        return APIResponse.success(
            {"post_id": str(post.id), "slug": post.slug, "title": post.title},
            "Post updated successfully",
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin blog post update error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"post_id": id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def admin_publish_post(request, id):
    """Admin: publish a blog post."""
    start_time = time.time()
    action = "admin_blog_post_publish"

    try:
        post, errors = BlogPostService.publish_post(id, user=request.user)
        if errors:
            _log_request(request, action, start_time, 404, extra={"post_id": id})
            return APIResponse.not_found(errors.get("post", "Post not found"))

        _log_request(request, action, start_time, 200, extra={"post_id": str(post.id)})
        return APIResponse.success({"post_id": str(post.id), "status": post.status}, "Post published")

    except Exception as e:
        logger.error(f"Admin blog post publish error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"post_id": id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def admin_archive_post(request, id):
    """Admin: archive a blog post."""
    start_time = time.time()
    action = "admin_blog_post_archive"

    try:
        post, errors = BlogPostService.archive_post(id, user=request.user)
        if errors:
            _log_request(request, action, start_time, 404, extra={"post_id": id})
            return APIResponse.not_found(errors.get("post", "Post not found"))

        _log_request(request, action, start_time, 200, extra={"post_id": str(post.id)})
        return APIResponse.success({"post_id": str(post.id), "status": post.status}, "Post archived")

    except Exception as e:
        logger.error(f"Admin blog post archive error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"post_id": id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key="user", rate="20/h", method=["DELETE", "POST"], block=True)
def admin_delete_post(request, id):
    """Admin: delete a blog post."""
    start_time = time.time()
    action = "admin_blog_post_delete"

    try:
        success, errors = BlogPostService.delete_post(id, user=request.user)
        if not success:
            _log_request(request, action, start_time, 404, extra={"post_id": id})
            return APIResponse.not_found(errors.get("post", "Post not found"))

        _log_request(request, action, start_time, 200, extra={"post_id": id})
        return APIResponse.success(message="Post deleted successfully")

    except Exception as e:
        logger.error(f"Admin blog post delete error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"post_id": id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def admin_bulk_action_posts(request):
    """Admin: bulk publish/archive/delete on blog posts."""
    start_time = time.time()
    action = "admin_blog_post_bulk_action"

    try:
        cleaned, errors = validate_bulk_action(request.json_data)
        if errors:
            _log_request(request, action, start_time, 400, extra={"errors": errors})
            return APIResponse.validation_error(errors)

        results, error = BlogPostService.bulk_action_posts(
            cleaned["post_ids"], cleaned["action"], user=request.user
        )
        if error:
            _log_request(request, action, start_time, 400, extra={"error": error})
            return APIResponse.validation_error(error)

        serialized = serialize_bulk_action_result(results)
        _log_request(request, action, start_time, 200, extra={
            "action": cleaned["action"],
            "total": cleaned["post_ids"],
            "success_count": serialized["success_count"],
            "failed_count": serialized["failed_count"],
        })
        return APIResponse.success(serialized, f"Bulk {cleaned['action']} completed")

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin blog post bulk action error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()
