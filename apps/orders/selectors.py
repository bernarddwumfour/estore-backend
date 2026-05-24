# apps/orders/selectors.py

from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from apps.orders.models import Order, OrderItem, Transaction, Shipment
from apps.users.models import Address
import logging

logger = logging.getLogger(__name__)


# ==================== ORDER SELECTORS ====================

def get_order_by_id(order_id: str, include_cancelled: bool = False) -> Optional[Order]:
    """Get order by ID or order number"""
    try:
        queryset = Order.objects.select_related(
            'user', 'shipping_address', 'billing_address'
        ).prefetch_related("items", "items__variant", "transactions")
        
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


def get_admin_orders_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    status: str = None,
    payment_status: str = None,
    payment_method: str = None,
    date_from: str = None,
    date_to: str = None,
    min_total: float = None,
    max_total: float = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[Order], int, Dict]:
    """
    Get filtered, sorted, and paginated orders for admin
    """
    queryset = Order.objects.select_related(
        'user', 'shipping_address', 'billing_address'
    ).prefetch_related('items', 'items__variant', 'transactions')
    
    # Filter by status
    if status:
        queryset = queryset.filter(status=status)
    
    # Filter by payment status
    if payment_status:
        queryset = queryset.filter(payment_status=payment_status)
    
    # Filter by payment method
    if payment_method:
        queryset = queryset.filter(payment_method=payment_method)
    
    # Search by order number, customer name, email
    if search:
        queryset = queryset.filter(
            Q(order_number__icontains=search) |
            Q(guest_email__icontains=search) |
            Q(guest_first_name__icontains=search) |
            Q(guest_last_name__icontains=search) |
            Q(user__email__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(shipping_address__first_name__icontains=search) |
            Q(shipping_address__last_name__icontains=search)
        )
    
    # Filter by date range
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    
    # Filter by total amount range
    if min_total is not None:
        queryset = queryset.filter(total__gte=Decimal(str(min_total)))
    if max_total is not None:
        queryset = queryset.filter(total__lte=Decimal(str(max_total)))
    
    # Apply sorting
    allowed_sort_fields = {
        'created_at': 'created_at',
        'total': 'total',
        'subtotal': 'subtotal',
        'status': 'status',
        'payment_status': 'payment_status',
        'order_number': 'order_number',
    }
    
    if sort_by in allowed_sort_fields:
        sort_field = allowed_sort_fields[sort_by]
        if sort_order == "desc":
            sort_field = f"-{sort_field}"
        queryset = queryset.order_by(sort_field)
    else:
        queryset = queryset.order_by("-created_at")
    
    # Get total count before pagination
    total = queryset.count()
    
    # Apply pagination
    paginator = Paginator(queryset, limit)
    
    try:
        orders_page = paginator.page(page)
    except PageNotAnInteger:
        orders_page = paginator.page(1)
        page = 1
    except EmptyPage:
        orders_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    # Calculate pagination metadata
    total_pages = paginator.num_pages
    has_next = orders_page.has_next()
    has_previous = orders_page.has_previous()
    
    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_page": page + 1 if has_next else None,
        "previous_page": page - 1 if has_previous else None,
        "start_index": (page - 1) * limit + 1 if total > 0 else 0,
        "end_index": min(page * limit, total),
    }
    
    return list(orders_page), total, pagination_meta


def get_admin_orders(
    page: int = 1,
    limit: int = 20,
    status: str = None,
    payment_status: str = None,
    search: str = None,
    date_from: str = None,
    date_to: str = None,
) -> Tuple[List[Order], int]:
    """Legacy function - kept for compatibility"""
    orders, total, _ = get_admin_orders_filtered(
        page=page,
        limit=limit,
        search=search,
        status=status,
        payment_status=payment_status,
        date_from=date_from,
        date_to=date_to,
    )
    return orders, total


