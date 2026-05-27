"""
Address Views - User address management endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, json_request_required
from apps.orders.schemas import (
    serialize_address,
    validate_address_create,
    validate_address_update,
)
from apps.orders.order_service import AddressService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def get_user_addresses(request):
    """Get user's addresses"""
    try:
        address_type = request.GET.get("type")
        active_only = request.GET.get("active_only", "true").lower() == "true"

        addresses = AddressService.get_user_addresses(
            user=request.user,
            address_type=address_type,
            active_only=active_only,
        )

        return APIResponse.success(
            data={
                "addresses": [
                    serialize_address(addr, is_admin=False) for addr in addresses
                ]
            },
            message="Addresses retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Get addresses error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def create_address(request):
    """Create a new address"""
    try:
        data = request.json_data

        # Validate input
        cleaned, errors = validate_address_create(data)
        if errors:
            return APIResponse.validation_error(errors)

        address, error = AddressService.create_address(
            user=request.user,
            address_type=cleaned["address_type"],
            first_name=cleaned["first_name"],
            last_name=cleaned["last_name"],
            phone=cleaned["phone"],
            email=cleaned["email"],
            address_line1=cleaned["address_line1"],
            city=cleaned["city"],
            state=cleaned["state"],
            postal_code=cleaned["postal_code"],
            country=cleaned["country"],
            company=cleaned.get("company", ""),
            address_line2=cleaned.get("address_line2", ""),
            instructions=cleaned.get("instructions", ""),
            is_default=cleaned.get("is_default", False),
        )

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.created(
            data={"address": serialize_address(address)},
            message="Address created successfully",
        )

    except Exception as e:
        logger.error(f"Create address error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@json_request_required
def update_address(request, address_id):
    """Update an address"""
    try:
        data = request.json_data

        # Validate input
        cleaned, errors = validate_address_update(data)
        if errors:
            return APIResponse.validation_error(errors)

        address, error = AddressService.update_address(
            address_id=address_id, user=request.user, **cleaned
        )

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data={"address": serialize_address(address)},
            message="Address updated successfully",
        )

    except Exception as e:
        logger.error(f"Update address error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
def delete_address(request, address_id):
    """Delete an address"""
    try:
        success, error = AddressService.delete_address(
            address_id=address_id,
            user=request.user,
        )

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(message="Address deleted successfully")

    except Exception as e:
        logger.error(f"Delete address error: {str(e)}")
        return APIResponse.server_error()