# apps/orders/views.py
import logging
import csv
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.http import JsonResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required,jwt_optional
from apps.users.services.guest_service import GuestCheckoutService
from estore.utils.responses import APIResponse
from decimal import Decimal

from django.conf import settings

from apps.orders.selectors import (
    get_user_orders, get_order_statistics,
    get_order_by_id, get_order_transactions, get_refundable_amount,
)
from apps.orders.schemas import (
    serialize_order, serialize_order_list, serialize_order_item, serialize_address,
    validate_order_create, validate_order_status_update,
    validate_payment_status_update, validate_address_create,
    validate_address_update,  validate_shipment_update,
    validate_refund_request
)

from apps.orders.order_service import OrderService, AddressService
from apps.orders.models import Order, OrderItem, Transaction, Shipment
from apps.orders.shipment_service import ShipmentService
from apps.orders.transaction_service import TransactionService
from django.db import transaction
from apps.users.utils.auth_utils import get_user_or_none

# apps/orders/views.py - Add these imports at the top


logger = logging.getLogger(__name__)


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, "user") or not request.user:
        return False
    return getattr(request.user, "role", "customer") in ["admin", "staff"]


# ==================== USER ORDER VIEWS ====================


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
                # Get dedicated guest info (not from shipping address)
                guest_info = cleaned.get("guest_info", {})
                
                # Validate guest info has required fields (should already be validated)
                if not guest_info.get("email"):
                    return APIResponse.validation_error(
                        {"guest_info.email": "Email is required for guest checkout"}
                    )
                if not guest_info.get("first_name") or not guest_info.get("last_name"):
                    return APIResponse.validation_error(
                        {"guest_info.name": "First name and last name are required for guest checkout"}
                    )
                
                # Create or retrieve guest user - THIS RETURNS A USER OBJECT, NOT A DICT
                guest_user, error = GuestCheckoutService.create_guest_checkout(guest_info)
                
                if error:
                    return APIResponse.validation_error({"guest_info": error})
                
                # guest_user should be a User object, not a dictionary
                # If it's a dictionary, we need to extract the user
                if isinstance(guest_user, dict):
                    # This shouldn't happen if the service is implemented correctly
                    # But as a fallback, get the user from the dict
                    from apps.users.models.user import User
                    guest_user = User.objects.filter(id=guest_user.get('id')).first()
                    if not guest_user:
                        return APIResponse.validation_error({"guest_info": "Failed to create guest user"})
                
                # Set the user to the guest user for order creation
                order_user = guest_user
                
                # Ensure shipping address has the guest's email and phone if not provided
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
                # Authenticated user
                order_user = user

            # Create order with the user (authenticated or guest)
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

            # If Paystack payment, initialize payment
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

            # For POD (Pay on Delivery), order is confirmed
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

        # Check permission
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
        # Get order and check permission
        order = get_order_by_id(order_id)
        if not order:
            return APIResponse.not_found("Order not found")

        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to view this order")

        # Get payment options
        payment_options, error = OrderService.get_order_payment_options(order_id)

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data=payment_options, message="Payment options retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Payment options error: {str(e)}")
        return APIResponse.server_error()


# ==================== PAYMENT VIEWS ====================


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def initiate_payment(request, order_id):
    """Initiate payment for an order"""
    try:
        # Get order and check permission
        order = get_order_by_id(order_id)
        if not order:
            return APIResponse.not_found("Order not found")

        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden(
                "You don't have permission to pay for this order"
            )

        # Initiate payment
        payment_data, error = OrderService.initiate_payment(order_id)

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data=payment_data, message="Payment initialized successfully"
        )

    except Exception as e:
        logger.error(f"Initiate payment error: {str(e)}")
        return APIResponse.server_error()


# apps/orders/views.py - Fix the verify_payment view

# apps/orders/views.py - Fix verify_payment to return JSON, NOT redirect

# apps/orders/views.py - Fix verify_payment to serialize the order


@csrf_exempt
@require_http_methods(["GET"])
def verify_payment(request):
    """Verify payment - returns JSON for frontend AJAX call"""
    try:
        reference = request.GET.get("reference")
        order_id = request.GET.get("order_id")

        if not reference:
            return APIResponse.bad_request("Transaction reference is required")

        # Clean up order_id if it's 'null' string
        if order_id and order_id.lower() == "null":
            order_id = None

        # Validate UUID format if provided
        if order_id:
            import uuid

            try:
                uuid.UUID(order_id)
            except ValueError:
                from django.core.cache import cache

                cached_order_id = cache.get(f"paystack_ref_{reference}")
                if cached_order_id:
                    order_id = cached_order_id
                else:
                    order_id = None

        success, result = OrderService.verify_payment(reference, order_id)

        if success:
            # Get the order from result and serialize it
            order = result.get("order")
            from apps.orders.schemas import serialize_order

            # Serialize the order for JSON response
            serialized_order = (
                serialize_order(order, is_admin=False, detailed=False)
                if order
                else None
            )

            return APIResponse.success(
                data={
                    "order": serialized_order,
                    "transaction": result.get("transaction"),
                },
                message="Payment verified successfully",
            )
        else:
            return APIResponse.bad_request(
                message=result.get("error", "Payment verification failed")
            )

    except Exception as e:
        logger.error(f"Verify payment error: {str(e)}")
        return APIResponse.server_error()

