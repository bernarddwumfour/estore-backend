"""
POS Views - Point of Sale order creation for admin/staff
"""

import logging
import time
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from django.db import transaction, models
from django.db.models import Q

from estore.utils.responses import APIResponse
from apps.users.decorators.auth import jwt_required, role_required, json_request_required
from apps.common.logging import log_action, LogSeverity, get_user_info
from apps.orders.selectors import get_order_by_id
from apps.orders.schemas import serialize_order
from apps.orders.order_service import OrderService
from apps.products.models import ProductVariant
from apps.promotions.models import Promotion
from apps.users.models import User

logger = logging.getLogger(__name__)
APP_NAME = "orders"


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def pos_create_order(request):
    """POS: Create an order (for admin/staff in dashboard)"""
    start_time = time.time()
    action = "pos_create_order"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="POS order creation request",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = request.json_data
        
        customer_id = data.get('customer_id')
        customer_email = data.get('customer_email')
        is_guest = data.get('is_guest', True)
        
        if not is_guest and customer_id:
            try:
                order_user = User.objects.get(id=customer_id, is_active=True)
            except User.DoesNotExist:
                return APIResponse.not_found("Customer not found")
        elif not is_guest and customer_email:
            try:
                order_user = User.objects.get(email=customer_email, is_active=True)
            except User.DoesNotExist:
                return APIResponse.not_found(f"Customer with email {customer_email} not found")
        else:
            order_user = None
        
        items = []
        for item in data.get('items', []):
            if item.get('is_bundle'):
                try:
                    promotion = Promotion.objects.get(id=item['bundle_id'], status=Promotion.STATUS_ACTIVE)
                    
                    if not promotion.is_currently_active:
                        return APIResponse.bad_request(f"Promotion {promotion.name} is no longer active")
                    
                    if not promotion.has_stock:
                        return APIResponse.bad_request(f"Promotion {promotion.name} is out of stock")
                    
                    items.append({
                        'is_bundle': True,
                        'bundle_id': str(promotion.id),
                        'bundle_name': promotion.name,
                        'price': float(promotion.bundle_price),
                        'quantity': item.get('quantity', 1),
                        'bundle_items': [
                            {
                                'variant_id': str(bi.variant.id),
                                'quantity': bi.quantity,
                                'is_free': bi.is_free,
                                'original_price': float(bi.original_price),
                            }
                            for bi in promotion.items.all()
                        ],
                    })
                except Promotion.DoesNotExist:
                    return APIResponse.not_found(f"Promotion not found: {item['bundle_id']}")
            else:
                variant = ProductVariant.objects.select_related('product').get(
                    id=item['variant_id'], is_active=True
                )
                items.append({
                    'is_bundle': False,
                    'variant_id': str(variant.id),
                    'quantity': item.get('quantity', 1),
                    'price': float(variant.discounted_price),
                })
        
        if not items:
            return APIResponse.bad_request("No items to order")
        
        shipping_address = {
            'first_name': data.get('shipping_address', {}).get('first_name', user.first_name if user else ''),
            'last_name': data.get('shipping_address', {}).get('last_name', user.last_name if user else ''),
            'email': data.get('shipping_address', {}).get('email', user.email if user else customer_email or ''),
            'phone': data.get('shipping_address', {}).get('phone', ''),
            'address_line1': data.get('shipping_address', {}).get('address_line1', ''),
            'address_line2': data.get('shipping_address', {}).get('address_line2', ''),
            'city': data.get('shipping_address', {}).get('city', ''),
            'state': data.get('shipping_address', {}).get('state', ''),
            'postal_code': data.get('shipping_address', {}).get('postal_code', ''),
            'country': data.get('shipping_address', {}).get('country', 'GH'),
        }
        
        order, error = OrderService.create_order(
            user=order_user,
            items=items,
            shipping_address_data=shipping_address,
            payment_method=data.get('payment_method', 'cash_on_delivery'),
            guest_info={
                'email': customer_email or shipping_address['email'],
                'first_name': shipping_address['first_name'],
                'last_name': shipping_address['last_name'],
                'phone': shipping_address['phone'],
            } if not order_user else None,
            customer_note=data.get('customer_note', ''),
            currency=data.get('currency', 'GHS'),
        )
        
        if error:
            duration_ms = (time.time() - start_time) * 1000
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action=action,
                description=f"POS order creation failed: {error}",
                status_code=400,
                user=user,
                request=request,
                app_name=APP_NAME,
                extra={"error": error, "duration_ms": round(duration_ms, 2)}
            )
            return APIResponse.validation_error(error)
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action=action,
            description=f"POS order created: {order.order_number}",
            status_code=201,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={
                "order_id": str(order.id),
                "order_number": order.order_number,
                "items_count": len(items),
                "total": float(order.total),
                "customer": order.customer_email,
                "duration_ms": round(duration_ms, 2),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.created(
            data={
                "order": serialize_order(order, is_admin=True, detailed=True),
            },
            message="POS order created successfully"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"POS order creation error: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def pos_search_customers(request):
    """Search customers for POS order creation"""
    start_time = time.time()
    action = "pos_search_customers"
    user = request.user
    
    try:
        search = request.GET.get('search', '').strip()
        limit = min(int(request.GET.get('limit', 20)), 50)
        
        if not search or len(search) < 2:
            return APIResponse.success(
                data={"customers": []},
                message="Enter at least 2 characters to search"
            )
        
        customers = User.objects.filter(
            is_active=True,
            role__in=['customer', 'admin', 'staff']
        ).filter(
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        ).values('id', 'email', 'first_name', 'last_name')[:limit]
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Customer search completed: {customers.count()} results",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"search_term": search, "results_count": customers.count(), "duration_ms": round(duration_ms, 2)}
        )
        
        return APIResponse.success(
            data={
                "customers": [
                    {
                        "id": str(c['id']),
                        "email": c['email'],
                        "name": f"{c['first_name']} {c['last_name']}".strip() or c['email'],
                        "first_name": c['first_name'],
                        "last_name": c['last_name'],
                    }
                    for c in customers
                ]
            },
            message="Customers retrieved"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Customer search error: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def pos_get_active_promotions(request):
    """Get active promotions for POS interface"""
    start_time = time.time()
    action = "pos_get_active_promotions"
    user = request.user
    
    try:
        from django.utils import timezone
        now = timezone.now()
        
        promotions = Promotion.objects.filter(
            status=Promotion.STATUS_ACTIVE,
            starts_at__lte=now,
        ).filter(
            Q(ends_at__isnull=True) | Q(ends_at__gte=now)
        ).values('id', 'name', 'slug', 'bundle_price', 'original_total', 'savings_amount', 'savings_percentage')
        
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.DEBUG,
            action=action,
            description=f"Active promotions retrieved: {promotions.count()}",
            status_code=200,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"promotions_count": promotions.count(), "duration_ms": round(duration_ms, 2)}
        )
        
        return APIResponse.success(
            data={
                "promotions": [
                    {
                        "id": str(p['id']),
                        "name": p['name'],
                        "slug": p['slug'],
                        "bundle_price": float(p['bundle_price']),
                        "original_total": float(p['original_total']),
                        "savings_amount": float(p['savings_amount']),
                        "savings_percentage": p['savings_percentage'],
                    }
                    for p in promotions
                ]
            },
            message="Active promotions retrieved"
        )
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_action(
            logger=logger,
            severity=LogSeverity.ERROR,
            action=action,
            description=f"Get promotions error: {str(e)}",
            status_code=500,
            user=user,
            request=request,
            app_name=APP_NAME,
            extra={"error": str(e), "duration_ms": round(duration_ms, 2)}
        )
        return APIResponse.server_error()