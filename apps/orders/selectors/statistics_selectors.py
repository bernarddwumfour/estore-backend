"""
Statistics Selectors - Database read operations for order statistics
No business logic - just queries
"""

from typing import Dict, Any, List, Tuple
from django.db.models import Q, Sum
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from apps.orders.models import Order, OrderItem


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