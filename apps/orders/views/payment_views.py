"""
Payment Views - Payment processing endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.http import JsonResponse
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, json_request_required
from apps.orders.selectors import get_order_by_id
from apps.orders.schemas import serialize_order
from apps.orders.order_service import OrderService

logger = logging.getLogger(__name__)


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, "user") or not request.user:
        return False
    return getattr(request.user, "role", "customer") in ["admin", "staff"]


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def initiate_payment(request, order_id):
    """Initiate payment for an order"""
    try:
        order = get_order_by_id(order_id)
        if not order:
            return APIResponse.not_found("Order not found")

        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden(
                "You don't have permission to pay for this order"
            )

        payment_data, error = OrderService.initiate_payment(order_id)

        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data=payment_data, message="Payment initialized successfully"
        )

    except Exception as e:
        logger.error(f"Initiate payment error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def verify_payment(request):
    """Verify payment - returns JSON for frontend AJAX call"""
    try:
        reference = request.GET.get("reference")
        order_id = request.GET.get("order_id")

        if not reference:
            return APIResponse.bad_request("Transaction reference is required")

        if order_id and order_id.lower() == "null":
            order_id = None

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
            order = result.get("order")
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

            success, result = OrderService.verify_payment(reference)

            if success:
                logger.info(f"Webhook: Payment successful for reference {reference}")
            else:
                logger.error(f"Webhook: Payment verification failed for {reference}: {result}")

        elif event == "charge.failed":
            data = event_data.get("data", {})
            reference = data.get("reference")

            # Resolve the order from metadata first, then the cached reference.
            order_id = (data.get("metadata") or {}).get("order_id")
            if not order_id and reference:
                from django.core.cache import cache
                order_id = cache.get(f"paystack_ref_{reference}")

            if order_id:
                OrderService.mark_payment_failed(
                    order_id, reason=f"Paystack charge.failed webhook (ref={reference})"
                )
                logger.info(f"Webhook: Payment failed for reference {reference}; stock released")
            else:
                logger.error(f"Webhook: charge.failed could not resolve order for ref {reference}")

        elif event == "charge.dispute.create":
            logger.warning(f"Dispute created: {event_data.get('data', {}).get('reference')}")

        elif event == "refund.processed":
            logger.info(f"Refund processed: {event_data.get('data', {}).get('reference')}")

        return JsonResponse({"status": "success"})

    except Exception as e:
        # Log internally; never echo internal error detail to the caller.
        # Return 200 so Paystack does not retry-storm a non-recoverable error
        # (the signature has already been verified above and processing is
        # idempotent on the transaction reference).
        logger.exception(f"Webhook processing error: {str(e)}")
        return JsonResponse({"status": "received"}, status=200)


@csrf_exempt
@require_http_methods(["GET"])
def payment_callback(request):
    """Handle Paystack payment callback - returns JSON for frontend

    Delegates entirely to PaystackService.process_successful_payment, the
    same path the webhook uses, so the browser-redirect callback gets the
    same amount/currency verification and Transaction record as the webhook
    rather than a second, weaker code path that could mark an order paid
    without either.
    """
    try:
        reference = request.GET.get('reference')
        trxref = request.GET.get('trxref')
        payment_ref = reference or trxref

        if not payment_ref:
            return APIResponse.bad_request("No payment reference found")

        from apps.orders.paystack_service import PaystackService
        success, result = PaystackService.process_successful_payment(reference=payment_ref)

        if not success:
            error_message = (result or {}).get('error', 'Payment verification failed')
            if error_message == 'Order not found':
                return APIResponse.not_found(error_message)
            return APIResponse.bad_request(error_message)

        order = result.get('order')
        if not order:
            return APIResponse.not_found("Order not found")

        serialized_order = serialize_order(order, is_admin=False, detailed=False)

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