"""
Admin User Views - Admin-only user management endpoints
"""

import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.users.selectors import (
    get_users_filtered,
    get_customers_filtered,
    get_staff_users_filtered,
    get_guest_users_filtered,
)
from apps.users.schemas import (
    serialize_user_list,
    serialize_customer_list,
    serialize_staff_list,
    serialize_guest_list,
    serialize_pagination_metadata,
    validate_bulk_user_action,
)
from apps.users.models.user import User

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def list_all_users(request):
    """Admin: List all users with pagination and filters"""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        search = request.GET.get("search", "").strip()
        role = request.GET.get("role")
        is_active = request.GET.get("is_active")
        email_verified = request.GET.get("email_verified")
        is_guest = request.GET.get("is_guest")
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")

        is_active_bool = None
        if is_active is not None and is_active != '':
            is_active_bool = is_active.lower() == "true"

        email_verified_bool = None
        if email_verified is not None and email_verified != '':
            email_verified_bool = email_verified.lower() == "true"

        is_guest_bool = None
        if is_guest is not None and is_guest != '':
            is_guest_bool = is_guest.lower() == "true"

        users, total, pagination_meta = get_users_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            role=role if role else None,
            is_active=is_active_bool,
            email_verified=email_verified_bool,
            is_guest=is_guest_bool,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        users_data = serialize_user_list(users, is_admin=True)

        return APIResponse.success(
            data={
                "users": users_data,
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta)
            },
            message="Users retrieved successfully"
        )

    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        return APIResponse.bad_request(f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"List all users error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@jwt_required
@role_required("admin")
def user_detail(request, user_id):
    """Admin: Get, update, or delete a specific user"""
    try:
        user = get_object_or_404(User, id=user_id)

        if request.method == "GET":
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "role": user.role,
                "phone": user.phone,
                "is_active": user.is_active,
                "email_verified": user.email_verified,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
                "last_login": user.last_login.isoformat() if user.last_login else None,
            }
            return APIResponse.success(user_data)

        elif request.method in ["PUT", "PATCH"]:
            data = json.loads(request.body)

            restricted_fields = ["password", "email", "id"]
            for field in restricted_fields:
                if field in data:
                    return APIResponse.bad_request(f"Cannot modify {field} through this endpoint")

            allowed_fields = ["role", "is_active", "is_staff", "phone"]
            for field in allowed_fields:
                if field in data:
                    setattr(user, field, data[field])

            user.save()
            logger.info(f"Admin updated user {user.email}")
            return APIResponse.success(message="User updated successfully")

        elif request.method == "DELETE":
            user.is_active = False
            user.save()
            logger.warning(f"Admin deactivated user {user.email}")
            return APIResponse.success(message="User deactivated successfully")

    except Exception as e:
        logger.error(f"User detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def list_customers(request):
    """Admin: List all registered customers"""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        search = request.GET.get("search", "").strip()
        is_active = request.GET.get("is_active")
        email_verified = request.GET.get("email_verified")
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")

        is_active_bool = None
        if is_active is not None and is_active != '':
            is_active_bool = is_active.lower() == "true"

        email_verified_bool = None
        if email_verified is not None and email_verified != '':
            email_verified_bool = email_verified.lower() == "true"
            

        users, total, pagination_meta = get_customers_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            is_active=is_active_bool,
            email_verified=email_verified_bool,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        users_data = serialize_customer_list(users, is_admin=True)

        return APIResponse.success(
            data={
                "customers": users_data,
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta)
            },
            message="Customers retrieved successfully"
        )

    except Exception as e:
        logger.error(f"List customers error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def list_guest_users(request):
    """Admin: List all guest users"""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        search = request.GET.get("search", "").strip()
        is_active = request.GET.get("is_active")
        email_verified = request.GET.get("email_verified")
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")

        is_active_bool = None
        if is_active is not None and is_active != '':
            is_active_bool = is_active.lower() == "true"

        email_verified_bool = None
        if email_verified is not None and email_verified != '':
            email_verified_bool = email_verified.lower() == "true"

        users, total, pagination_meta = get_guest_users_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            is_active=is_active_bool,
            email_verified=email_verified_bool,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        users_data = serialize_guest_list(users, is_admin=True)

        return APIResponse.success(
            data={
                "guests": users_data,
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta)
            },
            message="Guest users retrieved successfully"
        )

    except Exception as e:
        logger.error(f"List guest users error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@json_request_required
def bulk_user_action(request):
    """Admin: Bulk actions on users (activate, deactivate, delete only)"""
    try:
        data = request.json_data
        cleaned, errors = validate_bulk_user_action(data)

        if errors:
            return APIResponse.validation_error(errors)

        if cleaned["action"] not in ["activate", "deactivate", "delete"]:
            return APIResponse.validation_error({"action": "Invalid action for bulk user action"})

        results = {"success": [], "failed": [], "total": len(cleaned["user_ids"])}

        for user_id in cleaned["user_ids"]:
            try:
                user = User.objects.get(id=user_id)

                if cleaned["action"] == "activate":
                    user.is_active = True
                    user.save()
                    results["success"].append({"id": str(user.id), "name": user.email})

                elif cleaned["action"] == "deactivate":
                    user.is_active = False
                    user.save()
                    results["success"].append({"id": str(user.id), "name": user.email})

                elif cleaned["action"] == "delete":
                    if str(user.id) == str(request.user.id):
                        results["failed"].append({"id": user_id, "name": user.email, "reason": "Cannot delete your own account"})
                        continue
                    user.delete()
                    results["success"].append({"id": str(user.id), "name": user.email})

            except User.DoesNotExist:
                results["failed"].append({"id": user_id, "name": "Unknown", "reason": "User not found"})
            except Exception as e:
                results["failed"].append({"id": user_id, "name": "Unknown", "reason": str(e)})

        return APIResponse.success(
            data={
                "success": results["success"],
                "failed": results["failed"],
                "total": results["total"],
                "success_count": len(results["success"]),
                "failed_count": len(results["failed"]),
            },
            message=f"Processed {len(results['success'])} of {results['total']} users"
        )

    except Exception as e:
        logger.error(f"Bulk user action error: {str(e)}")
        return APIResponse.server_error()