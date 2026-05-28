"""
Password Views - Password reset functionality
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import json_request_required
from apps.users.services.password_service import PasswordService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def password_reset_request(request):
    """Request password reset"""
    try:
        data = request.json_data

        if "email" not in data or not data["email"]:
            return APIResponse.bad_request("Email required")

        success, message = PasswordService.request_reset(data["email"], request)

        if not success:
            return APIResponse.bad_request(message)

        return APIResponse.success(message=message)

    except Exception as e:
        logger.error(f"Reset request error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def password_reset_confirm(request):
    """Reset password with token"""
    try:
        data = request.json_data

        required = ["token", "new_password"]
        for field in required:
            if field not in data or not data[field]:
                return APIResponse.bad_request(f"{field} required")

        success, error = PasswordService.reset_password(data["token"], data["new_password"], request)

        if not success:
            return APIResponse.bad_request(error)

        return APIResponse.success(message="Password reset successful")

    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def password_reset_validate(request):
    """Validate reset token"""
    try:
        data = request.json_data

        if "token" not in data or not data["token"]:
            return APIResponse.bad_request("Token required")

        valid, error, user = PasswordService.validate_token(data["token"])

        if not valid:
            return APIResponse.bad_request(error)

        return APIResponse.success({"valid": True, "user_email": user.email})

    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        return APIResponse.server_error()