# apps/orders/views.py - Update webhook to create transaction

@csrf_exempt
@require_http_methods(["POST"])
def paystack_webhook(request):
    """Paystack webhook endpoint"""
    try:
        from apps.orders.paystack_service import PaystackService

        signature = request.headers.get("x-paystack-signature", "")

        if not signature:
            return JsonResponse({"status": "error", "message": "No signature"}, status=400)

        event_data = PaystackService.handle_webhook(request.body, signature)

        if not event_data:
            return JsonResponse({"status": "error", "message": "Invalid signature"}, status=400)

        event = event_data.get("event")

        if event == "charge.success":
            data = event_data.get("data", {})
            reference = data.get("reference")

            # Process payment (this will create transaction)
            success, result = OrderService.verify_payment(reference)

            if success:
                logger.info(f"Webhook: Payment successful for reference {reference}")
            else:
                logger.error(f"Webhook: Payment verification failed for {reference}: {result}")

        elif event == "charge.dispute.create":
            logger.warning(f"Dispute created: {event_data.get('data', {}).get('reference')}")

        elif event == "refund.processed":
            logger.info(f"Refund processed: {event_data.get('data', {}).get('reference')}")

        return JsonResponse({"status": "success"})

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return JsonResponse({"status": "error", "message": str(e)}, status=500)
    

@csrf_exempt
@require_http_methods(["GET"])
def payment_callback(request):
    """
    Handle Paystack payment callback - returns JSON for frontend
    """
    try:
        reference = request.GET.get('reference')
        trxref = request.GET.get('trxref')
        payment_ref = reference or trxref

        if not payment_ref:
            return APIResponse.bad_request("No payment reference found")

        # Verify payment
        from apps.orders.paystack_service import PaystackService
        transaction_data, error = PaystackService.verify_transaction(payment_ref)

        if error or not transaction_data:
            return APIResponse.bad_request(f"Verification failed: {error}")

        if transaction_data.get('status') != 'success':
            return APIResponse.bad_request("Payment was not successful")

        # Get order from metadata
        metadata = transaction_data.get('metadata', {})
        order_id = metadata.get('order_id')

        if not order_id:
            from django.core.cache import cache
            order_id = cache.get(f'paystack_ref_{payment_ref}')

        if not order_id:
            return APIResponse.not_found("Order not found")

        # Update order payment status
        from apps.orders.order_service import OrderService
        order, error = OrderService.update_payment_status(
            order_id=order_id,
            payment_status='paid',
            payment_intent_id=transaction_data.get('reference'),
            payment_receipt_url=transaction_data.get('receipt_url', ''),
        )

        if error:
            return APIResponse.validation_error(error)

        # Serialize order
        from apps.orders.schemas import serialize_order
        serialized_order = serialize_order(order, is_admin=False, detailed=False)

        # Return JSON - frontend will handle navigation
        return APIResponse.success(
            data={
                "order": serialized_order,
                "reference": payment_ref
            },
            message="Payment verified successfully"
        )

    except Exception as e:
        logger.error(f"Payment callback error: {str(e)}")
        return APIResponse.server_error()

