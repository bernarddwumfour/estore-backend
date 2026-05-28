"""
users/views.py

Thin views that delegate business logic to services
"""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db.models import Q
from django.urls import reverse

from apps.users.utils.token_utils import generate_jwt_token, validate_jwt_token
from apps.users.models.address import Address
from apps.users.models.user import User
from apps.users.models.affiliate import Affiliate
from .services.password_service import PasswordService
from .decorators.auth import jwt_required, role_required, json_request_required
from estore.utils.responses import APIResponse
from .services.auth_service import AuthService
from .services.verification_service import VerificationService
from .services.guest_service import GuestCheckoutService
from .services.staff_service import StaffService

from .selectors import (
    get_users_filtered,
    get_customers_filtered,
    get_staff_users_filtered,
    get_guest_users_filtered,
    get_affiliates_filtered,
    get_user_statistics as get_user_stats,
    
)
from .schemas import (
    serialize_user_list,
    serialize_customer_list,
    serialize_staff_list,
    serialize_guest_list,
    serialize_affiliate_list,
    serialize_pagination_metadata,
    serialize_user_statistics,
    validate_bulk_user_action,
    serialize_affiliate_user
)

logger = logging.getLogger(__name__)


# ==================== AUTHENTICATION VIEWS ====================
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
def logout(request):
    """User logout - revoke refresh token"""
    try:
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

        user_id = payload.get("user_id")
        if not user_id:
            return APIResponse.unauthorized("Invalid token payload")

        try:
            user = User.objects.get(id=user_id, is_active=True)
        except User.DoesNotExist:
            return APIResponse.unauthorized("User not found or inactive")

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
            "role": user.role,
            "phone": user.phone or "",
            "is_verified": user.email_verified,
            "email_verified": user.email_verified,
            "email_verified_at": (
                user.email_verified_at.isoformat() if user.email_verified_at else None
            ),
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        }

        if default_address:
            profile_data.update({
                "address": default_address.full_address,
                "address_city": default_address.city,
                "address_country": default_address.country,
                "address_postal_code": default_address.postal_code,
                "default_address": default_address.to_dict() if hasattr(default_address, "to_dict") else None,
            })
        else:
            profile_data.update({
                "address": "",
                "address_city": "",
                "address_country": "",
                "address_postal_code": "",
                "default_address": None,
            })

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

        user_allowed_fields = ["username", "first_name", "last_name", "phone"]
        updated = False
        user_updates = {}

        for field in user_allowed_fields:
            if field in data:
                new_value = data[field].strip() if isinstance(data[field], str) else data[field]
                current_value = getattr(user, field, "")

                if field == "username" and new_value != current_value:
                    if User.objects.filter(username=new_value).exclude(id=user.id).exists():
                        return APIResponse.conflict({"username": "This username is already taken"})

                if new_value != current_value:
                    setattr(user, field, new_value)
                    user_updates[field] = new_value
                    updated = True

        address_fields = ["address_line1", "address_line2", "city", "country", "postal_code", "state"]
        address_data = {}

        for field in address_fields:
            if field in data:
                address_data[field] = data[field]

        if address_data:
            default_address = None
            if hasattr(user, "addresses"):
                default_address = user.addresses.filter(is_default=True).first()

            if default_address:
                for field, value in address_data.items():
                    if hasattr(default_address, field):
                        setattr(default_address, field, value)
                default_address.save()
                updated = True
            else:
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
                        return APIResponse.bad_request({"address": "Failed to create address"})

        if user_updates:
            user.save()
            logger.info(f"User {user.email} updated profile fields: {list(user_updates.keys())}")

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

        if not user.check_password(data["current_password"]):
            return APIResponse.unauthorized("Current password is incorrect")

        from .utils.validators import UserValidators
        is_valid, error, _ = UserValidators.validate_password_strength(data["new_password"])
        if not is_valid:
            return APIResponse.validation_error({"new_password": error})

        user.set_password(data["new_password"])
        user.save()

        logger.info(f"User {user.email} changed password")

        return APIResponse.success(message="Password changed successfully")

    except Exception as e:
        logger.error(f"Change password error: {str(e)}")
        return APIResponse.server_error()


# ==================== PASSWORD RESET VIEWS ====================

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


# ==================== EMAIL VERIFICATION VIEWS ====================

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


# ==================== GUEST CHECKOUT VIEWS ====================

@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def guest_checkout(request):
    """Guest checkout endpoint - Creates or retrieves a guest user for checkout"""
    try:
        data = request.json_data
        guest_data, error = GuestCheckoutService.create_guest_checkout(data)

        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(guest_data, "Guest checkout prepared successfully")

    except Exception as e:
        logger.error(f"Guest checkout error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def guest_convert(request):
    """Convert guest user to registered user"""
    try:
        data = request.json_data

        required_fields = ["email", "password"]
        for field in required_fields:
            if field not in data:
                return APIResponse.bad_request(f"{field} is required")

        user_data, error = GuestCheckoutService.convert_guest_to_registered(
            email=data["email"],
            password=data["password"],
            first_name=data.get("first_name"),
            last_name=data.get("last_name"),
            phone=data.get("phone"),
        )

        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(user_data, "Account created successfully. Please verify your email.")

    except Exception as e:
        logger.error(f"Guest convert error: {str(e)}")
        return APIResponse.server_error()


# ==================== ADMIN USER MANAGEMENT VIEWS ====================

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


# ==================== AFFILIATE MANAGEMENT VIEWS ====================

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


# ==================== USER STATISTICS VIEW ====================

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin")
def user_statistics(request):
    """Admin: Get user statistics for dashboard"""
    try:
        stats = get_user_stats()

        return APIResponse.success(
            data=serialize_user_statistics(stats),
            message="User statistics retrieved successfully"
        )

    except Exception as e:
        logger.error(f"User statistics error: {str(e)}")
        return APIResponse.server_error()


# ==================== BULK USER ACTION VIEW ====================

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