def get_order_statistics_filtered(
    status: str = None,
    payment_status: str = None,
    date_from: str = None,
    date_to: str = None,
) -> Dict[str, Any]:
    """
    Get filtered order statistics
    """
    queryset = Order.objects.all()
    
    if status:
        queryset = queryset.filter(status=status)
    if payment_status:
        queryset = queryset.filter(payment_status=payment_status)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    
    stats = {
        "total_orders": queryset.count(),
        "total_revenue": float(queryset.aggregate(total=Sum('total'))['total'] or 0),
        "average_order_value": 0,
        "total_items_sold": OrderItem.objects.filter(order__in=queryset).aggregate(total=Sum('quantity'))['total'] or 0,
    }
    
    if stats["total_orders"] > 0:
        stats["average_order_value"] = round(stats["total_revenue"] / stats["total_orders"], 2)
    
    # Status distribution
    stats["by_status"] = {
        status_code: queryset.filter(status=status_code).count()
        for status_code, _ in Order.STATUS_CHOICES
    }
    
    # Payment status distribution
    stats["by_payment_status"] = {
        status_code: queryset.filter(payment_status=status_code).count()
        for status_code, _ in Order.PAYMENT_STATUS_CHOICES
    }
    
    # Payment method distribution
    stats["by_payment_method"] = {
        'paystack': queryset.filter(payment_method='paystack').count(),
        'pod': queryset.filter(payment_method='pod').count(),
    }
    
    return stats


def get_order_statistics() -> Dict[str, Any]:
    """Legacy function - kept for compatibility"""
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


# ==================== SHIPMENT SELECTORS ====================

def get_shipments_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    status: str = None,
    carrier: str = None,
    date_from: str = None,
    date_to: str = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[Shipment], int, Dict]:
    """
    Get filtered, sorted, and paginated shipments for admin
    """
    queryset = Shipment.objects.select_related('order', 'order__user', 'order__shipping_address')
    
    # Filter by status
    if status:
        queryset = queryset.filter(status=status)
    
    # Filter by carrier
    if carrier:
        queryset = queryset.filter(carrier__icontains=carrier)
    
    # Filter by date range
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    
    # Search by tracking number, order number, customer
    if search:
        queryset = queryset.filter(
            Q(tracking_number__icontains=search) |
            Q(order__order_number__icontains=search) |
            Q(order__guest_email__icontains=search) |
            Q(order__user__email__icontains=search) |
            Q(order__shipping_address__first_name__icontains=search) |
            Q(order__shipping_address__last_name__icontains=search)
        )
    
    # Apply sorting
    allowed_sort_fields = {
        'created_at': 'created_at',
        'shipped_at': 'shipped_at',
        'delivered_at': 'delivered_at',
        'status': 'status',
    }
    
    if sort_by in allowed_sort_fields:
        sort_field = allowed_sort_fields[sort_by]
        if sort_order == "desc":
            sort_field = f"-{sort_field}"
        queryset = queryset.order_by(sort_field)
    else:
        queryset = queryset.order_by("-created_at")
    
    # Get total count before pagination
    total = queryset.count()
    
    # Apply pagination
    paginator = Paginator(queryset, limit)
    
    try:
        shipments_page = paginator.page(page)
    except PageNotAnInteger:
        shipments_page = paginator.page(1)
        page = 1
    except EmptyPage:
        shipments_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    # Calculate pagination metadata
    total_pages = paginator.num_pages
    has_next = shipments_page.has_next()
    has_previous = shipments_page.has_previous()
    
    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_page": page + 1 if has_next else None,
        "previous_page": page - 1 if has_previous else None,
        "start_index": (page - 1) * limit + 1 if total > 0 else 0,
        "end_index": min(page * limit, total),
    }
    
    return list(shipments_page), total, pagination_meta


def get_orders_by_shipment_status(
    status: str = None,
    page: int = 1,
    limit: int = 20,
    search: str = None,
) -> Tuple[List[Order], int]:
    """Get orders filtered by shipment status (legacy)"""
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


def get_shipment_tracking(shipment_id: str) -> List[Dict]:
    """Get shipment tracking history"""
    from apps.orders.models import ShipmentTracking
    
    tracking = ShipmentTracking.objects.filter(shipment_id=shipment_id).order_by('-created_at')
    return list(tracking)


