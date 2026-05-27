"""
Shipment Selectors - Database read operations for shipments
No business logic - just queries
"""

from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger

from apps.orders.models import Order, Shipment


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
    