"""
Affiliate Views - Affiliate management endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.users.selectors import get_affiliates_filtered, get_user_by_email
from apps.users.schemas import (
    serialize_affiliate_list,
    serialize_affiliate_user,
    serialize_pagination_metadata,
)
from apps.users.models.user import User
from apps.users.models.affiliate import Affiliate
from apps.promotions.models import DiscountCode
from apps.promotions.services import DiscountCodeService

logger = logging.getLogger(__name__)


def _make_affiliate_for_user(
    user,
    discount_code,
    referral_code=None,
    commission_rate=None,
    commission_basis=None,
):
    create_kwargs = {}
    if commission_rate is not None:
        create_kwargs["commission_rate"] = commission_rate
    if commission_basis is not None:
        create_kwargs["commission_basis"] = commission_basis

    affiliate = Affiliate.objects.create(
        user=user,
        referral_code=referral_code or "",
        is_active=True,
        is_approved=True,
        **create_kwargs,
    )
    discount_code, error = DiscountCodeService.assign_discount_code_to_affiliate(
        discount_code,
        affiliate,
    )
    if error:
        affiliate.delete()
        return None, None, error
    return affiliate, discount_code, None


def _resolve_commission(request):
    """Validate optional commission_rate / commission_basis from the body.

    Returns ((rate, basis), error_response): rate is a Decimal or None,
    basis a valid choice or None (None = keep model default / current value).
    """
    from decimal import Decimal, InvalidOperation

    data = request.json_data
    rate = None
    basis = None

    if data.get("commission_rate") not in (None, ""):
        try:
            rate = Decimal(str(data["commission_rate"]))
        except InvalidOperation:
            return None, APIResponse.validation_error(
                {"commission_rate": "Commission rate must be a number"}
            )
        if not Decimal("0") <= rate <= Decimal("100"):
            return None, APIResponse.validation_error(
                {"commission_rate": "Commission rate must be between 0 and 100"}
            )

    if data.get("commission_basis"):
        basis = data["commission_basis"]
        valid_bases = dict(Affiliate.BASIS_CHOICES).keys()
        if basis not in valid_bases:
            return None, APIResponse.validation_error(
                {"commission_basis": f"Commission basis must be one of: {', '.join(valid_bases)}"}
            )

    return (rate, basis), None


def _resolve_discount_code(request):
    discount_code_id = request.json_data.get("discount_code_id")
    if not discount_code_id:
        return None, APIResponse.validation_error({"discount_code_id": "Discount code is required"})

    discount_code = DiscountCode.objects.filter(id=discount_code_id).first()
    if not discount_code:
        return None, APIResponse.not_found("Discount code not found")
    if discount_code.affiliate_id:
        return None, APIResponse.validation_error({"discount_code_id": "Discount code is already assigned to an affiliate"})
    return discount_code, None


def _resolve_referral_code(request):
    referral_code = (request.json_data.get("referral_code") or "").strip().upper()
    if not referral_code:
        return None, None
    if DiscountCode.objects.filter(code=referral_code).exists():
        return None, APIResponse.validation_error(
            {"referral_code": "Referral code cannot match an existing discount code"}
        )
    if Affiliate.objects.filter(referral_code=referral_code).exists():
        return None, APIResponse.validation_error(
            {"referral_code": "Referral code already exists"}
        )
    return referral_code, None


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def list_affiliate_users(request):
    """Admin: List all affiliate users"""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        search = request.GET.get("search", "").strip()
        is_active = request.GET.get("is_active")
        email_verified = request.GET.get("email_verified")
        level = request.GET.get("affiliate_level") or request.GET.get("level")
        min_earnings = request.GET.get("min_earnings")
        max_earnings = request.GET.get("max_earnings")
        min_referrals = request.GET.get("min_referrals")
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
        min_referrals_int = int(min_referrals) if min_referrals else None

        affiliates, total, pagination_meta = get_affiliates_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            is_active=is_active_bool,
            email_verified=email_verified_bool,
            level=level if level else None,
            min_earnings=min_earnings_float,
            max_earnings=max_earnings_float,
            min_referrals=min_referrals_int,
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
@role_required("admin", "staff")
@json_request_required
def make_affiliate(request, user_id):
    """Admin: Make a user an affiliate (creates Affiliate profile)"""
    try:
        user = get_object_or_404(User, id=user_id)
        discount_code, response = _resolve_discount_code(request)
        if response:
            return response
        referral_code, response = _resolve_referral_code(request)
        if response:
            return response
        commission, response = _resolve_commission(request)
        if response:
            return response
        commission_rate, commission_basis = commission

        if Affiliate.objects.filter(user=user).exists():
            return APIResponse.bad_request("User is already an affiliate")

        affiliate, discount_code, error = _make_affiliate_for_user(
            user,
            discount_code,
            referral_code=referral_code,
            commission_rate=commission_rate,
            commission_basis=commission_basis,
        )
        if error:
            return APIResponse.validation_error(error)

        logger.info(f"User {user.email} is now an affiliate (ID: {affiliate.id})")

        return APIResponse.success(
            data={
                "id": str(user.id),
                "email": user.email,
                "is_affiliate": True,
                "affiliate_id": str(affiliate.id),
                "referral_code": affiliate.referral_code,
                "discount_code": discount_code.code,
                "commission_rate": float(affiliate.commission_rate),
                "commission_basis": affiliate.commission_basis,
            },
            message="User is now an affiliate"
        )

    except Exception as e:
        logger.error(f"Make affiliate error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def make_affiliate_by_email(request):
    """Admin: make a user an affiliate using their email."""
    try:
        email = (request.json_data.get("email") or "").strip().lower()
        if not email:
            return APIResponse.validation_error({"email": "Email is required"})
        discount_code, response = _resolve_discount_code(request)
        if response:
            return response
        referral_code, response = _resolve_referral_code(request)
        if response:
            return response
        commission, response = _resolve_commission(request)
        if response:
            return response
        commission_rate, commission_basis = commission

        user = get_user_by_email(email)
        if not user:
            return APIResponse.not_found("User not found")

        if Affiliate.objects.filter(user=user).exists():
            return APIResponse.bad_request("User is already an affiliate")

        affiliate, discount_code, error = _make_affiliate_for_user(
            user,
            discount_code,
            referral_code=referral_code,
            commission_rate=commission_rate,
            commission_basis=commission_basis,
        )
        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data={
                "id": str(user.id),
                "email": user.email,
                "is_affiliate": True,
                "affiliate_id": str(affiliate.id),
                "referral_code": affiliate.referral_code,
                "discount_code": discount_code.code,
                "commission_rate": float(affiliate.commission_rate),
                "commission_basis": affiliate.commission_basis,
            },
            message="User is now an affiliate",
        )

    except Exception as e:
        logger.error(f"Make affiliate by email error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def update_affiliate_commission(request, user_id):
    """Admin: Update an affiliate's commission rate and/or basis.

    Applies to future orders only — recorded commissions keep the
    rate/amount snapshots taken when their order was placed.
    """
    try:
        user = get_object_or_404(User, id=user_id)
        affiliate = Affiliate.objects.filter(user=user).first()
        if not affiliate:
            return APIResponse.bad_request("User is not an affiliate")

        commission, response = _resolve_commission(request)
        if response:
            return response
        commission_rate, commission_basis = commission

        if commission_rate is None and commission_basis is None:
            return APIResponse.validation_error(
                {"commission": "Provide commission_rate and/or commission_basis"}
            )

        update_fields = ["updated_at"]
        if commission_rate is not None:
            affiliate.commission_rate = commission_rate
            update_fields.append("commission_rate")
        if commission_basis is not None:
            affiliate.commission_basis = commission_basis
            update_fields.append("commission_basis")
        affiliate.save(update_fields=update_fields)

        logger.info(
            f"Affiliate commission updated for {user.email}: "
            f"{affiliate.commission_rate}% of {affiliate.commission_basis}"
        )

        return APIResponse.success(
            data={"affiliate": serialize_affiliate_user(affiliate, is_admin=True)},
            message="Affiliate commission updated",
        )

    except Exception as e:
        logger.error(f"Update affiliate commission error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
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
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def toggle_affiliate_status(request, user_id):
    """Admin: activate or deactivate an affiliate profile."""
    try:
        user = get_object_or_404(User, id=user_id)
        affiliate = Affiliate.objects.filter(user=user).first()
        if not affiliate:
            return APIResponse.bad_request("User is not an affiliate")

        is_active = request.json_data.get("is_active")
        if not isinstance(is_active, bool):
            return APIResponse.validation_error({"is_active": "Boolean is_active is required"})

        affiliate.is_active = is_active
        affiliate.save(update_fields=["is_active"])
        affiliate.discount_codes.update(is_active=is_active)

        return APIResponse.success(
            data={
                "id": str(user.id),
                "email": user.email,
                "is_active": affiliate.is_active,
            },
            message=f"Affiliate {'activated' if is_active else 'deactivated'} successfully",
        )

    except Exception as e:
        logger.error(f"Toggle affiliate status error: {str(e)}")
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