def get_shipment_by_id(shipment_id: str) -> Optional[Shipment]:
    """Get shipment by ID"""
    try:
        return Shipment.objects.select_related('order', 'order__user', 'order__shipping_address').get(id=shipment_id)
    except Shipment.DoesNotExist:
        return None


# ==================== TRANSACTION SELECTORS ====================

def get_transactions_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    transaction_type: str = None,
    status: str = None,
    payment_method: str = None,
    date_from: str = None,
    date_to: str = None,
    min_amount: float = None,
    max_amount: float = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[Transaction], int, Dict]:
    """
    Get filtered, sorted, and paginated transactions for admin
    """
    queryset = Transaction.objects.select_related('order', 'parent_transaction')
    
    # Filter by transaction type
    if transaction_type:
        queryset = queryset.filter(transaction_type=transaction_type)
    
    # Filter by status
    if status:
        queryset = queryset.filter(status=status)
    
    # Filter by payment method
    if payment_method:
        queryset = queryset.filter(payment_method__icontains=payment_method)
    
    # Filter by date range
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    
    # Filter by amount range
    if min_amount is not None:
        queryset = queryset.filter(amount__gte=Decimal(str(min_amount)))
    if max_amount is not None:
        queryset = queryset.filter(amount__lte=Decimal(str(max_amount)))
    
    # Search by transaction ID, reference, order number
    if search:
        queryset = queryset.filter(
            Q(transaction_id__icontains=search) |
            Q(reference__icontains=search) |
            Q(order__order_number__icontains=search) |
            Q(order__guest_email__icontains=search) |
            Q(order__user__email__icontains=search)
        )
    
    # Apply sorting
    allowed_sort_fields = {
        'created_at': 'created_at',
        'amount': 'amount',
        'status': 'status',
        'transaction_type': 'transaction_type',
        'completed_at': 'completed_at',
    }
    
    if sort_by in allowed_sort_fields:
        sort_field = allowed_sort_fields[sort_by]
        if sort_order == "desc":
            sort_field = f"-{sort_field}"
        queryset = queryset.order_by(sort_field)
    else:
        queryset = queryset.order_by("-created_at")
    
    # Get total count before pagination
    total = queryset.count()
    
    # Apply pagination
    paginator = Paginator(queryset, limit)
    
    try:
        transactions_page = paginator.page(page)
    except PageNotAnInteger:
        transactions_page = paginator.page(1)
        page = 1
    except EmptyPage:
        transactions_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    # Calculate pagination metadata
    total_pages = paginator.num_pages
    has_next = transactions_page.has_next()
    has_previous = transactions_page.has_previous()
    
    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_page": page + 1 if has_next else None,
        "previous_page": page - 1 if has_previous else None,
        "start_index": (page - 1) * limit + 1 if total > 0 else 0,
        "end_index": min(page * limit, total),
    }
    
    return list(transactions_page), total, pagination_meta


def get_order_transactions(order_id: str) -> List[Transaction]:
    """Get all transactions for an order"""
    return list(Transaction.objects.filter(order_id=order_id).order_by('-created_at'))


def get_transaction_by_id(transaction_id: str) -> Optional[Transaction]:
    """Get transaction by transaction ID"""
    try:
        return Transaction.objects.select_related('order', 'parent_transaction').get(transaction_id=transaction_id)
    except Transaction.DoesNotExist:
        return None


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


def get_transaction_statistics() -> Dict[str, Any]:
    """Get transaction statistics"""
    stats = {
        "total_charges": float(Transaction.objects.filter(transaction_type='charge', status='success').aggregate(total=Sum('amount'))['total'] or 0),
        "total_refunds": float(Transaction.objects.filter(transaction_type='refund', status='success').aggregate(total=Sum('amount'))['total'] or 0),
        "net_revenue": float(Transaction.objects.filter(transaction_type='charge', status='success').aggregate(total=Sum('amount'))['total'] or 0) - 
                      float(Transaction.objects.filter(transaction_type='refund', status='success').aggregate(total=Sum('amount'))['total'] or 0),
        "successful_count": Transaction.objects.filter(status='success').count(),
        "failed_count": Transaction.objects.filter(status='failed').count(),
        "pending_count": Transaction.objects.filter(status='pending').count(),
    }
    
    return stats