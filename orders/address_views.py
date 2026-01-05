# views/address_views.py
import json
from django.http import JsonResponse
from django.views.decorators.http import (
    require_http_methods,
    require_POST,
    require_GET,
)
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from orders.services.order_service import AddressService
from users.decorators.auth import json_request_required


@login_required
@require_GET
@json_request_required
def get_user_addresses(request):
    """
    Get addresses for authenticated user
    GET /api/addresses/
    """
    try:
        address_type = request.GET.get("type")  # 'shipping' or 'billing'
        active_only = request.GET.get("active_only", "true").lower() == "true"

        addresses = AddressService.get_user_addresses(
            user=request.user, address_type=address_type, active_only=active_only
        )

        response_data = {
            "success": True,
            "addresses": [address.to_dict() for address in addresses],
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
@json_request_required
def create_address(request):
    """
    Create new address for user
    POST /api/addresses/create/
    """
    try:
        data = json.loads(request.body)

        # Validate required fields
        required = [
            "address_type",
            "first_name",
            "last_name",
            "address_line1",
            "city",
            "state",
            "postal_code",
            "country",
            "phone",
            "email",
        ]

        for field in required:
            if field not in data or not data[field]:
                return JsonResponse(
                    {"success": False, "error": f"Missing required field: {field}"},
                    status=400,
                )

        address = AddressService.create_address_from_data(
            data=data, user=request.user, address_type=data["address_type"]
        )

        response_data = {
            "success": True,
            "address": address.to_dict(),
            "message": "Address created successfully",
        }

        return JsonResponse(response_data, status=201)

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
@json_request_required
def update_address(request, address_id):
    """
    Update existing address
    POST /api/addresses/<address_id>/update/
    """
    try:
        data = json.loads(request.body)

        address = AddressService.update_address(
            address_id=address_id, data=data, user=request.user
        )

        response_data = {
            "success": True,
            "address": address.to_dict(),
            "message": "Address updated successfully",
        }

        return JsonResponse(response_data)

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
@json_request_required
def delete_address(request, address_id):
    """
    Soft delete address
    POST /api/addresses/<address_id>/delete/
    """
    try:
        success = AddressService.delete_address(
            address_id=address_id, user=request.user
        )

        response_data = {"success": True, "message": "Address deleted successfully"}

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required
@require_POST
@json_request_required
def set_default_address(request, address_id):
    """
    Set address as default for its type
    POST /api/addresses/<address_id>/set-default/
    """
    try:
        address = AddressService.update_address(
            address_id=address_id, data={"is_default": True}, user=request.user
        )

        response_data = {
            "success": True,
            "address": address.to_dict(),
            "message": "Address set as default",
        }

        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
