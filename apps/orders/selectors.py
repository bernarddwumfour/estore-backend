# apps/orders/selectors.py
from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q, Sum
from django.core.paginator import Paginator
from apps.orders.models import Order, OrderItem
from apps.users.models import Address
from decimal import Decimal
from .models import Transaction


# ==================== ORDER SELECTORS ====================

def get_order_by_id(order_id: str, include_cancelled: bool = False) -> Optional[Order]:
    """Get order by ID or order number"""
    try:
        queryset = Order.objects.all().prefetch_related("items__variant")
        if not include_cancelled:
            queryset = queryset.exclude(status=Order.STATUS_CANCELLED)
        
        # Try by UUID first
        try:
            return queryset.get(id=order_id)
        except (ValueError, Order.DoesNotExist):
            # Try by order number
            return queryset.get(order_number=order_id)
    except Order.DoesNotExist:
        return None


def get_user_orders(
    user,
    page: int = 1,
    limit: int = 10,
    status: str = None,
    payment_status: str = None,
) -> Tuple[List[Order], int]:
    """Get paginated orders for a user"""
    queryset = Order.objects.filter(user=user).select_related(
        'shipping_address', 'billing_address'
    ).prefetch_related('items', 'items__variant')
    
    if status:
        queryset = queryset.filter(status=status)
    if payment_status:
        queryset = queryset.filter(payment_status=payment_status)
    
    queryset = queryset.order_by('-created_at')
    
    paginator = Paginator(queryset, limit)
    page_obj = paginator.get_page(page)
    
    return list(page_obj), paginator.count


def get_admin_orders(
    page: int = 1,
    limit: int = 20,
    status: str = None,
    payment_status: str = None,
    search: str = None,
    date_from: str = None,
    date_to: str = None,
) -> Tuple[List[Order], int]:
    """Get paginated orders for admin"""
    queryset = Order.objects.select_related(
        'user', 'shipping_address', 'billing_address'
    ).prefetch_related('items', 'items__variant')
    
    if status:
        queryset = queryset.filter(status=status)
    if payment_status:
        queryset = queryset.filter(payment_status=payment_status)
    if search:
        queryset = queryset.filter(
            Q(order_number__icontains=search) |
            Q(guest_email__icontains=search) |
            Q(user__email__icontains=search) |
            Q(shipping_address__first_name__icontains=search) |
            Q(shipping_address__last_name__icontains=search)
        )
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    
    queryset = queryset.order_by('-created_at')
    
    paginator = Paginator(queryset, limit)
    page_obj = paginator.get_page(page)
    
    return list(page_obj), paginator.count


def get_order_statistics() -> Dict[str, Any]:
    """Get order statistics for admin dashboard"""
    from django.utils import timezone
    from datetime import timedelta
    
    today = timezone.now().date()
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    stats = {
        'total_orders': Order.objects.count(),
        'total_revenue': float(Order.objects.aggregate(total=Sum('total'))['total'] or 0),
        'average_order_value': 0,
    }
    
    # Today's stats
    stats['today'] = {
        'orders': Order.objects.filter(created_at__date=today).count(),
        'revenue': float(Order.objects.filter(created_at__date=today).aggregate(total=Sum('total'))['total'] or 0),
    }
    
    # This week stats
    stats['this_week'] = {
        'orders': Order.objects.filter(created_at__date__gte=week_ago).count(),
        'revenue': float(Order.objects.filter(created_at__date__gte=week_ago).aggregate(total=Sum('total'))['total'] or 0),
    }
    
    # This month stats
    stats['this_month'] = {
        'orders': Order.objects.filter(created_at__date__gte=month_ago).count(),
        'revenue': float(Order.objects.filter(created_at__date__gte=month_ago).aggregate(total=Sum('total'))['total'] or 0),
    }
    
    # Status distribution
    stats['status_distribution'] = {
        status_code: Order.objects.filter(status=status_code).count()
        for status_code, _ in Order.STATUS_CHOICES
    }
    
    # Payment status distribution
    stats['payment_status_distribution'] = {
        status_code: Order.objects.filter(payment_status=status_code).count()
        for status_code, _ in Order.PAYMENT_STATUS_CHOICES
    }
    
    # Calculate average order value
    if stats['total_orders'] > 0:
        stats['average_order_value'] = round(stats['total_revenue'] / stats['total_orders'], 2)
    
    return stats


def get_order_items(order_id: str) -> List[OrderItem]:
    """Get all items for an order"""
    return list(OrderItem.objects.filter(order_id=order_id).select_related('variant'))


# ==================== ADDRESS SELECTORS ====================

def get_user_addresses(user, address_type: str = None, only_active: bool = True) -> List[Address]:
    """Get addresses for a user"""
    queryset = Address.objects.filter(user=user)
    
    if only_active:
        queryset = queryset.filter(is_active=True)
    if address_type:
        queryset = queryset.filter(address_type=address_type)
    
    return list(queryset.order_by('-is_default', '-created_at'))


def get_address_by_id(address_id: str, user=None) -> Optional[Address]:
    """Get address by ID"""
    try:
        queryset = Address.objects.all()
        if user:
            queryset = queryset.filter(user=user)
        return queryset.get(id=address_id)
    except Address.DoesNotExist:
        return None
    

# apps/orders/selectors.py - Add these functions



def get_orders_by_shipment_status(
    status: str = None,
    page: int = 1,
    limit: int = 20,
    search: str = None,
) -> Tuple[List[Order], int]:
    """Get orders filtered by shipment status"""
    queryset = Order.objects.select_related('user', 'shipping_address').prefetch_related('items')
    
    if status:
        queryset = queryset.filter(shipment__status=status)
    
    if search:
        queryset = queryset.filter(
            Q(order_number__icontains=search) |
            Q(shipment__tracking_number__icontains=search) |
            Q(shipment__carrier__icontains=search)
        )
    
    queryset = queryset.filter(shipment__isnull=False).order_by('-created_at')
    
    paginator = Paginator(queryset, limit)
    page_obj = paginator.get_page(page)
    
    return list(page_obj), paginator.count


def get_order_transactions(order_id: str) -> List[Transaction]:
    """Get all transactions for an order"""
    return list(Transaction.objects.filter(order_id=order_id).order_by('-created_at'))


def get_refundable_amount(order_id: str) -> Decimal:
    """Calculate the maximum refundable amount for an order"""
    # Get total charged amount
    charged_amount = Transaction.objects.filter(
        order_id=order_id,
        transaction_type='charge',
        status='success'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    # Get total refunded amount
    refunded_amount = Transaction.objects.filter(
        order_id=order_id,
        transaction_type='refund',
        status='success'
    ).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    
    return charged_amount - refunded_amount


def get_shipment_tracking(shipment_id: str) -> List[Dict]:
    """Get shipment tracking history"""
    from apps.orders.models import ShipmentTracking
    
    tracking = ShipmentTracking.objects.filter(shipment_id=shipment_id).order_by('-created_at')
    return list(tracking)