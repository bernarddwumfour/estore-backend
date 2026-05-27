"""
Order Selectors - Database read operations for orders
No business logic - just queries
"""

from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from decimal import Decimal

from apps.orders.models import Order, OrderItem


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


def get_order_items(order_id: str) -> List[OrderItem]:
    """Get all items for an order"""
    return list(OrderItem.objects.filter(order_id=order_id).select_related('variant'))