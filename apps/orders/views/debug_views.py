"""
Debug Views - Debugging endpoints for orders
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required
from apps.orders.selectors import get_order_by_id
from apps.orders.models import Transaction

logger = logging.getLogger(__name__)


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, "user") or not request.user:
        return False
    return getattr(request.user, "role", "customer") in ["admin", "staff"]


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
def order_debug_info(request, order_id):
    """Debug view to check order transactions and shipment"""
    try:
        order = get_order_by_id(order_id, include_cancelled=True)
        if not order:
            return APIResponse.not_found("Order not found")
        
        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to view this order")
        
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