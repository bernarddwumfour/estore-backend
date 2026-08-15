"""
Authentication Views - Login, registration, logout, token refresh
"""

import logging
import time
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
from apps.common.logging import log_action, LogSeverity

logger = logging.getLogger(__name__)
APP_NAME = "users"


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def register_customer(request):
    """Customer self-registration endpoint - converts guest users to registered users"""
    start_time = time.time()
    action = "customer_register"

    try:
        data = request.json_data
        log_action(
            logger=logger, severity=LogSeverity.DEBUG, action=action,
            description="Customer registration attempt", status_code=0,
            request=request, app_name=APP_NAME,
            extra={"email": data.get("email", "unknown"), "start_time": start_time},
        )

        user_data, errors = AuthService.register_customer(data, request)

        if errors:
            return APIResponse.validation_error(errors)

        log_action(
            logger=logger, severity=LogSeverity.INFO, action=action,
            description=f"Customer registered: {data.get('email', 'unknown')}", status_code=201,
            request=request, app_name=APP_NAME,
            extra={"email": data.get("email"), "user_id": user_data.get("id")},
        )
        return APIResponse.created(user_data, "Registration successful")

    except Exception as e:
        logger.error(f"Customer registration view error: {str(e)}")
        log_action(
            logger=logger, severity=LogSeverity.ERROR, action=action,
            description=f"Registration error: {str(e)}", status_code=500,
            request=request, app_name=APP_NAME, extra={"error": str(e)},
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def register_user(request):
    """Admin/Staff user registration (with role selection)"""
    start_time = time.time()
    action = "admin_user_register"

    try:
        data = request.json_data
        log_action(
            logger=logger, severity=LogSeverity.DEBUG, action=action,
            description="Admin user registration", status_code=0,
            request=request, app_name=APP_NAME,
            extra={"email": data.get("email", "unknown"), "start_time": start_time},
        )

        user_data, errors = AuthService.register_user(data, request)

        if errors:
            return APIResponse.validation_error(errors)

        log_action(
            logger=logger, severity=LogSeverity.INFO, action=action,
            description=f"Admin created user: {data.get('email', 'unknown')}", status_code=201,
            user=getattr(request, 'user', None), request=request, app_name=APP_NAME,
            extra={"email": data.get("email"), "new_user_id": user_data.get("id")},
        )
        return APIResponse.created(user_data, "User created successfully")

    except Exception as e:
        logger.error(f"Admin user registration error: {str(e)}")
        log_action(
            logger=logger, severity=LogSeverity.ERROR, action=action,
            description=f"Registration error: {str(e)}", status_code=500,
            request=request, app_name=APP_NAME, extra={"error": str(e)},
        )
        return APIResponse.server_error()


def _handle_login(request, action, allowed_roles):
    """Shared login flow for the customer and staff login endpoints."""
    start_time = time.time()
    email = (request.json_data or {}).get("email", "unknown") if hasattr(request, "json_data") else "unknown"

    log_action(
        logger=logger, severity=LogSeverity.DEBUG, action=action,
        description=f"Login attempt for {email}", status_code=0,
        request=request, app_name=APP_NAME,
        extra={"email": email, "start_time": start_time},
    )

    try:
        data = request.json_data

        required_fields = ["email", "password"]
        for field in required_fields:
            if field not in data or not data[field]:
                return APIResponse.bad_request(f"{field} is required")

        auth_data, error = AuthService.authenticate_user(
            data["email"], data["password"], request, allowed_roles=allowed_roles
        )

        if error:
            log_action(
                logger=logger, severity=LogSeverity.WARNING, action=action,
                description=f"Failed login for {email}: {error}", status_code=401,
                request=request, app_name=APP_NAME,
                extra={"email": email, "reason": error},
            )
            return APIResponse.unauthorized(error)

        log_action(
            logger=logger, severity=LogSeverity.INFO, action=action,
            description=f"User {email} logged in successfully", status_code=200,
            user=auth_data.get("user") if isinstance(auth_data, dict) else None,
            request=request, app_name=APP_NAME,
            extra={"email": email, "user_id": auth_data.get("user", {}).get("id") if isinstance(auth_data, dict) else None},
        )
        return APIResponse.success(auth_data, "Login successful")

    except Exception as e:
        logger.error(f"Login view error: {str(e)}")
        log_action(
            logger=logger, severity=LogSeverity.ERROR, action=action,
            description=f"Login error: {str(e)}", status_code=500,
            request=request, app_name=APP_NAME,
            extra={"email": email, "error": str(e)},
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@ratelimit(key="post:email", rate="10/h", method="POST", block=True)
@json_request_required
def login(request):
    """Customer login - staff/admin credentials are rejected here."""
    return _handle_login(request, "customer_login", allowed_roles=[User.ROLE_CUSTOMER])


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key="ip", rate="5/m", method="POST", block=True)
@ratelimit(key="post:email", rate="10/h", method="POST", block=True)
@json_request_required
def staff_login(request):
    """Staff/admin login - customer credentials are rejected here."""
    return _handle_login(request, "staff_login", allowed_roles=[User.ROLE_STAFF, User.ROLE_ADMIN])


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def logout(request):
    """User logout - revoke the current access token and the supplied refresh token."""
    start_time = time.time()
    action = "user_logout"
    user = getattr(request, 'user', None)

    log_action(
        logger=logger, severity=LogSeverity.DEBUG, action=action,
        description="Logout attempt", status_code=0,
        user=user, request=request, app_name=APP_NAME,
        extra={"start_time": start_time},
    )

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

        log_action(
            logger=logger, severity=LogSeverity.INFO, action=action,
            description="User logged out successfully", status_code=200,
            user=user, request=request, app_name=APP_NAME,
        )
        return APIResponse.success(message="Logged out successfully")
    except Exception as e:
        logger.error(f"Logout view error: {str(e)}")
        log_action(
            logger=logger, severity=LogSeverity.ERROR, action=action,
            description=f"Logout error: {str(e)}", status_code=500,
            request=request, app_name=APP_NAME, extra={"error": str(e)},
        )
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