"""
Profile Views - User profile management
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, json_request_required
from apps.users.models.address import Address
from apps.users.models.user import User

logger = logging.getLogger(__name__)


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

        from apps.users.utils.validators import UserValidators
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