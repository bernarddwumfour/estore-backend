"""
Guest Views - Guest checkout functionality
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import json_request_required
from apps.users.services.guest_service import GuestCheckoutService

logger = logging.getLogger(__name__)


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