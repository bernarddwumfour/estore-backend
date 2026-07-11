"""
Authentication Views - Login, registration, logout, token refresh
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.users.services.auth_service import AuthService
from apps.users.utils.token_utils import (
    generate_jwt_token,
    validate_jwt_token,
    revoke_token,
)
from apps.users.models.user import User

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def register_customer(request):
    """Customer self-registration endpoint - converts guest users to registered users"""
    try:
        data = request.json_data
        user_data, errors = AuthService.register_customer(data, request)

        if errors:
            return APIResponse.validation_error(errors)

        return APIResponse.created(user_data, "Registration successful")

    except Exception as e:
        logger.error(f"Customer registration view error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def register_user(request):
    """Admin/Staff user registration (with role selection)"""
    try:
        data = request.json_data
        user_data, errors = AuthService.register_user(data, request)

        if errors:
            return APIResponse.validation_error(errors)

        return APIResponse.created(user_data, "User created successfully")

    except Exception as e:
        logger.error(f"Admin user registration error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@ratelimit(key="post:email", rate="10/h", method="POST", block=True)
@json_request_required
def login(request):
    """User login"""
    try:
        data = request.json_data

        required_fields = ["email", "password"]
        for field in required_fields:
            if field not in data or not data[field]:
                return APIResponse.bad_request(f"{field} is required")

        auth_data, error = AuthService.authenticate_user(
            data["email"], data["password"], request
        )

        if error:
            return APIResponse.unauthorized(error)

        return APIResponse.success(auth_data, "Login successful")

    except Exception as e:
        logger.error(f"Login view error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def logout(request):
    """User logout - revoke the current access token and the supplied refresh token."""
    try:
        # Revoke the access token used for this request.
        if getattr(request, "token_payload", None):
            revoke_token(request.token_payload)

        # Revoke the refresh token if the client supplies it.
        refresh = (getattr(request, "json_data", None) or {}).get("refresh_token")
        if refresh:
            verified, payload = validate_jwt_token(refresh)
            if verified:
                revoke_token(payload)

        return APIResponse.success(message="Logged out successfully")
    except Exception as e:
        logger.error(f"Logout view error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def refresh_token(request):
    """Refresh access token using refresh token"""
    try:
        data = request.json_data

        if "refresh_token" not in data:
            return APIResponse.bad_request("refresh_token is required")

        refresh_token = data["refresh_token"]
        verified, payload = validate_jwt_token(refresh_token)

        if not verified:
            return APIResponse.unauthorized("Invalid or expired refresh token")

        # Only refresh tokens may be exchanged here (an access token must not work).
        if payload.get("type") != "refresh":
            return APIResponse.unauthorized("Invalid token type")

        user_id = payload.get("user_id")
        if not user_id:
            return APIResponse.unauthorized("Invalid token payload")

        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            return APIResponse.unauthorized("User not found or inactive")

        # Refresh-token rotation: revoke the presented refresh token so it cannot
        # be replayed, then issue a fresh pair.
        revoke_token(payload)

        access_token = generate_jwt_token(user, "access")
        new_refresh_token = generate_jwt_token(user, "refresh")

        return APIResponse.success(
            data={
                "access_token": access_token,
                "refresh_token": new_refresh_token,
            },
            message="Tokens refreshed successfully",
        )

    except Exception as e:
        logger.error(f"Token refresh error: {str(e)}")
        return APIResponse.server_error()