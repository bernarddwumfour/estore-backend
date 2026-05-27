"""
Shipment Views - Shipment management endpoints (admin and customer)
"""

import logging
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.orders.selectors import get_order_by_id, get_shipments_filtered
from apps.orders.schemas import (
    serialize_shipment_info,
    serialize_shipment_list,
    serialize_pagination_metadata,
    validate_shipment_update,
)
from apps.orders.models import Order, Shipment
from apps.orders.shipment_service import ShipmentService

logger = logging.getLogger(__name__)


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, "user") or not request.user:
        return False
    return getattr(request.user, "role", "customer") in ["admin", "staff"]


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
        
        if order.payment_method == Order.PAYMENT_CASH_ON_DELIVERY:
            pass
        elif order.payment_status != Order.PAYMENT_PAID:
            return APIResponse.bad_request("Order must be paid before creating shipment")
        
        shipping_cost = None
        if data.get('shipping_cost'):
            shipping_cost = Decimal(str(data['shipping_cost']))
        
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
        
        if data.get('shipping_method'):
            order.shipping_method = data['shipping_method']
            order.save()
        
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
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        
        search = request.GET.get("search", "").strip()
        status = request.GET.get("status")
        carrier = request.GET.get("carrier")
        date_from = request.GET.get("date_from")
        date_to = request.GET.get("date_to")
        
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
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
        
        if order.user != request.user and not _is_admin(request):
            return APIResponse.forbidden("You don't have permission to view this order")
        
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
        try:
            shipment = Shipment.objects.get(tracking_number=tracking_number)
        except Shipment.DoesNotExist:
            return APIResponse.not_found("Shipment not found")
        
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
        
        results = {'success': [], 'failed': [], 'total': len(order_ids)}
        
        for order_id in order_ids:
            try:
                order = get_order_by_id(order_id, include_cancelled=True)
                if not order:
                    results['failed'].append({'id': order_id, 'reason': 'Order not found'})
                    continue
                
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


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_shipment_detail(request, shipment_id):
    """Admin: Get detailed shipment information"""
    try:
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
            "notes": shipment.notes,
            "created_at": shipment.created_at.isoformat(),
            "updated_at": shipment.updated_at.isoformat(),
            "shipped_at": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
            "delivered_at": shipment.delivered_at.isoformat() if shipment.delivered_at else None,
            "created_by": shipment.created_by.email if shipment.created_by else None,
        }
        
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