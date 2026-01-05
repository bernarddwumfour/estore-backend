"""
orders/views.py

Order views using SHARED APIResponse from estore.utils
"""

import json
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError

# Use SHARED decorators from users
from users.decorators.auth import json_request_required, jwt_required, role_required
from estore.utils.responses import APIResponse  # SHARED RESPONSE
from users.utils.token_utils import validate_jwt_token
from .services.order_service import AddressService, OrderService

logger = logging.getLogger(__name__)


# ==================== ORDER MANAGEMENT (USER) ====================


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def user_orders(request):
    """Get paginated orders for authenticated user"""
    print("HERE")
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 10))
        status = request.GET.get("status")
        payment_status = request.GET.get("payment_status")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        search = request.GET.get("search", "").strip()

        # Get user from request (added by jwt_required decorator)
        user = request.user

        # Get orders from service
        orders, total_count = OrderService.get_user_orders(
            user=user,
            filters={
                "page": page,
                "per_page": limit,
                "status": status,
                "payment_status": payment_status,
                "date_from": date_from,
                "date_to": date_to,
                "search": search,
            },
        )

        # Format orders for response
        orders_data = [OrderService.format_order_summary(order) for order in orders]

        return APIResponse.success(
            data={
                "orders": orders_data,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total_count,
                    "pages": (total_count + limit - 1) // limit,
                },
            },
            message="Your orders retrieved successfully",
        )

    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        return APIResponse.bad_request(f"Invalid query parameter: {str(e)}")
    except Exception as e:
        logger.error(f"User orders error: {str(e)}")
        return APIResponse.server_error("Failed to retrieve orders")


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def order_detail(request, order_id):
    """Get detailed order information"""
    try:
        # Get user from request (if authenticated)
        user = (
            request.user
            if hasattr(request, "user") and request.user.is_authenticated
            else None
        )

        # Get guest email for guest order lookup (if provided)
        guest_email = request.GET.get("guest_email", "")

        # Get order from service
        order = OrderService.get_order(
            order_id=order_id, user=user, guest_email=guest_email
        )

        # Format order for response
        order_data = OrderService.format_order(order)

        return APIResponse.success(
            data={"order": order_data}, message="Order details retrieved successfully"
        )

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Order detail error: {error_msg}")

        if "not found" in error_msg.lower():
            return APIResponse.not_found("Order not found")
        elif (
            "permission" in error_msg.lower()
            or "authentication" in error_msg.lower()
            or "email verification" in error_msg.lower()
        ):
            return APIResponse.forbidden(error_msg)
        else:
            return APIResponse.server_error("Failed to retrieve order details")


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def create_order(request):
    """Create a new order (guest or authenticated user)"""
    try:
        # Parse request data
        data = json.loads(request.body)

        # Get user from JWT token if provided
        user = None

        # Check for Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            try:
                print(auth_header)
                token = auth_header.split(" ")[1]
                # Manually decode JWT to get user
                error, payload = validate_jwt_token(token)
                print("Payload", payload)
                user_id = payload.get("user_id")

                if user_id:
                    from django.contrib.auth import get_user_model

                    User = get_user_model()
                    user = User.objects.get(id=user_id)
            except Exception:
                # Token is invalid, treat as guest
                user = None

        print(f"User: {user}")  # Should show user object or None

        # Create order using service
        order, order_items = OrderService.create_order_from_data(data=data, user=user)

        # Format response
        order_data = OrderService.format_order(order)

        return APIResponse.success(
            data={"order": order_data}, message="Order created successfully"
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except ValidationError as e:
        logger.error(f"Order validation error: {str(e)}")
        return APIResponse.bad_request(str(e))
    except ValueError as e:
        logger.error(f"Order validation error: {str(e)}")
        return APIResponse.bad_request(str(e))
    except Exception as e:
        logger.error(f"Order creation error: {str(e)}")
        return APIResponse.server_error("Failed to create order")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def cancel_order(request, order_id):
    """Cancel an order"""
    try:
        # Get cancellation reason
        data = json.loads(request.body) if request.body else {}
        reason = data.get("reason", "")

        # Cancel order using service
        order = OrderService.cancel_order(
            order_id=order_id, user=request.user, reason=reason
        )

        # Format response
        order_data = OrderService.format_order_summary(order)

        return APIResponse.success(
            data={"order": order_data}, message="Order cancelled successfully"
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Cancel order error: {error_msg}")

        if "not found" in error_msg.lower():
            return APIResponse.not_found("Order not found")
        elif "cannot be cancelled" in error_msg.lower():
            return APIResponse.bad_request(error_msg)
        elif "permission" in error_msg.lower():
            return APIResponse.forbidden(error_msg)
        else:
            return APIResponse.server_error("Failed to cancel order")


# ==================== ADMIN ORDER MANAGEMENT ====================


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_list(request):
    """Get all orders with filtering (admin only)"""
    print("here")
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        status = request.GET.get("status")
        payment_status = request.GET.get("payment_status")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        search = request.GET.get("search", "").strip()

        # Get orders from service
        orders, total_count = OrderService.get_admin_orders(
            filters={
                "page": page,
                "per_page": limit,
                "status": status,
                "payment_status": payment_status,
                "date_from": date_from,
                "date_to": date_to,
                "search": search,
            }
        )

        # Format orders for response
        orders_data = [OrderService.format_order_summary(order) for order in orders]

        return APIResponse.success(
            data={
                "orders": orders_data,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total_count,
                    "pages": (total_count + limit - 1) // limit,
                },
                "filters": {
                    "status": status,
                    "payment_status": payment_status,
                    "date_from": date_from,
                    "date_to": date_to,
                    "search": search,
                },
            },
            message="Orders retrieved successfully",
        )

    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        return APIResponse.bad_request(f"Invalid query parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Admin order list error: {str(e)}")
        return APIResponse.server_error("Failed to retrieve orders")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
def update_order_status(request, order_id):
    """Update order status (admin only)"""
    try:
        # Parse request data
        data = json.loads(request.body)

        status = data.get("status")
        admin_note = data.get("admin_note", "")
        carrier = data.get("carrier", "")

        if not status:
            return APIResponse.bad_request("Status is required")

        # Update order using service
        order = OrderService.update_order_status(
            order_id=order_id,
            status=status,
            admin_note=admin_note,
            carrier=carrier,
        )

        # Format response
        order_data = OrderService.format_order_summary(order)

        return APIResponse.success(
            data={"order": order_data}, message="Order status updated successfully"
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Update order status error: {error_msg}")

        if "not found" in error_msg.lower():
            return APIResponse.not_found("Order not found")
        elif "invalid status" in error_msg.lower():
            return APIResponse.bad_request(error_msg)
        else:
            return APIResponse.server_error("Failed to update order status")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
def update_payment_status(request, order_id):
    """Update payment status (admin only)"""
    try:
        # Parse request data
        data = json.loads(request.body)

        payment_status = data.get("payment_status")
        payment_intent_id = data.get("payment_intent_id", "")
        payment_receipt_url = data.get("payment_receipt_url", "")

        if not payment_status:
            return APIResponse.bad_request("Payment status is required")

        # Update order using service
        order = OrderService.update_payment_status(
            order_id=order_id,
            payment_status=payment_status,
            payment_intent_id=payment_intent_id,
            payment_receipt_url=payment_receipt_url,
        )

        # Format response
        order_data = OrderService.format_order_summary(order)

        return APIResponse.success(
            data={"order": order_data}, message="Payment status updated successfully"
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Update payment status error: {error_msg}")

        if "not found" in error_msg.lower():
            return APIResponse.not_found("Order not found")
        elif "invalid payment status" in error_msg.lower():
            return APIResponse.bad_request(error_msg)
        else:
            return APIResponse.server_error("Failed to update payment status")


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def order_stats(request):
    """Get order statistics (admin only)"""
    try:
        # Get statistics from service
        stats = OrderService.get_order_statistics()

        return APIResponse.success(
            data={"statistics": stats},
            message="Order statistics retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Order stats error: {str(e)}")
        return APIResponse.server_error("Failed to retrieve order statistics")


# ==================== ADDRESS MANAGEMENT ====================


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def get_user_addresses(request):
    """Get addresses for authenticated user"""
    try:
        address_type = request.GET.get("type")  # 'shipping' or 'billing'
        active_only = request.GET.get("active_only", "true").lower() == "true"

        addresses = AddressService.get_user_addresses(
            user=request.user, address_type=address_type, active_only=active_only
        )

        return APIResponse.success(
            data={"addresses": [address.to_dict() for address in addresses]},
            message="Addresses retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Get addresses error: {str(e)}")
        return APIResponse.server_error("Failed to retrieve addresses")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def create_address(request):
    """Create new address for user"""
    try:
        # Parse request data
        data = json.loads(request.body)

        # Validate required fields
        required = [
            "address_type",
            "contact_name",
            "contact_phone",
            "address_line_1",
            "city",
            "postal_code",
            "country",
        ]

        for field in required:
            if field not in data or not data[field]:
                return APIResponse.bad_request(f"Missing required field: {field}")

        address = AddressService.create_address_from_data(
            data=data, user=request.user, address_type=data["address_type"]
        )

        return APIResponse.success(
            data={"address": address.to_dict()}, message="Address created successfully"
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Create address error: {str(e)}")
        return APIResponse.server_error("Failed to create address")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def update_address(request, address_id):
    """Update existing address"""
    try:
        # Parse request data
        data = json.loads(request.body)

        address = AddressService.update_address(
            address_id=address_id, data=data, user=request.user
        )

        return APIResponse.success(
            data={"address": address.to_dict()}, message="Address updated successfully"
        )

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Update address error: {error_msg}")

        if "not found" in error_msg.lower():
            return APIResponse.not_found("Address not found")
        else:
            return APIResponse.server_error("Failed to update address")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
def delete_address(request, address_id):
    """Soft delete address"""
    try:
        AddressService.delete_address(address_id=address_id, user=request.user)

        return APIResponse.success(message="Address deleted successfully")

    except Exception as e:
        error_msg = str(e)
        logger.error(f"Delete address error: {error_msg}")

        if "not found" in error_msg.lower():
            return APIResponse.not_found("Address not found")
        else:
            return APIResponse.server_error("Failed to delete address")


# ==================== PAYMENT VERIFICATION ====================


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def verify_payment(request):
    """Verify payment and update order status"""
    try:
        # Parse request data
        data = json.loads(request.body)

        payment_intent_id = data.get("payment_intent_id")
        order_id = data.get("order_id")
        payment_success = data.get("payment_success", True)
        receipt_url = data.get("receipt_url", "")

        if not payment_intent_id or not order_id:
            return APIResponse.bad_request("Missing payment_intent_id or order_id")

        # Determine payment status
        payment_status = "paid" if payment_success else "failed"

        # Update payment status using service
        order = OrderService.update_payment_status(
            order_id=order_id,
            payment_status=payment_status,
            payment_intent_id=payment_intent_id,
            payment_receipt_url=receipt_url,
        )

        # Format response
        order_data = OrderService.format_order_summary(order)

        message = (
            "Payment verified and order confirmed"
            if payment_success
            else "Payment verification failed"
        )

        return APIResponse.success(data={"order": order_data}, message=message)

    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Payment verification error: {error_msg}")

        if "not found" in error_msg.lower():
            return APIResponse.not_found("Order not found")
        else:
            return APIResponse.server_error("Failed to verify payment")