# ==================== ADMIN ORDER VIEWS ====================
@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_list(request):
    """Admin: List all orders with filtering, sorting, and pagination"""
    try:
        # Get pagination parameters
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        
        # Get filter parameters
        search = request.GET.get("search", "").strip()
        status = request.GET.get("status")
        payment_status = request.GET.get("payment_status")
        payment_method = request.GET.get("payment_method")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        min_total = request.GET.get("min_total")
        max_total = request.GET.get("max_total")
        
        # Get sorting parameters
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
        # Convert numeric parameters
        min_total_float = float(min_total) if min_total else None
        max_total_float = float(max_total) if max_total else None
        
        # Get filtered orders
        from apps.orders.selectors import get_admin_orders_filtered
        
        orders, total, pagination_meta = get_admin_orders_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            status=status if status else None,
            payment_status=payment_status if payment_status else None,
            payment_method=payment_method if payment_method else None,
            date_from=date_from if date_from else None,
            date_to=date_to if date_to else None,
            min_total=min_total_float,
            max_total=max_total_float,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        from apps.orders.schemas import serialize_pagination_metadata
        
        return APIResponse.success(
            data={
                "orders": serialize_order_list(orders, is_admin=True),
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta)
            },
            message="Orders retrieved successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid parameter: {str(e)}")
        return APIResponse.bad_request(f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Admin order list error: {str(e)}")
        import traceback
        traceback.print_exc()
        return APIResponse.server_error()





@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_detail(request, order_id):
    """Admin: Get order details"""
    try:
        order = get_order_by_id(order_id, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")

        return APIResponse.success(
            data=serialize_order(order, is_admin=True, detailed=True),
            message="Order retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Admin order detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_by_number(request, order_number):
    """Admin: Get order by order number"""
    try:
        order = get_order_by_id(order_number, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")

        return APIResponse.success(
            data=serialize_order(order, is_admin=True, detailed=True),
            message="Order retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Admin order by number error: {str(e)}")
        return APIResponse.server_error()


# apps/orders/views.py - Update admin_update_order_status

@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_update_order_status(request, order_id):
    """Admin: Update order status (auto-creates shipment when status='shipped')"""
    try:
        data = request.json_data

        # Validate input
        cleaned, errors = validate_order_status_update(data)
        if errors:
            return APIResponse.validation_error(errors)

        # Pass tracking info if provided (for when status changes to shipped)
        tracking_number = cleaned.get('tracking_number')
        carrier = cleaned.get('carrier')
        
        order, error = OrderService.update_order_status(
            order_id=order_id,
            status=cleaned["status"],
            admin_note=cleaned.get("admin_note"),
            carrier=carrier,
            tracking_number=tracking_number,
            user=request.user,
        )

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data={"order": serialize_order(order, is_admin=True)},
            message=f"Order status updated to {cleaned['status']}",
        )

    except Exception as e:
        logger.error(f"Update order status error: {str(e)}")
        return APIResponse.server_error()
    
    

@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_update_payment_status(request, order_id):
    """Admin: Update payment status"""
    try:
        data = request.json_data

        # Validate input
        cleaned, errors = validate_payment_status_update(data)
        if errors:
            return APIResponse.validation_error(errors)

        order, error = OrderService.update_payment_status(
            order_id=order_id,
            payment_status=cleaned["payment_status"],
            payment_intent_id=cleaned.get("payment_intent_id"),
            payment_receipt_url=cleaned.get("payment_receipt_url"),
            user=request.user,
        )

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data={"order": serialize_order(order, is_admin=True)},
            message=f"Payment status updated to {cleaned['payment_status']}",
        )

    except Exception as e:
        logger.error(f"Update payment status error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_stats(request):
    """Admin: Get order statistics"""
    try:
        stats = get_order_statistics()

        return APIResponse.success(
            data=stats, message="Order statistics retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Order stats error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_order_analytics(request):
    """Admin: Get detailed order analytics"""
    try:
        from django.db.models import Sum
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)

        # Get analytics data
        analytics = {
            "summary": {
                "total_orders": Order.objects.count(),
                "total_revenue": float(
                    Order.objects.aggregate(total=Sum("total"))["total"] or 0
                ),
                "average_order_value": 0,
                "total_items_sold": OrderItem.objects.aggregate(total=Sum("quantity"))[
                    "total"
                ]
                or 0,
            },
            "today": {
                "orders": Order.objects.filter(created_at__date=today).count(),
                "revenue": float(
                    Order.objects.filter(created_at__date=today).aggregate(
                        total=Sum("total")
                    )["total"]
                    or 0
                ),
            },
            "this_week": {
                "orders": Order.objects.filter(created_at__date__gte=week_ago).count(),
                "revenue": float(
                    Order.objects.filter(created_at__date__gte=week_ago).aggregate(
                        total=Sum("total")
                    )["total"]
                    or 0
                ),
            },
            "this_month": {
                "orders": Order.objects.filter(created_at__date__gte=month_ago).count(),
                "revenue": float(
                    Order.objects.filter(created_at__date__gte=month_ago).aggregate(
                        total=Sum("total")
                    )["total"]
                    or 0
                ),
            },
            "by_status": {
                status: Order.objects.filter(status=status).count()
                for status, _ in Order.STATUS_CHOICES
            },
            "by_payment_method": {
                "paystack": Order.objects.filter(payment_method="paystack").count(),
                "pod": Order.objects.filter(payment_method="pod").count(),
            },
        }

        # Calculate average order value
        if analytics["summary"]["total_orders"] > 0:
            analytics["summary"]["average_order_value"] = round(
                analytics["summary"]["total_revenue"]
                / analytics["summary"]["total_orders"],
                2,
            )

        return APIResponse.success(
            data=analytics, message="Order analytics retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Order analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_export_orders(request):
    """Admin: Export orders to CSV"""
    try:
        # Get filters
        status = request.GET.get("status")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")

        # Build queryset
        from apps.orders.models import Order

        queryset = Order.objects.all().order_by("-created_at")

        if status:
            queryset = queryset.filter(status=status)
        if date_from:
            queryset = queryset.filter(created_at__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(created_at__date__lte=date_to)

        # Create CSV response
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="orders_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(
            [
                "Order Number",
                "Customer Name",
                "Customer Email",
                "Status",
                "Payment Status",
                "Payment Method",
                "Subtotal",
                "Shipping",
                "Tax",
                "Discount",
                "Total",
                "Item Count",
                "Created At",
            ]
        )

        for order in queryset:
            writer.writerow(
                [
                    order.order_number,
                    order.customer_name,
                    order.customer_email,
                    order.get_status_display(),
                    order.get_payment_status_display(),
                    order.get_payment_method_display(),
                    float(order.subtotal),
                    float(order.shipping_cost),
                    float(order.tax_amount),
                    float(order.discount_amount),
                    float(order.total),
                    order.item_count,
                    order.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                ]
            )

        return response

    except Exception as e:
        logger.error(f"Export orders error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_bulk_order_action(request):
    """Admin: Perform bulk actions on orders"""
    print("Hereee")
    try:
        data = request.json_data
        action = data.get("action")
        order_ids = data.get("order_ids", [])

        if not order_ids:
            return APIResponse.bad_request("No order IDs provided")

        if not action:
            return APIResponse.bad_request("No action specified")

        results = {"success": [], "failed": [], "total": len(order_ids)}

        if action == "cancel":
            for order_id in order_ids:
                try:
                    order, error = OrderService.cancel_order(
                        order_id=order_id,
                        user=request.user,
                        reason="Bulk cancellation by admin",
                    )
                    if error:
                        results["failed"].append({"id": order_id, "reason": str(error)})
                    else:
                        results["success"].append(
                            {"id": order_id, "order_number": order.order_number}
                        )
                except Exception as e:
                    results["failed"].append({"id": order_id, "reason": str(e)})

        elif action in ["confirm", "process", "ship", "deliver"]:
            status_map = {
                "confirm": "confirmed",
                "process": "processing",
                "ship": "shipped",
                "deliver": "delivered",
            }
            new_status = status_map.get(action)

            for order_id in order_ids:
                try:
                    order, error = OrderService.update_order_status(
                        order_id=order_id,
                        status=new_status,
                        admin_note=f"Bulk {action} action by admin",
                        user=request.user,
                    )
                    if error:
                        results["failed"].append({"id": order_id, "reason": str(error)})
                    else:
                        results["success"].append(
                            {"id": order_id, "order_number": order.order_number}
                        )
                except Exception as e:
                    results["failed"].append({"id": order_id, "reason": str(e)})

        else:
            return APIResponse.bad_request(f"Unknown action: {action}")

        return APIResponse.success(
            data=results,
            message=f"Processed {len(results['success'])} out of {results['total']} orders",
        )

    except Exception as e:
        logger.error(f"Bulk order action error: {str(e)}")
        return APIResponse.server_error()


# ==================== ADDRESS VIEWS ====================


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



# ==================== SHIPMENT VIEWS ====================

@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_create_shipment(request, order_id):
    """Admin: Create a new shipment for an order (after payment)"""
    try:
        data = request.json_data
        
        order = get_order_by_id(order_id, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")
        
        # Check if order is paid or is POD
        if order.payment_method == Order.PAYMENT_CASH_ON_DELIVERY:
            # POD orders can be shipped without payment
            pass
        elif order.payment_status != Order.PAYMENT_PAID:
            return APIResponse.bad_request("Order must be paid before creating shipment")
        
        # Parse shipping cost if provided
        shipping_cost = None
        if data.get('shipping_cost'):
            shipping_cost = Decimal(str(data['shipping_cost']))
        
        # Create shipment
        shipment, error = ShipmentService.create_shipment(
            order_id=str(order.id),
            carrier=data.get('carrier', ''),
            tracking_number=data.get('tracking_number', ''),
            tracking_url=data.get('tracking_url', ''),
            weight=Decimal(str(data['weight'])) if data.get('weight') else None,
            dimensions=data.get('dimensions', ''),
            estimated_delivery=data.get('estimated_delivery'),
            notes=data.get('notes', ''),
            shipping_cost=shipping_cost,
            created_by=request.user,
        )
        
        if error:
            return APIResponse.validation_error(error)
        
        # Update order shipping method
        if data.get('shipping_method'):
            order.shipping_method = data['shipping_method']
            order.save()
        
        from apps.orders.schemas import serialize_shipment_info
        shipment_info = serialize_shipment_info(order)
        
        return APIResponse.created(
            data={
                "shipment": {
                    "id": str(shipment.id),
                    "status": shipment.status,
                    "tracking_number": shipment.tracking_number,
                    "carrier": shipment.carrier,
                },
                "order": shipment_info,
            },
            message="Shipment created successfully"
        )
        
    except Exception as e:
        logger.error(f"Create shipment error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_update_shipment_status(request, shipment_id):
    """Admin: Update shipment status and tracking"""
    try:
        data = request.json_data
        
        # Validate input
        cleaned, errors = validate_shipment_update(data)
        if errors:
            return APIResponse.validation_error(errors)
        
        shipment, error = ShipmentService.update_shipment_status(
            shipment_id=shipment_id,
            status=cleaned.get('shipment_status'),
            location=cleaned.get('location', ''),
            description=cleaned.get('description', ''),
            tracking_number=cleaned.get('tracking_number'),
            carrier=cleaned.get('carrier'),
            created_by=request.user,
        )
        
        if error:
            return APIResponse.validation_error(error)
        
        from apps.orders.schemas import serialize_shipment_info
        shipment_info = serialize_shipment_info(shipment.order)
        
        return APIResponse.success(
            data={
                "shipment": {
                    "id": str(shipment.id),
                    "status": shipment.status,
                    "tracking_number": shipment.tracking_number,
                    "carrier": shipment.carrier,
                },
                "order": shipment_info,
                "tracking_history": ShipmentService.get_shipment_tracking(shipment_id),
            },
            message=f"Shipment status updated to {shipment.status}"
        )
        
    except Exception as e:
        logger.error(f"Update shipment status error: {str(e)}")
        return APIResponse.server_error()



@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_shipments_list(request):
    """Admin: List all shipments with filtering, sorting, and pagination"""
    try:
        # Get pagination parameters
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        
        # Get filter parameters
        search = request.GET.get("search", "").strip()
        status = request.GET.get("status")
        carrier = request.GET.get("carrier")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        
        # Get sorting parameters
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
        # Get filtered shipments
        from apps.orders.selectors import get_shipments_filtered
        from apps.orders.schemas import serialize_pagination_metadata, serialize_shipment_list
        
        shipments, total, pagination_meta = get_shipments_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            status=status if status else None,
            carrier=carrier if carrier else None,
            date_from=date_from if date_from else None,
            date_to=date_to if date_to else None,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        shipments_data = serialize_shipment_list(shipments, is_admin=True)
        
        return APIResponse.success(
            data={
                "shipments": shipments_data,
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta)
            },
            message="Shipments retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Admin shipments list error: {str(e)}")
        import traceback
        traceback.print_exc()
        return APIResponse.server_error()




@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def order_shipment_info(request, order_id):
    """Get shipment information for an order (customer view)"""
    try:
        order = get_order_by_id(order_id)
        if not order:
            return APIResponse.not_found("Order not found")
        
        # Check permission
        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to view this order")
        
        from apps.orders.schemas import serialize_shipment_info
        shipment_info = serialize_shipment_info(order)
        
        return APIResponse.success(
            data=shipment_info,
            message="Shipment info retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Order shipment info error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def track_shipment(request, tracking_number):
    """Track a shipment by tracking number"""
    try:
        # Find shipment by tracking number
        try:
            shipment = Shipment.objects.get(tracking_number=tracking_number)
        except Shipment.DoesNotExist:
            return APIResponse.not_found("Shipment not found")
        
        # Check permission
        if shipment.order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to track this shipment")
        
        tracking_history = ShipmentService.get_shipment_tracking(str(shipment.id))
        
        return APIResponse.success(
            data={
                "tracking_number": shipment.tracking_number,
                "carrier": shipment.carrier,
                "status": shipment.status,
                "status_display": shipment.get_status_display(),
                "estimated_delivery": shipment.estimated_delivery.isoformat() if shipment.estimated_delivery else None,
                "tracking_history": tracking_history,
            },
            message="Tracking information retrieved"
        )
        
    except Exception as e:
        logger.error(f"Track shipment error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_bulk_update_shipments(request):
    """Admin: Bulk update shipment status for multiple orders"""
    try:
        data = request.json_data
        order_ids = data.get('order_ids', [])
        shipment_status = data.get('shipment_status')
        tracking_number = data.get('tracking_number', '')
        carrier = data.get('carrier', '')
        admin_note = data.get('admin_note', '')
        
        if not order_ids:
            return APIResponse.bad_request("No order IDs provided")
        
        if not shipment_status:
            return APIResponse.bad_request("Shipment status is required")
        
        results = {
            'success': [],
            'failed': [],
            'total': len(order_ids)
        }
        
        for order_id in order_ids:
            try:
                order = get_order_by_id(order_id, include_cancelled=True)
                if not order:
                    results['failed'].append({'id': order_id, 'reason': 'Order not found'})
                    continue
                
                # Check if shipment exists
                if not hasattr(order, 'shipment'):
                    results['failed'].append({'id': order_id, 'reason': 'No shipment found for order'})
                    continue
                
                shipment, error = ShipmentService.update_shipment_status(
                    shipment_id=str(order.shipment.id),
                    status=shipment_status,
                    tracking_number=tracking_number,
                    carrier=carrier,
                    description=admin_note,
                    created_by=request.user,
                )
                
                if error:
                    results['failed'].append({'id': order_id, 'reason': str(error)})
                else:
                    results['success'].append({'id': order_id, 'order_number': order.order_number})
                    
            except Exception as e:
                results['failed'].append({'id': order_id, 'reason': str(e)})
        
        return APIResponse.success(
            data=results,
            message=f"Processed {len(results['success'])} out of {results['total']} shipments"
        )
        
    except Exception as e:
        logger.error(f"Bulk shipment update error: {str(e)}")
        return APIResponse.server_error()


# ==================== TRANSACTION VIEWS ====================

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def order_transactions(request, order_id):
    """Get all transactions for an order"""
    try:
        order = get_order_by_id(order_id, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")
        
        # Check permission
        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to view this order")
        
        transactions = get_order_transactions(order_id)
        is_admin = _is_admin(request)
        
        from apps.orders.schemas import serialize_transaction
        transactions_data = [serialize_transaction(t, is_admin=is_admin) for t in transactions]
        
        # Get refundable amount (admin only)
        refundable_amount = None
        if is_admin:
            refundable_amount = float(get_refundable_amount(order_id))
        
        return APIResponse.success(
            data={
                "transactions": transactions_data,
                "refundable_amount": refundable_amount,
                "order_total": float(order.total),
                "order_paid": float(order.subtotal + order.shipping_cost + order.tax_amount - order.discount_amount),
            },
            message="Transactions retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Order transactions error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_process_refund(request, order_id):
    """Admin: Process a refund for an order"""
    try:
        data = request.json_data
        
        # Validate input
        cleaned, errors = validate_refund_request(data)
        if errors:
            return APIResponse.validation_error(errors)
        
        order = get_order_by_id(order_id, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")
        
        # Check if order can be refunded
        if order.payment_status not in [Order.PAYMENT_PAID, Order.PAYMENT_PARTIALLY_REFUNDED]:
            return APIResponse.bad_request("Order cannot be refunded in its current payment status")
        
        # Process refund
        transaction_obj, error = TransactionService.record_refund(
            order_id=order_id,
            amount=Decimal(str(cleaned['amount'])),
            refund_reason=cleaned.get('refund_reason', ''),
            notes=cleaned.get('admin_note', ''),
        )
        
        if error:
            return APIResponse.validation_error(error)
        
        from apps.orders.schemas import serialize_transaction
        transaction_data = serialize_transaction(transaction_obj, is_admin=True)
        
        # Get updated refundable amount
        refundable_amount = float(get_refundable_amount(order_id))
        
        return APIResponse.success(
            data={
                "transaction": transaction_data,
                "refundable_amount": refundable_amount,
                "order_payment_status": order.payment_status,
            },
            message=f"Refund of ${cleaned['amount']} processed successfully"
        )
        
    except Exception as e:
        logger.error(f"Process refund error: {str(e)}")
        return APIResponse.server_error()



@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_transactions_list(request):
    """Admin: List all transactions with filtering, sorting, and pagination"""
    try:
        # Get pagination parameters
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        
        # Get filter parameters
        search = request.GET.get("search", "").strip()
        transaction_type = request.GET.get("type")
        status = request.GET.get("status")
        payment_method = request.GET.get("payment_method")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        min_amount = request.GET.get("min_amount")
        max_amount = request.GET.get("max_amount")
        
        # Get sorting parameters
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
        # Convert numeric parameters
        min_amount_float = float(min_amount) if min_amount else None
        max_amount_float = float(max_amount) if max_amount else None
        
        # Get filtered transactions
        from apps.orders.selectors import get_transactions_filtered
        from apps.orders.schemas import serialize_pagination_metadata, serialize_transaction_list
        
        transactions, total, pagination_meta = get_transactions_filtered(
            page=page,
            limit=limit,
            search=search if search else None,
            transaction_type=transaction_type if transaction_type else None,
            status=status if status else None,
            payment_method=payment_method if payment_method else None,
            date_from=date_from if date_from else None,
            date_to=date_to if date_to else None,
            min_amount=min_amount_float,
            max_amount=max_amount_float,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        transactions_data = serialize_transaction_list(transactions, is_admin=True)
        
        # Summary stats
        from django.db.models import Sum
        from apps.orders.models import Transaction
        
        stats = {
            "total_charges": float(Transaction.objects.filter(transaction_type='charge', status='success').aggregate(total=Sum('amount'))['total'] or 0),
            "total_refunds": float(Transaction.objects.filter(transaction_type='refund', status='success').aggregate(total=Sum('amount'))['total'] or 0),
            "net_revenue": float(Transaction.objects.filter(transaction_type='charge', status='success').aggregate(total=Sum('amount'))['total'] or 0) - 
                          float(Transaction.objects.filter(transaction_type='refund', status='success').aggregate(total=Sum('amount'))['total'] or 0),
            "successful_count": Transaction.objects.filter(status='success').count(),
            "failed_count": Transaction.objects.filter(status='failed').count(),
            "pending_count": Transaction.objects.filter(status='pending').count(),
        }
        
        return APIResponse.success(
            data={
                "transactions": transactions_data,
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta),
                "stats": stats,
            },
            message="Transactions retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Admin transactions list error: {str(e)}")
        import traceback
        traceback.print_exc()
        return APIResponse.server_error()




@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_transaction_detail(request, transaction_id):
    """Admin: Get detailed transaction information"""
    try:
        transaction = Transaction.objects.select_related('order').get(transaction_id=transaction_id)
        
        from apps.orders.schemas import serialize_transaction
        transaction_data = serialize_transaction(transaction, is_admin=True)
        
        # Add related refunds if any
        refunds = transaction.refunds.all()
        if refunds:
            transaction_data['refunds'] = [serialize_transaction(r, is_admin=True) for r in refunds]
        
        # Add parent transaction if this is a refund
        if transaction.parent_transaction:
            transaction_data['parent_transaction'] = serialize_transaction(transaction.parent_transaction, is_admin=True)
        
        return APIResponse.success(
            data=transaction_data,
            message="Transaction details retrieved"
        )
        
    except Transaction.DoesNotExist:
        return APIResponse.not_found("Transaction not found")
    except Exception as e:
        logger.error(f"Transaction detail error: {str(e)}")
        return APIResponse.server_error()
    
    
# apps/orders/views.py - Add these views

@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def get_shipping_rates(request):
    """
    Get real-time shipping rates from Terminal Africa
    This is typically called during checkout before order creation
    """
    try:
        data = request.json_data
        
        # Get shipping address details
        shipping_address = data.get('shipping_address', {})
        items = data.get('items', [])
        currency = data.get('currency', 'GHS')
        
        if not shipping_address:
            return APIResponse.bad_request("Shipping address is required")
        
        if not items:
            return APIResponse.bad_request("Items are required")
        
        # Prepare origin address (warehouse/sender)
        origin = {
            "country": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('country', 'GH'),
            "state": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('state', 'Greater Accra'),
            "city": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('city', 'Accra'),
            "postal_code": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('postal_code', '00233'),
            "address": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('address', ''),
        }
        
        # Prepare destination address
        destination = {
            "country": shipping_address.get('country', 'GH'),
            "state": shipping_address.get('state', ''),
            "city": shipping_address.get('city', ''),
            "postal_code": shipping_address.get('postal_code', ''),
            "address": shipping_address.get('address_line1', ''),
        }
        
        # Calculate total weight from items
        from apps.orders.shipment_service import ShippingCalculator
        total_weight = Decimal('0.00')
        
        # Fetch variant details to get weights
        for item in items:
            variant_id = item.get('variant_id')
            quantity = item.get('quantity', 1)
            
            try:
                from apps.products.models import ProductVariant
                variant = ProductVariant.objects.get(id=variant_id)
                if variant.weight:
                    total_weight += Decimal(str(variant.weight)) * Decimal(str(quantity))
                else:
                    # Default weight 0.5kg per item
                    total_weight += Decimal('0.5') * Decimal(str(quantity))
            except ProductVariant.DoesNotExist:
                # Default weight 0.5kg per item
                total_weight += Decimal('0.5') * Decimal(str(quantity))
        
        # Prepare parcels
        parcels = [{
            "weight": float(total_weight),
            "quantity": 1,
            "description": "Package",
        }]
        
        # Try Terminal Africa first, fallback to calculator
        from apps.orders.terminal_africa_service import TerminalAfricaService
        
        rates, error = TerminalAfricaService.get_shipping_rates(
            origin=origin,
            destination=destination,
            parcels=parcels,
            currency=currency,
        )
        
        # If Terminal Africa fails or not configured, use internal calculator
        if error or not rates:
            # Use internal shipping calculator
            subtotal = Decimal('0.00')
            
            # Calculate subtotal from items
            for item in items:
                variant_id = item.get('variant_id')
                quantity = item.get('quantity', 1)
                try:
                    from apps.products.models import ProductVariant
                    variant = ProductVariant.objects.get(id=variant_id)
                    subtotal += variant.price * Decimal(str(quantity))
                except ProductVariant.DoesNotExist:
                    pass
            
            rates = ShippingCalculator.get_shipping_options(
                country_code=destination['country'],
                total_weight_kg=total_weight,
                subtotal=subtotal,
            )
            
            # Format rates to match Terminal Africa format
            formatted_rates = []
            for rate in rates:
                formatted_rates.append({
                    'id': rate['id'],
                    'carrier': 'Internal',
                    'carrier_code': 'internal',
                    'service_level': rate['name'],
                    'service_level_code': rate['id'],
                    'amount': rate['cost'],
                    'currency': currency,
                    'estimated_days': rate.get('estimated_days', '3-7 business days'),
                    'guaranteed_delivery': False,
                    'description': rate.get('estimated_days', ''),
                })
            rates = formatted_rates
        
        return APIResponse.success(
            data={
                "rates": rates,
                "origin": origin,
                "destination": destination,
                "weight_kg": float(total_weight),
            },
            message="Shipping rates retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Get shipping rates error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
# @jwt_required
@json_request_required
def get_shipping_options(request):
    """
    Get shipping options based on internal calculation
    This is used when Terminal Africa is not configured or as fallback
    """
    try:
        data = request.json_data
        
        country_code = data.get('country_code', 'GH')
        subtotal = data.get('subtotal', 0)
        items = data.get('items', [])
        
        if not items:
            return APIResponse.bad_request("Items are required")
        
        from apps.orders.shipping_calculator import ShippingCalculator
        
        # Calculate total weight
        total_weight = Decimal('0.00')
        
        for item in items:
            variant_id = item.get('variant_id')
            quantity = item.get('quantity', 1)
            
            try:
                from apps.products.models import ProductVariant
                variant = ProductVariant.objects.get(id=variant_id)
                if variant.weight:
                    total_weight += Decimal(str(variant.weight)) * Decimal(str(quantity))
                else:
                    total_weight += Decimal('0.5') * Decimal(str(quantity))
            except ProductVariant.DoesNotExist:
                total_weight += Decimal('0.5') * Decimal(str(quantity))
        
        # Get shipping options
        options = ShippingCalculator.get_shipping_options(
            country_code=country_code,
            total_weight_kg=total_weight,
            subtotal=Decimal(str(subtotal)),
        )
        
        return APIResponse.success(
            data={
                "options": options,
                "weight_kg": float(total_weight),
                "subtotal": subtotal,
                "country": country_code,
            },
            message="Shipping options retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Get shipping options error: {str(e)}")
        return APIResponse.server_error()
    
    

# apps/orders/views.py - Add this view

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_shipment_detail(request, shipment_id):
    """Admin: Get detailed shipment information"""
    try:
        from apps.orders.models import Shipment
        
        # Get shipment with related data
        shipment = Shipment.objects.select_related(
            'order', 
            'order__user', 
            'order__shipping_address',
            'order__billing_address'
        ).prefetch_related(
            'tracking_history',
            'tracking_history__created_by',
            'order__items',
            'order__items__variant',
            'order__items__variant__product'
        ).get(id=shipment_id)
        
        order = shipment.order
        
        # Build detailed response
        shipment_data = {
            "id": str(shipment.id),
            "order_number": order.order_number,
            "customer_name": order.customer_name,
            "customer_email": order.customer_email,
            "status": shipment.status,
            "status_display": shipment.get_status_display(),
            "tracking_number": shipment.tracking_number,
            "carrier": shipment.carrier,
            "tracking_url": shipment.tracking_url,
            "estimated_delivery": shipment.estimated_delivery.isoformat() if shipment.estimated_delivery else None,
            "shipping_method": order.shipping_method,
            "shipping_cost": float(order.shipping_cost),
            "weight": float(shipment.weight) if shipment.weight else None,
            # "dimensions": shipment.dimensions,
            "notes": shipment.notes,
            # "internal_notes": shipment.internal_notes,
            "created_at": shipment.created_at.isoformat(),
            "updated_at": shipment.updated_at.isoformat(),
            "shipped_at": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
            "delivered_at": shipment.delivered_at.isoformat() if shipment.delivered_at else None,
            "created_by": shipment.created_by.email if shipment.created_by else None,
        }
        
        # Add tracking history
        tracking_history = []
        for track in shipment.tracking_history.all().order_by('-created_at'):
            tracking_history.append({
                "status": track.status,
                "status_display": dict(Shipment.STATUS_CHOICES).get(track.status, track.status),
                "location": track.location,
                "description": track.description,
                "created_at": track.created_at.isoformat(),
                "created_by": track.created_by.email if track.created_by else None,
            })
        shipment_data["tracking_history"] = tracking_history
        
        # Add shipping address
        if order.shipping_address:
            shipment_data["shipping_address"] = {
                "first_name": order.shipping_address.first_name,
                "last_name": order.shipping_address.last_name,
                "company": order.shipping_address.company,
                "address_line1": order.shipping_address.address_line1,
                "address_line2": order.shipping_address.address_line2,
                "city": order.shipping_address.city,
                "state": order.shipping_address.state,
                "postal_code": order.shipping_address.postal_code,
                "country": order.shipping_address.country,
                "phone": order.shipping_address.phone,
                "email": order.shipping_address.email,
                "instructions": order.shipping_address.instructions,
            }
        
        # Add order items summary
        order_items = []
        for item in order.items.all():
            order_items.append({
                "id": str(item.id),
                "product_title": item.product_title,
                "product_slug": item.product_slug,
                "sku": item.sku,
                "quantity": item.quantity,
                "unit_price": float(item.unit_price),
                "total_price": float(item.total_price),
                "image": item.variant.images.first().image.url if item.variant and item.variant.images.exists() else None,
            })
        shipment_data["order_items"] = order_items
        
        # Add order summary
        shipment_data["order_summary"] = {
            "subtotal": float(order.subtotal),
            "shipping_cost": float(order.shipping_cost),
            "tax_amount": float(order.tax_amount),
            "discount_amount": float(order.discount_amount),
            "total": float(order.total),
            "currency": order.currency,
            "item_count": order.item_count,
            "payment_status": order.payment_status,
            "payment_status_display": order.get_payment_status_display(),
            "payment_method": order.payment_method,
            "payment_method_display": order.get_payment_method_display(),
        }
        
        return APIResponse.success(
            data=shipment_data,
            message="Shipment details retrieved successfully"
        )
        
    except Shipment.DoesNotExist:
        return APIResponse.not_found("Shipment not found")
    except Exception as e:
        logger.error(f"Admin shipment detail error: {str(e)}")
        return APIResponse.server_error()
    
    
@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def order_debug_info(request, order_id):
    """Debug view to check order transactions and shipment"""
    try:
        order = get_order_by_id(order_id, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")
        
        # Check permissions
        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to view this order")
        
        from apps.orders.models import Transaction
        
        transactions = Transaction.objects.filter(order=order).values(
            'id', 'transaction_type', 'amount', 'status', 'created_at', 'transaction_id'
        )
        
        shipment = None
        if hasattr(order, 'shipment'):
            shipment = {
                'id': str(order.shipment.id),
                'status': order.shipment.status,
                'tracking_number': order.shipment.tracking_number,
                'carrier': order.shipment.carrier,
                'created_at': order.shipment.created_at.isoformat(),
            }
        
        return APIResponse.success(
            data={
                "order": {
                    "id": str(order.id),
                    "order_number": order.order_number,
                    "status": order.status,
                    "payment_status": order.payment_status,
                    "payment_method": order.payment_method,
                },
                "transactions": list(transactions),
                "shipment": shipment,
                "has_shipment": hasattr(order, 'shipment'),
            },
            message="Debug info retrieved"
        )
        
    except Exception as e:
        logger.error(f"Debug info error: {str(e)}")
        return APIResponse.server_error()