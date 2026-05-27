"""
User Order Views - Customer-facing order endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.db import transaction
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, json_request_required, jwt_optional
from apps.users.utils.auth_utils import get_user_or_none
from apps.orders.selectors import get_user_orders, get_order_by_id
from apps.orders.schemas import (
    serialize_order,
    serialize_order_list,
    serialize_order_item,
    validate_order_create,
)
from apps.orders.order_service import OrderService
from apps.users.services.guest_service import GuestCheckoutService

logger = logging.getLogger(__name__)


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, "user") or not request.user:
        return False
    return getattr(request.user, "role", "customer") in ["admin", "staff"]


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def user_orders(request):
    """Get authenticated user's orders"""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 10)), 50)
        status = request.GET.get("status")
        payment_status = request.GET.get("payment_status")

        orders, total = get_user_orders(
            user=request.user,
            page=page,
            limit=limit,
            status=status,
            payment_status=payment_status,
        )

        return APIResponse.success(
            data={
                "orders": serialize_order_list(orders, is_admin=False),
                "total": total,
                "page": page,
                "limit": limit,
            },
            message="Orders retrieved successfully",
        )

    except Exception as e:
        logger.error(f"User orders error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_optional
@json_request_required
def create_order(request):
    """Create a new order - supports both authenticated users and guest checkout"""
    try:
        data = request.json_data
        user = get_user_or_none(request)
        is_authenticated = user is not None and user.is_authenticated

        # Validate input
        cleaned, errors = validate_order_create(data, is_authenticated)
        if errors:
            return APIResponse.validation_error(errors)

        # Validate payment method is provided
        payment_method = cleaned.get("payment_method")
        if not payment_method:
            return APIResponse.validation_error(
                {"payment_method": "Payment method is required"}
            )

        # Start atomic transaction
        with transaction.atomic():
            # Handle user creation/retrieval for guests
            if not is_authenticated:
                guest_info = cleaned.get("guest_info", {})
                
                if not guest_info.get("email"):
                    return APIResponse.validation_error(
                        {"guest_info.email": "Email is required for guest checkout"}
                    )
                if not guest_info.get("first_name") or not guest_info.get("last_name"):
                    return APIResponse.validation_error(
                        {"guest_info.name": "First name and last name are required for guest checkout"}
                    )
                
                guest_user, error = GuestCheckoutService.create_guest_checkout(guest_info)
                
                if error:
                    return APIResponse.validation_error({"guest_info": error})
                
                if isinstance(guest_user, dict):
                    from apps.users.models.user import User
                    guest_user = User.objects.filter(id=guest_user.get('id')).first()
                    if not guest_user:
                        return APIResponse.validation_error({"guest_info": "Failed to create guest user"})
                
                order_user = guest_user
                
                shipping_address = cleaned.get("shipping_address", {})
                if not shipping_address.get("email") and guest_info.get("email"):
                    shipping_address["email"] = guest_info["email"]
                if not shipping_address.get("phone") and guest_info.get("phone"):
                    shipping_address["phone"] = guest_info["phone"]
                if not shipping_address.get("first_name") and guest_info.get("first_name"):
                    shipping_address["first_name"] = guest_info["first_name"]
                if not shipping_address.get("last_name") and guest_info.get("last_name"):
                    shipping_address["last_name"] = guest_info["last_name"]
                
                cleaned["shipping_address"] = shipping_address
            else:
                order_user = user

            order, error = OrderService.create_order(
                user=order_user,
                items=cleaned["items"],
                shipping_address_data=cleaned["shipping_address"],
                payment_method=payment_method,
                guest_info=guest_info if not is_authenticated else None,
                billing_address_data=cleaned.get("billing_address"),
                customer_note=cleaned.get("customer_note", ""),
                currency=cleaned.get("currency", "GHS"),
            )

            if error:
                return APIResponse.validation_error(error)

            response_data = {
                "order": serialize_order(order, is_admin=False),
                "payment_method": payment_method,
                "shipping_cost": float(order.shipping_cost),
            }

            if payment_method == "paystack":
                from apps.orders.paystack_service import PaystackService

                payment_data, pay_error = PaystackService.initialize_transaction(order)
                if pay_error:
                    return APIResponse.validation_error({"payment": pay_error})

                response_data["payment"] = payment_data
                response_data["message"] = "Order created. Please complete payment."

                return APIResponse.created(
                    data=response_data, message="Order created. Redirect to payment."
                )

            elif payment_method in ["pod", "cash_on_delivery"]:
                response_data["message"] = "Order confirmed. You will pay on delivery."
                return APIResponse.created(
                    data=response_data, message="Order confirmed successfully"
                )

            return APIResponse.created(
                data=response_data, message="Order created successfully"
            )

    except Exception as e:
        logger.error(f"Create order error: {str(e)}")
        import traceback
        traceback.print_exc()
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def order_detail(request, order_id):
    """Get order details"""
    try:
        order = get_order_by_id(order_id)
        if not order:
            return APIResponse.not_found("Order not found")

        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to view this order")

        is_admin = _is_admin(request)

        return APIResponse.success(
            data=serialize_order(order, is_admin=is_admin, detailed=True),
            message="Order retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Order detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def order_items(request, order_id):
    """Get items for a specific order"""
    try:
        order = get_order_by_id(order_id)
        if not order:
            return APIResponse.not_found("Order not found")

        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden(
                "You don't have permission to view these items"
            )

        is_admin = _is_admin(request)
        items = [serialize_order_item(item, is_admin) for item in order.items.all()]

        return APIResponse.success(
            data={"items": items}, message="Order items retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Order items error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def cancel_order(request, order_id):
    """Cancel an order"""
    try:
        order, error = OrderService.cancel_order(
            order_id=order_id,
            user=request.user,
            reason=request.json_data.get("reason", ""),
        )

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data={"order": serialize_order(order, is_admin=_is_admin(request))},
            message="Order cancelled successfully",
        )

    except Exception as e:
        logger.error(f"Cancel order error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def order_payment_options(request, order_id):
    """Get available payment options for an order (e.g., for retrying payment)"""
    try:
        order = get_order_by_id(order_id)
        if not order:
            return APIResponse.not_found("Order not found")

        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to view this order")

        payment_options, error = OrderService.get_order_payment_options(order_id)

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data=payment_options, message="Payment options retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Payment options error: {str(e)}")
        return APIResponse.server_error()