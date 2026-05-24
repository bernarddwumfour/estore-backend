"""
users/decorators/auth.py

Authentication and authorization decorators for views
"""

import json
from functools import wraps
from django.views.decorators.csrf import csrf_exempt

from apps.users.utils.token_utils import validate_jwt_token
from estore.utils.responses import APIResponse
from ..models.user import User


def jwt_required(view_func):
    """
    Decorator to require valid JWT token for view access
    Usage: @jwt_required
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get("Authorization", "")

        if not auth_header.startswith("Bearer "):
            return APIResponse.unauthorized("Bearer token required")

        token = auth_header.split(" ")[1]

        # Validate token
        is_validated, payload = validate_jwt_token(token)
        if not is_validated:
            return APIResponse.unauthorized(payload)

        # Verify token type is access
        if payload.get("type") != "access":
            return APIResponse.unauthorized("Invalid token type")

        # Get user from database
        try:
            user = User.objects.get(id=payload["user_id"])
            if not user.is_active:
                return APIResponse.forbidden("Account is deactivated")

            # Attach user to request for easy access in views
            request.user = user
            request.token_payload = payload

            return view_func(request, *args, **kwargs)

        except User.DoesNotExist:
            return APIResponse.unauthorized("User not found")
        except Exception as e:
            return APIResponse.server_error()

    return wrapper


def jwt_optional(view_func):
    """
    Decorator that attempts to validate JWT token but doesn't require it
    If token is valid, user is attached to request
    If token is invalid or missing, request.user remains None
    Usage: @jwt_optional
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Initialize user as None
        request.user = None
        request.token_payload = None

        # Get token from Authorization header
        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

            # Validate token
            is_validated, payload = validate_jwt_token(token)
            
            if is_validated and payload.get("type") == "access":
                try:
                    user = User.objects.get(id=payload["user_id"])
                    if user.is_active:
                        # Attach User object to request
                        request.user = user
                        request.token_payload = payload
                except User.DoesNotExist:
                    # User not found, but that's okay - they're just not authenticated
                    request.user = None
                except Exception:
                    # Any other error, just continue as unauthenticated
                    request.user = None
        else:
            # No token provided, user remains None
            request.user = None

        return view_func(request, *args, **kwargs)

    return wrapper



def role_required(*allowed_roles):
    """
    Decorator to require specific user role(s)
    Usage: @role_required('admin', 'staff')
    """

    def decorator(view_func):
        @wraps(view_func)
        @jwt_required
        def wrapper(request, *args, **kwargs):
            if not hasattr(request, "user"):
                return APIResponse.unauthorized()

            user = request.user

            if user.role not in allowed_roles:
                return APIResponse.forbidden(
                    f"Required role: {', '.join(allowed_roles)}. Your role: {user.role}"
                )

            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def json_request_required(view_func):
    """
    Decorator for views that require JSON request body
    """

    @wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        if request.method in ["POST", "PUT", "PATCH"]:
            if request.content_type != "application/json":
                return APIResponse.bad_request("Content-Type must be application/json")

            try:
                if request.body:
                    request.json_data = json.loads(request.body)
                else:
                    request.json_data = {}
            except json.JSONDecodeError:
                return APIResponse.bad_request("Invalid JSON data")

        return view_func(request, *args, **kwargs)

    return wrapper


def multipart_request_allowed(view_func):
    """
    Decorator for views that accept multipart/form-data
    """

    @wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.content_type

            if not (
                content_type == "application/json"
                or content_type.startswith("multipart/form-data")
            ):
                return APIResponse.bad_request(
                    "Content-Type must be application/json or multipart/form-data"
                )

            # Handle JSON
            if content_type == "application/json":
                try:
                    if request.body:
                        request.json_data = json.loads(request.body)
                    else:
                        request.json_data = {}
                    request.files_data = {}
                except json.JSONDecodeError:
                    return APIResponse.bad_request("Invalid JSON data")

            # Handle multipart
            elif content_type.startswith("multipart/form-data"):
                # Parse form data
                request.json_data = request.POST.dict()
                request.files_data = request.FILES

                # Auto-parse JSON strings in form data
                for key, value in request.json_data.items():
                    if isinstance(value, str) and value.strip():
                        # Check if it looks like JSON
                        if (value.startswith("{") and value.endswith("}")) or (
                            value.startswith("[") and value.endswith("]")
                        ):
                            try:
                                request.json_data[key] = json.loads(value)
                            except (json.JSONDecodeError, TypeError):
                                pass  # Keep as string

        return view_func(request, *args, **kwargs)

    return wrapper


def rate_limit(key_func=None, rate="100/hour", method=None):
    """
    Basic rate limiting decorator (placeholder for actual implementation)
    In production, use django-ratelimit or similar
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # TODO: Implement actual rate limiting
            # For now, just pass through
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator