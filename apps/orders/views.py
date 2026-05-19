# apps/orders/views.py
import logging
import csv
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.http import JsonResponse
from users.decorators.auth import jwt_required, role_required, json_request_required
from estore.utils.responses import APIResponse

from apps.orders.selectors import (
    get_user_orders,
    get_admin_orders,
    get_order_statistics,
    get_order_by_id,
)
from apps.orders.schemas import (
    serialize_order,
    serialize_order_list,
    serialize_order_item,
    serialize_address,
    validate_order_create,
    validate_order_status_update,
    validate_payment_status_update,
    validate_address_create,
    validate_address_update,
)
from apps.orders.order_service import OrderService, AddressService
from apps.orders.models import Order, OrderItem

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
@jwt_required
@json_request_required
def create_order(request):
    """Create a new order"""
    try:
        data = request.json_data
        is_authenticated = request.user.is_authenticated

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

        # Prepare guest info if not authenticated
        guest_info = None
        if not is_authenticated:
            guest_info = {
                "email": cleaned.get("guest_email"),
                "first_name": cleaned.get("guest_first_name"),
                "last_name": cleaned.get("guest_last_name"),
                "phone": cleaned.get("guest_phone"),
            }

        # Create order
        order, error = OrderService.create_order(
            user=request.user if is_authenticated else None,
            items=cleaned["items"],
            shipping_address_data=cleaned["shipping_address"],
            payment_method=payment_method,
            guest_info=guest_info,
            billing_address_data=cleaned.get("billing_address"),
            shipping_cost=cleaned.get("shipping_cost", 0),
            tax_rate=cleaned.get("tax_rate", 0),
            discount_amount=cleaned.get("discount_amount", 0),
            customer_note=cleaned.get("customer_note", ""),
            shipping_method=cleaned.get("shipping_method", ""),
            currency=cleaned.get("currency", "USD"),
        )

        if error:
            return APIResponse.validation_error(error)

        response_data = {
            "order": serialize_order(order, is_admin=False),
            "payment_method": payment_method,
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

        # For POD, order is confirmed
        elif payment_method == "pod":
            response_data["message"] = "Order confirmed. You will pay on delivery."
            return APIResponse.created(
                data=response_data, message="Order confirmed successfully"
            )

        return APIResponse.created(
            data=response_data, message="Order created successfully"
        )

    except Exception as e:
        logger.error(f"Create order error: {str(e)}")
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


@csrf_exempt
@require_http_methods(["POST"])
def paystack_webhook(request):
    """Paystack webhook endpoint"""
    try:
        from apps.orders.paystack_service import PaystackService

        # Get signature from headers
        signature = request.headers.get("x-paystack-signature", "")

        if not signature:
            return APIResponse.bad_request("No signature provided")

        # Process webhook
        event_data = PaystackService.handle_webhook(request.body, signature)

        if not event_data:
            return APIResponse.bad_request("Invalid signature")

        # Handle different event types
        event = event_data.get("event")

        if event == "charge.success":
            data = event_data.get("data", {})
            reference = data.get("reference")

            # Process payment
            success, result = OrderService.verify_payment(reference)

            if success:
                logger.info(f"Webhook: Payment successful for reference {reference}")
            else:
                logger.error(
                    f"Webhook: Payment verification failed for {reference}: {result}"
                )

        elif event == "charge.dispute.create":
            logger.warning(
                f"Dispute created for transaction: {event_data.get('data', {}).get('reference')}"
            )

        elif event == "refund.processed":
            logger.info(
                f"Refund processed: {event_data.get('data', {}).get('reference')}"
            )

        # Paystack expects a simple 200 OK response
        # Using JsonResponse is fine here, but we can also use APIResponse
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
    """Admin: List all orders"""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        status = request.GET.get("status")
        payment_status = request.GET.get("payment_status")
        search = request.GET.get("search", "").strip()
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")

        orders, total = get_admin_orders(
            page=page,
            limit=limit,
            status=status,
            payment_status=payment_status,
            search=search,
            date_from=date_from,
            date_to=date_to,
        )

        return APIResponse.success(
            data={
                "orders": serialize_order_list(orders, is_admin=True),
                "total": total,
                "page": page,
                "limit": limit,
            },
            message="Orders retrieved successfully",
        )

    except Exception as e:
        logger.error(f"Admin order list error: {str(e)}")
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


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_update_order_status(request, order_id):
    """Admin: Update order status"""
    try:
        data = request.json_data

        # Validate input
        cleaned, errors = validate_order_status_update(data)
        if errors:
            return APIResponse.validation_error(errors)

        order, error = OrderService.update_order_status(
            order_id=order_id,
            status=cleaned["status"],
            admin_note=cleaned.get("admin_note"),
            carrier=cleaned.get("carrier"),
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
