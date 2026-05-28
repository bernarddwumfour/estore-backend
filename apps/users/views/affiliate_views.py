"""
Affiliate Views - Affiliate management endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.users.selectors import get_affiliates_filtered
from apps.users.schemas import (
    serialize_affiliate_list,
    serialize_affiliate_user,
    serialize_pagination_metadata,
)
from apps.users.models.user import User
from apps.users.models.affiliate import Affiliate

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def list_affiliate_users(request):
    """Admin: List all affiliate users"""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        search = request.GET.get("search", "").strip()
        is_active = request.GET.get("is_active")
        email_verified = request.GET.get("email_verified")
        level = request.GET.get("level")
        min_earnings = request.GET.get("min_earnings")
        max_earnings = request.GET.get("max_earnings")
        sort_by = request.GET.get("sort_by", "joined_at")
        sort_order = request.GET.get("sort_order", "desc")

        is_active_bool = None
        if is_active is not None and is_active != '':
            is_active_bool = is_active.lower() == "true"

        email_verified_bool = None
        if email_verified is not None and email_verified != '':
            email_verified_bool = email_verified.lower() == "true"

        min_earnings_float = float(min_earnings) if min_earnings else None
        max_earnings_float = float(max_earnings) if max_earnings else None

        affiliates, total, pagination_meta = get_affiliates_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            is_active=is_active_bool,
            email_verified=email_verified_bool,
            level=level if level else None,
            min_earnings=min_earnings_float,
            max_earnings=max_earnings_float,
            sort_by=sort_by,
            sort_order=sort_order,
        )

        affiliates_data = serialize_affiliate_list(affiliates, is_admin=True)

        return APIResponse.success(
            data={
                "affiliates": affiliates_data,
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta)
            },
            message="Affiliate users retrieved successfully"
        )

    except Exception as e:
        logger.error(f"List affiliate users error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@json_request_required
def make_affiliate(request, user_id):
    """Admin: Make a user an affiliate (creates Affiliate profile)"""
    try:
        user = get_object_or_404(User, id=user_id)

        if Affiliate.objects.filter(user=user).exists():
            return APIResponse.bad_request("User is already an affiliate")

        affiliate = Affiliate.objects.create(
            user=user,
            is_active=True,
            is_approved=True,
        )

        logger.info(f"User {user.email} is now an affiliate (ID: {affiliate.id})")

        return APIResponse.success(
            data={
                "id": str(user.id),
                "email": user.email,
                "is_affiliate": True,
                "affiliate_id": str(affiliate.id),
                "referral_code": affiliate.referral_code,
            },
            message="User is now an affiliate"
        )

    except Exception as e:
        logger.error(f"Make affiliate error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@json_request_required
def remove_affiliate(request, user_id):
    """Admin: Remove affiliate status from a user (deletes Affiliate profile)"""
    try:
        user = get_object_or_404(User, id=user_id)

        affiliate = Affiliate.objects.filter(user=user).first()
        if not affiliate:
            return APIResponse.bad_request("User is not an affiliate")

        affiliate.delete()

        logger.info(f"Affiliate status removed from {user.email}")

        return APIResponse.success(
            data={"id": str(user.id), "email": user.email, "is_affiliate": False},
            message="Affiliate status removed"
        )

    except Exception as e:
        logger.error(f"Remove affiliate error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def get_affiliate_profile(request):
    """Get current user's affiliate profile (for affiliates)"""
    try:
        user = request.user

        affiliate = Affiliate.objects.filter(user=user).first()
        if not affiliate:
            return APIResponse.not_found("You are not an affiliate")

        affiliate_data = serialize_affiliate_user(affiliate, is_admin=False)

        return APIResponse.success(affiliate_data, "Affiliate profile retrieved")

    except Exception as e:
        logger.error(f"Get affiliate profile error: {str(e)}")
        return APIResponse.server_error()