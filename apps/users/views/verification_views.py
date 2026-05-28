"""
Verification Views - Email verification endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.http import JsonResponse
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.users.services.verification_service import VerificationService
from apps.users.models.user import User

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def verify_email(request):
    """API endpoint to verify email using token"""
    token = request.json_data["token"]
    try:
        success, user, message = VerificationService.verify_email_token(token)

        if success:
            response_data = {
                "success": True,
                "message": message,
                "data": {
                    "email": user.email,
                    "email_verified": user.email_verified,
                    "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
                    "username": user.username,
                    "user_id": str(user.id),
                },
            }
            return JsonResponse(response_data, status=200)
        else:
            return JsonResponse(
                {"success": False, "error": message, "resend_url": reverse("resend-verification")},
                status=400,
            )

    except Exception as e:
        logger.error(f"Email verification API error: {str(e)}")
        return JsonResponse({"success": False, "error": "Email verification failed"}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def validate_verification_token(request):
    """Validate verification token without using it"""
    try:
        data = request.json_data

        if "token" not in data or not data["token"]:
            return APIResponse.bad_request("Token is required")

        valid, user, message = VerificationService.validate_token(data["token"])

        if valid:
            return APIResponse.success({
                "valid": True,
                "user_email": user.email,
                "user_id": str(user.id),
                "message": message,
            })
        else:
            return APIResponse.success({"valid": False, "message": message})

    except Exception as e:
        logger.error(f"Token validation API error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def resend_verification(request):
    """API endpoint to resend verification email"""
    try:
        data = request.json_data

        if "email" not in data or not data["email"]:
            return APIResponse.bad_request("Email is required")

        if "@" not in data["email"] or "." not in data["email"]:
            return APIResponse.validation_error({"email": "Invalid email format"})

        success, message = VerificationService.resend_verification_email(data["email"], request)

        if success:
            return APIResponse.success(message=message)
        else:
            return APIResponse.bad_request(message)

    except Exception as e:
        logger.error(f"Resend verification API error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def request_verification(request):
    """API endpoint for authenticated user to request verification email"""
    try:
        user = request.user

        if user.email_verified:
            return APIResponse.bad_request("Email is already verified")

        success, message = VerificationService.send_verification_email(user, request)

        if success:
            return APIResponse.success(message=message)
        else:
            return APIResponse.bad_request(message)

    except Exception as e:
        logger.error(f"Request verification API error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def check_verification_status(request):
    """API endpoint to check verification status of authenticated user"""
    try:
        user = request.user
        status = VerificationService.get_verification_status(user.id)

        if status:
            return APIResponse.success(status)
        else:
            return APIResponse.not_found("User not found")

    except Exception as e:
        logger.error(f"Check verification status API error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def admin_check_verification(request, user_id):
    """Admin API: Check verification status of any user"""
    try:
        user = get_object_or_404(User, id=user_id)
        status = VerificationService.get_verification_status(user.id)

        if status:
            return APIResponse.success({
                **status,
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "username": user.username,
                    "role": user.role,
                },
            })
        else:
            return APIResponse.not_found("User not found")

    except Exception as e:
        logger.error(f"Admin check verification error: {str(e)}")
        return APIResponse.server_error()