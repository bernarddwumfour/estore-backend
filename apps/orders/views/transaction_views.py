"""
Transaction Views - Transaction and refund management endpoints
"""

import logging
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.orders.selectors import (
    get_order_by_id,
    get_order_transactions,
    get_refundable_amount,
    get_transactions_filtered,
)
from apps.orders.schemas import (
    serialize_transaction,
    serialize_transaction_list,
    serialize_pagination_metadata,
    validate_refund_request,
)
from apps.orders.models import Order, Transaction
from apps.orders.transaction_service import TransactionService

logger = logging.getLogger(__name__)


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, "user") or not request.user:
        return False
    return getattr(request.user, "role", "customer") in ["admin", "staff"]


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def order_transactions(request, order_id):
    """Get all transactions for an order"""
    try:
        order = get_order_by_id(order_id, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")
        
        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to view this order")
        
        transactions = get_order_transactions(order_id)
        is_admin = _is_admin(request)
        
        transactions_data = [serialize_transaction(t, is_admin=is_admin) for t in transactions]
        
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
        
        cleaned, errors = validate_refund_request(data)
        if errors:
            return APIResponse.validation_error(errors)
        
        order = get_order_by_id(order_id, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")
        
        if order.payment_status not in [Order.PAYMENT_PAID, Order.PAYMENT_PARTIALLY_REFUNDED]:
            return APIResponse.bad_request("Order cannot be refunded in its current payment status")
        
        transaction_obj, error = TransactionService.record_refund(
            order_id=order_id,
            amount=Decimal(str(cleaned['amount'])),
            refund_reason=cleaned.get('refund_reason', ''),
            notes=cleaned.get('admin_note', ''),
        )
        
        if error:
            return APIResponse.validation_error(error)
        
        transaction_data = serialize_transaction(transaction_obj, is_admin=True)
        
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
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        
        search = request.GET.get("search", "").strip()
        transaction_type = request.GET.get("type")
        status = request.GET.get("status")
        payment_method = request.GET.get("payment_method")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        min_amount = request.GET.get("min_amount")
        max_amount = request.GET.get("max_amount")
        
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
        min_amount_float = float(min_amount) if min_amount else None
        max_amount_float = float(max_amount) if max_amount else None
        
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
        
        from django.db.models import Sum
        
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
        
        transaction_data = serialize_transaction(transaction, is_admin=True)
        
        refunds = transaction.refunds.all()
        if refunds:
            transaction_data['refunds'] = [serialize_transaction(r, is_admin=True) for r in refunds]
        
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