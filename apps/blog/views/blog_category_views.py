"""
Blog Category Views — public + admin endpoints for blog categories.
"""

import json
import logging
import time

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.blog.schemas import serialize_category, serialize_category_list
from apps.blog.selectors import get_category_by_id, list_categories
from apps.blog.services import BlogCategoryService
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
def list_categories_view(request):
    """Public: list active blog categories."""
    start_time = time.time()
    action = "blog_category_list"

    try:
        categories = list_categories(active_only=True)
        _log_request(request, action, start_time, 200, extra={"total": len(categories)})
        return APIResponse.success(
            {"categories": serialize_category_list(categories)},
            "Categories retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Blog category list error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


# ==========================================================================
# ADMIN ENDPOINTS
# ==========================================================================

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key="user", rate="100/h", method="GET", block=True)
def admin_list_categories(request):
    """Admin: list all blog categories (including inactive)."""
    start_time = time.time()
    action = "admin_blog_category_list"

    try:
        categories = list_categories(active_only=False)
        _log_request(request, action, start_time, 200, extra={"total": len(categories)})
        return APIResponse.success(
            {"categories": serialize_category_list(categories, is_admin=True)},
            "Categories retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Admin blog category list error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def admin_create_category(request):
    """Admin: create a blog category."""
    start_time = time.time()
    action = "admin_blog_category_create"

    try:
        data = request.json_data
        name = str(data.get("name", "")).strip()
        if not name:
            return APIResponse.bad_request("Category name is required")

        category, errors = BlogCategoryService.create_category(
            name=name,
            description=data.get("description", ""),
            is_active=data.get("is_active", True) if isinstance(data.get("is_active"), bool) else True,
            user=request.user,
        )
        if errors:
            _log_request(request, action, start_time, 400, extra={"errors": errors})
            return APIResponse.validation_error(errors)

        _log_request(request, action, start_time, 201, extra={"category_id": str(category.id), "name": category.name})
        return APIResponse.created(
            {"category_id": str(category.id), "slug": category.slug, "name": category.name},
            "Category created successfully",
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin blog category create error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key="user", rate="50/h", method="POST", block=True)
def admin_update_category(request, id):
    """Admin: update a blog category."""
    start_time = time.time()
    action = "admin_blog_category_update"

    try:
        data = request.json_data
        update_data = {}

        if "name" in data and data["name"]:
            update_data["name"] = data["name"]
        if "description" in data:
            update_data["description"] = data["description"]
        if "is_active" in data:
            val = data["is_active"]
            update_data["is_active"] = val.lower() == "true" if isinstance(val, str) else bool(val)

        if not update_data:
            return APIResponse.bad_request("No data provided for update")

        category, errors = BlogCategoryService.update_category(id, update_data, user=request.user)
        if errors:
            if errors.get("category"):
                return APIResponse.not_found(errors["category"])
            _log_request(request, action, start_time, 400, extra={"errors": errors})
            return APIResponse.validation_error(errors)

        _log_request(request, action, start_time, 200, extra={"category_id": str(category.id), "name": category.name})
        return APIResponse.success(
            {"category_id": str(category.id), "slug": category.slug, "name": category.name},
            "Category updated successfully",
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin blog category update error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"category_id": id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE", "POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key="user", rate="20/h", method=["DELETE", "POST"], block=True)
def admin_delete_category(request, id):
    """Admin: delete a blog category."""
    start_time = time.time()
    action = "admin_blog_category_delete"

    try:
        success, errors = BlogCategoryService.delete_category(id, user=request.user)
        if not success:
            if errors.get("category"):
                return APIResponse.not_found(errors["category"])
            return APIResponse.bad_request(errors.get("category", "Cannot delete category"))

        _log_request(request, action, start_time, 200, extra={"category_id": id})
        return APIResponse.success(message="Category deleted successfully")

    except Exception as e:
        logger.error(f"Admin blog category delete error: {e}", exc_info=True)
        _log_request(request, action, start_time, 500, extra={"category_id": id, "error": str(e)})
        return APIResponse.server_error()
