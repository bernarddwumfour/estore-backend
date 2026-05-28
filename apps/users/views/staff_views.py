"""
Staff Views - Admin-only staff management endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.users.selectors import get_staff_users_filtered
from apps.users.schemas import (
    serialize_staff_list,
    serialize_pagination_metadata,
    validate_bulk_user_action,
)
from apps.users.services.staff_service import StaffService
from apps.users.models.user import User

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def list_staff_users(request):
    """Admin: List all staff and admin users"""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        search = request.GET.get("search", "").strip()
        role = request.GET.get("role")
        is_active = request.GET.get("is_active")
        email_verified = request.GET.get("email_verified")
        sort_by = request.GET.get("sort_by", "date_joined")
        sort_order = request.GET.get("sort_order", "desc")

        is_active_bool = None
        if is_active is not None and is_active != '':
            is_active_bool = is_active.lower() == "true"

        email_verified_bool = None
        if email_verified is not None and email_verified != '':
            email_verified_bool = email_verified.lower() == "true"

        users, total, pagination_meta = get_staff_users_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            role=role if role else None,
            is_active=is_active_bool,
            email_verified=email_verified_bool,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        users_data = serialize_staff_list(users, is_admin=True)

        return APIResponse.success(
            data={
                "staff": users_data,
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta)
            },
            message="Staff users retrieved successfully"
        )

    except Exception as e:
        logger.error(f"List staff users error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@json_request_required
def create_staff_user(request):
    """Admin: Create a new staff or admin user"""
    try:
        data = request.json_data
        user_data, errors = StaffService.create_staff_user(data)

        if errors:
            return APIResponse.validation_error(errors)

        return APIResponse.created(
            data=user_data,
            message=f"{user_data['role'].title()} created successfully"
        )

    except Exception as e:
        logger.error(f"Create staff user error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@json_request_required
def bulk_staff_action(request):
    """Admin: Bulk actions on staff users"""
    try:
        data = request.json_data
        cleaned, errors = validate_bulk_user_action(data)

        if errors:
            return APIResponse.validation_error(errors)

        results = StaffService.bulk_action(
            action=cleaned["action"],
            user_ids=cleaned["user_ids"],
            request_user=request.user
        )

        return APIResponse.success(
            data={
                "success": results["success"],
                "failed": results["failed"],
                "total": results["total"],
                "success_count": results["success_count"],
                "failed_count": results["failed_count"],
            },
            message=f"Processed {results['success_count']} of {results['total']} staff members"
        )

    except Exception as e:
        logger.error(f"Bulk staff action error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
@role_required("admin")
def delete_staff_user(request, user_id):
    """Admin: Permanently delete a staff user"""
    try:
        user = get_object_or_404(User, id=user_id, role__in=['admin', 'staff'])

        if str(user.id) == str(request.user.id):
            return APIResponse.bad_request("You cannot delete your own account")

        user.delete()
        logger.warning(f"Staff user deleted: {user.email} by {request.user.email}")

        return APIResponse.success(message="Staff user deleted successfully")

    except Exception as e:
        logger.error(f"Delete staff user error: {str(e)}")
        return APIResponse.server_error()