"""
Transaction Selectors - Database read operations for transactions
No business logic - just queries
"""

from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from decimal import Decimal

from apps.orders.models import Transaction


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