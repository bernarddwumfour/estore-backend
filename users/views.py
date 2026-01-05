"""
users/views.py

Thin views that delegate business logic to services
"""

import json
import logging
from datetime import datetime, timedelta

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q  # ADD THIS IMPORT

from users.utils.token_utils import generate_jwt_token, validate_jwt_token
from users.models.address import Address
from .services.password_service import PasswordService
from .decorators.auth import jwt_required, role_required, json_request_required
from estore.utils.responses import APIResponse
from .services.auth_service import AuthService
from .models.user import User
from .services.verification_service import VerificationService
from django.urls import reverse

logger = logging.getLogger(__name__)


# ==================== AUTHENTICATION VIEWS ====================
@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def register_customer(request):
    """Customer self-registration endpoint"""
    try:
        data = request.json_data

        # Delegate to service layer
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

        # Delegate to service layer
        user_data, errors = AuthService.register_user(data, request)

        if errors:
            return APIResponse.validation_error(errors)

        return APIResponse.created(user_data, "User created successfully")

    except Exception as e:
        logger.error(f"Admin user registration error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def login(request):
    """User login"""
    try:
        data = request.json_data

        # Validate required fields
        required_fields = ["email", "password"]
        for field in required_fields:
            if field not in data or not data[field]:
                return APIResponse.bad_request(f"{field} is required")

        # Delegate to service layer
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
def logout(request):
    """User logout - revoke refresh token"""
    try:
        # In a real implementation, you'd revoke the refresh token
        # For now, just return success
        return APIResponse.success(message="Logged out successfully")
    except Exception as e:
        logger.error(f"Logout view error: {str(e)}")
        return APIResponse.server_error()


# users/views/auth.py or wherever your auth views are


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

        # Verify the refresh token
        print("here")
        verified, payload = validate_jwt_token(refresh_token)
        if not verified:
            return APIResponse.unauthorized("Invalid or expired refresh token")

        # Get user from token
        user_id = payload.get("user_id")
        if not user_id:
            return APIResponse.unauthorized("Invalid token payload")

        # Get user
        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            return APIResponse.unauthorized("User not found or inactive")

        # Generate new tokens
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


# ==================== USER PROFILE VIEWS ====================


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def get_profile(request):
    """Get current user profile"""
    try:
        user = request.user

        # Get the user's default address if exists
        default_address = None
        if hasattr(user, "addresses"):
            default_address = user.addresses.filter(is_default=True).first()

        profile_data = {
            "id": str(user.id),
            "email": user.email,
            "username": user.username or "",
            "first_name": user.first_name or "",
            "last_name": user.last_name or "",
            "full_name": user.full_name,
            "role": user.role,  # Fixed: was 'rolse'
            "phone": user.phone or "",
            "is_verified": user.email_verified,  # Changed: was is_verified property
            "email_verified": user.email_verified,
            "email_verified_at": (
                user.email_verified_at.isoformat() if user.email_verified_at else None
            ),
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }

        # Add address data if exists
        if default_address:
            profile_data.update(
                {
                    "address": default_address.full_address,
                    "address_city": default_address.city,
                    "address_country": default_address.country,
                    "address_postal_code": default_address.postal_code,
                    "default_address": (
                        default_address.to_dict()
                        if hasattr(default_address, "to_dict")
                        else None
                    ),
                }
            )
        else:
            profile_data.update(
                {
                    "address": "",
                    "address_city": "",
                    "address_country": "",
                    "address_postal_code": "",
                    "default_address": None,
                }
            )

        return APIResponse.success(profile_data)

    except Exception as e:
        logger.error(f"Get profile error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@json_request_required
def update_profile(request):
    """Update user profile"""
    try:
        user = request.user
        data = request.json_data

        # List of allowed fields for update on User model
        user_allowed_fields = [
            "username",
            "first_name",
            "last_name",
            "phone",
        ]

        updated = False
        user_updates = {}

        # Update User model fields
        for field in user_allowed_fields:
            if field in data:
                new_value = (
                    data[field].strip() if isinstance(data[field], str) else data[field]
                )
                current_value = getattr(user, field, "")

                # Check if username is unique (if changing)
                if field == "username" and new_value != current_value:
                    if (
                        User.objects.filter(username=new_value)
                        .exclude(id=user.id)
                        .exists()
                    ):
                        return APIResponse.conflict(
                            {"username": "This username is already taken"}
                        )

                # Update if changed
                if new_value != current_value:
                    setattr(user, field, new_value)
                    user_updates[field] = new_value
                    updated = True

        # Handle address updates (create or update default address)
        address_fields = [
            "address_line1",
            "address_line2",
            "city",
            "country",
            "postal_code",
            "state",
        ]
        address_data = {}

        for field in address_fields:
            if field in data:
                address_data[field] = data[field]

        if address_data:
            # Check if user has a default address
            default_address = None
            if hasattr(user, "addresses"):
                default_address = user.addresses.filter(is_default=True).first()

            if default_address:
                # Update existing default address
                for field, value in address_data.items():
                    if hasattr(default_address, field):
                        setattr(default_address, field, value)
                default_address.save()
                updated = True
            else:
                # Create new default address with minimum required fields
                required_fields = ["address_line1", "city", "country", "postal_code"]
                if all(field in address_data for field in required_fields):
                    try:
                        Address.objects.create(
                            user=user,
                            address_type=Address.ADDRESS_TYPE_SHIPPING,
                            first_name=user.first_name or "",
                            last_name=user.last_name or "",
                            phone=user.phone or "",
                            email=user.email,
                            address_line1=address_data.get("address_line1", ""),
                            address_line2=address_data.get("address_line2", ""),
                            city=address_data.get("city", ""),
                            state=address_data.get("state", ""),
                            postal_code=address_data.get("postal_code", ""),
                            country=address_data.get("country", ""),
                            is_default=True,
                            is_active=True,
                        )
                        updated = True
                    except Exception as e:
                        logger.error(f"Address creation error: {str(e)}")
                        return APIResponse.bad_request(
                            {"address": "Failed to create address"}
                        )

        if user_updates:
            user.save()
            logger.info(
                f"User {user.email} updated profile fields: {list(user_updates.keys())}"
            )

        return APIResponse.success(
            message="Profile updated successfully",
            data={"updated_fields": list(user_updates.keys())} if updated else {},
        )

    except Exception as e:
        logger.error(f"Update profile error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def change_password(request):
    """Change user password"""
    try:
        user = request.user
        data = request.json_data

        required_fields = ["current_password", "new_password"]
        for field in required_fields:
            if field not in data:
                return APIResponse.bad_request(f"{field} is required")

        # Verify current password
        if not user.check_password(data["current_password"]):
            return APIResponse.unauthorized("Current password is incorrect")

        # Validate new password strength
        from .utils.validators import UserValidators

        is_valid, error, _ = UserValidators.validate_password_strength(
            data["new_password"]
        )
        if not is_valid:
            return APIResponse.validation_error({"new_password": error})

        # Set new password
        user.set_password(data["new_password"])
        user.save()

        logger.info(f"User {user.email} changed password")

        # TODO: Invalidate all existing tokens (optional security measure)

        return APIResponse.success(message="Password changed successfully")

    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        return APIResponse.server_error()


"""
Add to users/views.py
"""


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def password_reset_request(request):
    """Request password reset"""
    try:
        data = request.json_data

        if "email" not in data or not data["email"]:
            return APIResponse.bad_request("Email required")

        success, token = PasswordService.request_reset(data["email"], request)

        if not success:
            return APIResponse.bad_request(token)

        return APIResponse.success(
            message=f"Reset link sent to email address provided token : {token}"
        )

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

        success, error = PasswordService.reset_password(
            data["token"], data["new_password"], request
        )

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


# ==================== ADMIN VIEWS ====================


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def list_users(request):
    """Admin: List all users (paginated)"""
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        role = request.GET.get("role")
        is_active = request.GET.get("is_active")
        search = request.GET.get("search", "").strip()

        # Build query
        query = {}
        if role:
            query["role"] = role
        if is_active is not None:
            query["is_active"] = is_active.lower() == "true"

        # Base queryset
        users = User.objects.filter(**query)

        # Search
        if search:
            users = users.filter(
                Q(email__icontains=search)
                | Q(username__icontains=search)
                | Q(phone__icontains=search)
            )

        # Pagination
        total = users.count()
        offset = (page - 1) * limit
        users = users.order_by("-date_joined")[offset : offset + limit]

        # Prepare response
        users_data = []
        for user in users:
            users_data.append(
                {
                    "id": str(user.id),
                    "first_name": user.first_name,
                    "last_name": user.last_name,
                    "email": user.email,
                    "username": user.username,
                    "role": user.role,
                    "is_active": user.is_active,
                    "email_verified": user.email_verified,
                    "date_joined": (
                        user.date_joined.isoformat() if user.date_joined else None
                    ),
                    "last_login": (
                        user.last_login.isoformat() if user.last_login else None
                    ),
                }
            )

        response_data = {
            "users": users_data,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": (total + limit - 1) // limit,
            },
        }

        return APIResponse.success(response_data)

    except Exception as e:
        logger.error(f"List users error: {str(e)}")
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
            # Return user details
            user_data = {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "role": user.role,
                "phone": user.phone,
                # 'address': user.address,
                # 'city': user.city,
                # 'country': user.country,
                # 'postal_code': user.postal_code,
                "is_active": user.is_active,
                "email_verified": user.email_verified,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "date_joined": (
                    user.date_joined.isoformat() if user.date_joined else None
                ),
                "last_login": user.last_login.isoformat() if user.last_login else None,
                # 'email_verified_at': user.email_verified_at.isoformat() if user.email_verified_at else None
            }
            return APIResponse.success(user_data)

        elif request.method == "PUT" or request.method == "PATCH":
            # Update user
            data = json.loads(request.body)

            # Prevent modifying certain fields
            restricted_fields = ["password", "email", "id"]
            for field in restricted_fields:
                if field in data:
                    return APIResponse.bad_request(
                        f"Cannot modify {field} through this endpoint"
                    )

            # Update allowed fields
            allowed_fields = [
                "role",
                "is_active",
                "is_staff",
                "phone",
                "address",
                "city",
                "country",
                "postal_code",
            ]
            for field in allowed_fields:
                if field in data:
                    setattr(user, field, data[field])

            user.save()
            logger.info(f"Admin updated user {user.email}")
            return APIResponse.success(message="User updated successfully")

        elif request.method == "DELETE":
            # Soft delete (deactivate) user
            user.is_active = False
            user.save()
            logger.warning(f"Admin deactivated user {user.email}")
            return APIResponse.success(message="User deactivated successfully")

    except Exception as e:
        logger.error(f"User detail error: {str(e)}")
        return APIResponse.server_error()


# ==================== EMAIL VERIFICATION VIEWS ====================


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def verify_email(request):
    """
    API endpoint to verify email using token
    Returns JSON response only
    """
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
                    "email_verified_at": (
                        user.email_verified_at.isoformat()
                        if user.email_verified_at
                        else None
                    ),
                    "username": user.username,
                    "user_id": str(user.id),
                },
            }
            return JsonResponse(response_data, status=200)
        else:
            return JsonResponse(
                {
                    "success": False,
                    "error": message,
                    "resend_url": reverse("resend-verification"),
                },
                status=400,
            )

    except Exception as e:
        logger.error(f"Email verification API error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "Email verification failed"}, status=500
        )


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def validate_verification_token(request):
    """
    Validate verification token without using it
    Useful for checking token validity before form submission
    """
    try:
        data = request.json_data

        if "token" not in data or not data["token"]:
            return APIResponse.bad_request("Token is required")

        valid, user, message = VerificationService.validate_token(data["token"])

        if valid:
            return APIResponse.success(
                {
                    "valid": True,
                    "user_email": user.email,
                    "user_id": str(user.id),
                    "message": message,
                }
            )
        else:
            return APIResponse.success({"valid": False, "message": message})

    except Exception as e:
        logger.error(f"Token validation API error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def resend_verification(request):
    """
    API endpoint to resend verification email
    """
    try:
        data = request.json_data

        if "email" not in data or not data["email"]:
            return APIResponse.bad_request("Email is required")

        # Simple email format validation
        if "@" not in data["email"] or "." not in data["email"]:
            return APIResponse.validation_error({"email": "Invalid email format"})

        success, message = VerificationService.resend_verification_email(
            data["email"], request
        )

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
    """
    API endpoint for authenticated user to request verification email
    User requests verification for THEIR OWN email
    """
    try:
        user = request.user  # Get authenticated user from JWT token

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
@require_http_methods(["GET"])  # Changed from POST to GET
@jwt_required
def check_verification_status(request):
    """
    API endpoint to check verification status of authenticated user
    No request body needed - uses JWT token to identify user
    """
    try:
        user = request.user  # Get user from JWT token

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
    """
    Admin API: Check verification status of any user
    """
    try:
        user = get_object_or_404(User, id=user_id)

        status = VerificationService.get_verification_status(user.id)

        if status:
            return APIResponse.success(
                {
                    **status,
                    "user": {
                        "id": str(user.id),
                        "email": user.email,
                        "username": user.username,
                        "role": user.role,
                    },
                }
            )
        else:
            return APIResponse.not_found("User not found")

    except Exception as e:
        logger.error(f"Admin check verification error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def password_reset_request(request):
    """Request password reset - sends email with reset link"""
    try:
        data = request.json_data

        if "email" not in data or not data["email"]:
            return APIResponse.bad_request("Email is required")

        # Validate email format
        from .utils.validators import UserValidators

        if not UserValidators.validate_email_format(data["email"]):
            return APIResponse.validation_error({"email": "Invalid email format"})

        # Delegate to service layer
        success, message = PasswordService.request_reset(data["email"], request)

        if not success:
            return APIResponse.bad_request(message)

        return APIResponse.success(message=message)

    except Exception as e:
        logger.error(f"Password reset request error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def password_reset_confirm(request):
    """Reset password with token"""
    try:
        data = request.json_data

        required_fields = ["token", "new_password"]
        for field in required_fields:
            if field not in data or not data[field]:
                return APIResponse.bad_request(f"{field} is required")

        # Delegate to service layer
        success, error = PasswordService.reset_password(
            data["token"], data["new_password"], request
        )

        if not success:
            return APIResponse.bad_request(error)

        return APIResponse.success(message="Password reset successful")

    except Exception as e:
        logger.error(f"Password reset confirm error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def password_reset_validate(request):
    """Validate reset token"""
    try:
        data = request.json_data

        if "token" not in data or not data["token"]:
            return APIResponse.bad_request("Token is required")

        # Delegate to service layer
        valid, error, user = PasswordService.validate_token(data["token"])

        if not valid:
            return APIResponse.bad_request(error)

        return APIResponse.success(
            {"valid": True, "user_email": user.email, "user_id": str(user.id)}
        )

    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        return APIResponse.server_error()
