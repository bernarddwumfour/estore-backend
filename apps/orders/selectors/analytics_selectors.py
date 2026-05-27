"""
Order Analytics Selectors - Database read operations for order analytics
No business logic - just queries
"""

from django.db.models import Sum, Count, Avg, Q, F, Min, Max, DecimalField, IntegerField, FloatField, ExpressionWrapper
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, Coalesce
from django.utils import timezone
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Any, Tuple

from apps.orders.models import Order, OrderItem, Transaction, Shipment
from apps.users.models import User


class OrderAnalyticsSelector:
    """Selector for order analytics data"""
    
    @staticmethod
    def get_order_summary_stats(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get comprehensive order summary statistics"""
        
        queryset = Order.objects.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Basic metrics - specify output_field for Decimal
        total_orders = queryset.count()
        total_revenue = queryset.aggregate(
            total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        )['total'] or Decimal('0.00')
        
        # Paid orders only
        paid_orders = queryset.filter(payment_status=Order.PAYMENT_PAID)
        paid_revenue = paid_orders.aggregate(
            total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        )['total'] or Decimal('0.00')
        paid_count = paid_orders.count()
        
        # Average order value
        avg_order_value = float(total_revenue / total_orders) if total_orders > 0 else 0
        
        # Customer metrics
        registered_orders = queryset.filter(user__isnull=False)
        guest_orders = queryset.filter(user__isnull=True)
        
        unique_customers = queryset.filter(user__isnull=False).values('user').distinct().count()
        guest_customers = queryset.filter(user__isnull=True).values('guest_email').distinct().count()
        
        # Items sold
        total_items_sold = OrderItem.objects.filter(order__in=queryset).aggregate(
            total=Coalesce(Sum('quantity'), 0, output_field=IntegerField())
        )['total'] or 0
        
        # Payment method distribution
        payment_method_stats = {}
        for method_code, method_name in Order.PAYMENT_METHOD_CHOICES:
            count = queryset.filter(payment_method=method_code).count()
            if count > 0:
                revenue = queryset.filter(payment_method=method_code).aggregate(
                    total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
                )['total'] or Decimal('0.00')
                payment_method_stats[method_code] = {
                    "count": count,
                    "revenue": float(revenue),
                    "percentage": round(count / total_orders * 100, 2) if total_orders > 0 else 0
                }
        
        # Payment type distribution (Online vs POD)
        payment_type_stats = {
            "online": {
                "count": queryset.filter(payment_type=Order.PAYMENT_TYPE_ONLINE).count(),
                "revenue": float(queryset.filter(payment_type=Order.PAYMENT_TYPE_ONLINE).aggregate(
                    total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
                )['total'] or 0)
            },
            "pod": {
                "count": queryset.filter(payment_type=Order.PAYMENT_TYPE_POD).count(),
                "revenue": float(queryset.filter(payment_type=Order.PAYMENT_TYPE_POD).aggregate(
                    total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
                )['total'] or 0)
            }
        }
        
        return {
            "summary": {
                "total_orders": total_orders,
                "total_revenue": float(total_revenue),
                "average_order_value": round(avg_order_value, 2),
                "total_items_sold": total_items_sold,
                "paid_orders": paid_count,
                "paid_revenue": float(paid_revenue),
                "unpaid_orders": total_orders - paid_count,
                "unpaid_revenue": float(total_revenue - paid_revenue),
            },
            "customer_breakdown": {
                "registered_orders": registered_orders.count(),
                "guest_orders": guest_orders.count(),
                "registered_customers": unique_customers,
                "guest_customers": guest_customers,
                "registered_percentage": round(registered_orders.count() / total_orders * 100, 2) if total_orders > 0 else 0,
                "guest_percentage": round(guest_orders.count() / total_orders * 100, 2) if total_orders > 0 else 0,
            },
            "payment_method_stats": payment_method_stats,
            "payment_type_stats": payment_type_stats,
        }
    
    @staticmethod
    def get_sales_trends(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = 'day'
    ) -> List[Dict[str, Any]]:
        """Get sales trends over time"""
        
        queryset = Order.objects.filter(payment_status=Order.PAYMENT_PAID)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Choose truncation function
        trunc_func = {
            'day': TruncDay,
            'week': TruncWeek,
            'month': TruncMonth,
        }.get(interval, TruncDay)
        
        trends = queryset.annotate(
            period=trunc_func('created_at')
        ).values('period').annotate(
            revenue=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField()),
            orders=Count('id'),
            items_sold=Coalesce(Sum('items__quantity'), 0, output_field=IntegerField()),
            avg_order_value=Coalesce(Avg('total'), Decimal('0.00'), output_field=DecimalField()),
        ).order_by('period')
        
        return [
            {
                "period": item['period'].isoformat() if item['period'] else None,
                "revenue": float(item['revenue']),
                "orders": item['orders'],
                "items_sold": item['items_sold'] or 0,
                "average_order_value": float(item['avg_order_value']),
            }
            for item in trends
        ]
    
    @staticmethod
    def get_order_status_distribution(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get distribution of orders by status"""
        
        queryset = Order.objects.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        total = queryset.count()
        status_distribution = {}
        for status_code, status_label in Order.STATUS_CHOICES:
            count = queryset.filter(status=status_code).count()
            if count > 0:
                status_distribution[status_code] = {
                    "count": count,
                    "label": status_label,
                    "percentage": round(count / total * 100, 2) if total > 0 else 0
                }
        
        return status_distribution
    
    @staticmethod
    def get_payment_status_distribution(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get distribution of orders by payment status"""
        
        queryset = Order.objects.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        total = queryset.count()
        payment_distribution = {}
        for status_code, status_label in Order.PAYMENT_STATUS_CHOICES:
            count = queryset.filter(payment_status=status_code).count()
            if count > 0:
                payment_distribution[status_code] = {
                    "count": count,
                    "label": status_label,
                    "percentage": round(count / total * 100, 2) if total > 0 else 0
                }
        
        return payment_distribution
    
    @staticmethod
    def get_top_customers(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get top customers by total spent"""
        
        queryset = Order.objects.filter(payment_status=Order.PAYMENT_PAID)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Registered users
        user_stats = queryset.filter(user__isnull=False).values(
            'user__id', 'user__email', 'user__first_name', 'user__last_name'
        ).annotate(
            total_spent=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField()),
            order_count=Count('id'),
            avg_order_value=Coalesce(Avg('total'), Decimal('0.00'), output_field=DecimalField()),
            first_order=Min('created_at'),
            last_order=Max('created_at')
        ).order_by('-total_spent')[:limit]
        
        result = []
        for stat in user_stats:
            result.append({
                "customer_id": str(stat['user__id']),
                "email": stat['user__email'],
                "name": f"{stat['user__first_name'] or ''} {stat['user__last_name'] or ''}".strip() or stat['user__email'],
                "type": "registered",
                "total_spent": float(stat['total_spent']),
                "order_count": stat['order_count'],
                "average_order_value": float(stat['avg_order_value']),
                "first_order": stat['first_order'].isoformat() if stat['first_order'] else None,
                "last_order": stat['last_order'].isoformat() if stat['last_order'] else None,
            })
        
        # If we need more than registered users, add guests
        if len(result) < limit:
            guest_stats = queryset.filter(user__isnull=True).values(
                'guest_email', 'guest_first_name', 'guest_last_name'
            ).annotate(
                total_spent=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField()),
                order_count=Count('id'),
                avg_order_value=Coalesce(Avg('total'), Decimal('0.00'), output_field=DecimalField()),
                first_order=Min('created_at'),
                last_order=Max('created_at')
            ).order_by('-total_spent')[:limit - len(result)]
            
            for stat in guest_stats:
                result.append({
                    "customer_id": None,
                    "email": stat['guest_email'],
                    "name": f"{stat['guest_first_name'] or ''} {stat['guest_last_name'] or ''}".strip() or stat['guest_email'],
                    "type": "guest",
                    "total_spent": float(stat['total_spent']),
                    "order_count": stat['order_count'],
                    "average_order_value": float(stat['avg_order_value']),
                    "first_order": stat['first_order'].isoformat() if stat['first_order'] else None,
                    "last_order": stat['last_order'].isoformat() if stat['last_order'] else None,
                })
        
        return result
    
    @staticmethod
    def get_fulfillment_analytics(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get fulfillment and shipping analytics"""
        
        queryset = Order.objects.filter(payment_status=Order.PAYMENT_PAID)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        total_orders = queryset.count()
        
        # Shipping method distribution
        shipping_methods = []
        methods = queryset.values('shipping_method').annotate(
            count=Count('id'),
            total_revenue=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        ).order_by('-count')
        
        for item in methods:
            shipping_methods.append({
                "method": item['shipping_method'] or "Standard",
                "count": item['count'],
                "revenue": float(item['total_revenue']),
                "percentage": round(item['count'] / total_orders * 100, 2) if total_orders > 0 else 0
            })
        
        # Fulfillment time (time from order to shipment)
        fulfilled_orders = queryset.filter(shipped_at__isnull=False)
        avg_fulfillment_days = 0
        if fulfilled_orders.exists():
            fulfillment_times = []
            for order in fulfilled_orders:
                if order.created_at and order.shipped_at:
                    delta = order.shipped_at - order.created_at
                    fulfillment_times.append(delta.total_seconds() / 86400)
            avg_fulfillment_days = round(sum(fulfillment_times) / len(fulfillment_times), 2) if fulfillment_times else 0
        
        # Delivery time (time from shipment to delivery)
        delivered_orders = queryset.filter(delivered_at__isnull=False)
        avg_delivery_days = 0
        if delivered_orders.exists():
            delivery_times = []
            for order in delivered_orders:
                if order.shipped_at and order.delivered_at:
                    delta = order.delivered_at - order.shipped_at
                    delivery_times.append(delta.total_seconds() / 86400)
            avg_delivery_days = round(sum(delivery_times) / len(delivery_times), 2) if delivery_times else 0
        
        # Orders by fulfillment status
        fulfillment_status = {
            "pending": queryset.filter(shipped_at__isnull=True, cancelled_at__isnull=True).count(),
            "shipped": queryset.filter(shipped_at__isnull=False, delivered_at__isnull=True).count(),
            "delivered": queryset.filter(delivered_at__isnull=False).count(),
            "cancelled": queryset.filter(cancelled_at__isnull=False).count(),
        }
        
        return {
            "shipping_methods": shipping_methods,
            "fulfillment_times": {
                "average_fulfillment_days": avg_fulfillment_days,
                "average_delivery_days": avg_delivery_days,
                "total_fulfillment_time_days": avg_fulfillment_days + avg_delivery_days,
            },
            "fulfillment_status": fulfillment_status,
        }
    
    @staticmethod
    def get_refund_analytics(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get refund analytics"""
        
        queryset = Order.objects.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Refunded orders
        refunded_orders = queryset.filter(payment_status=Order.PAYMENT_REFUNDED)
        refunded_count = refunded_orders.count()
        refunded_amount = refunded_orders.aggregate(
            total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        )['total'] or Decimal('0.00')
        
        # Transaction refunds
        refund_transactions = Transaction.objects.filter(
            transaction_type=Transaction.TRANSACTION_TYPE_REFUND,
            status=Transaction.TRANSACTION_STATUS_SUCCESS,
            order__in=queryset
        )
        
        total_refunded = refund_transactions.aggregate(
            total=Coalesce(Sum('amount'), Decimal('0.00'), output_field=DecimalField())
        )['total'] or Decimal('0.00')
        
        # Refund reasons
        refund_reasons = {}
        for trans in refund_transactions:
            reason = trans.refund_reason or "No reason provided"
            if reason not in refund_reasons:
                refund_reasons[reason] = {"count": 0, "amount": Decimal('0.00')}
            refund_reasons[reason]["count"] += 1
            refund_reasons[reason]["amount"] += trans.amount
        
        # Refund rate
        total_revenue = queryset.filter(payment_status=Order.PAYMENT_PAID).aggregate(
            total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        )['total'] or Decimal('0.00')
        refund_rate = (float(total_refunded) / float(total_revenue) * 100) if total_revenue > 0 else 0
        
        return {
            "summary": {
                "refunded_orders": refunded_count,
                "refunded_amount": float(refunded_amount),
                "total_refunded": float(total_refunded),
                "refund_rate": round(refund_rate, 2),
                "refund_transactions": refund_transactions.count(),
            },
            "refund_reasons": [
                {"reason": reason, "count": data["count"], "amount": float(data["amount"])}
                for reason, data in refund_reasons.items()
            ],
        }
    
    @staticmethod
    def get_customer_retention_analytics(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """Get customer retention and repeat purchase analytics"""
        
        queryset = Order.objects.filter(payment_status=Order.PAYMENT_PAID, user__isnull=False)
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Count orders per customer
        customer_order_counts = list(queryset.values('user').annotate(
            order_count=Count('id'),
            total_spent=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        ))
        
        # Repeat purchase metrics
        one_time_customers = sum(1 for c in customer_order_counts if c['order_count'] == 1)
        repeat_customers = sum(1 for c in customer_order_counts if c['order_count'] >= 2)
        frequent_customers = sum(1 for c in customer_order_counts if c['order_count'] >= 5)
        
        total_customers = len(customer_order_counts)
        
        # Average orders per customer
        avg_orders = sum(c['order_count'] for c in customer_order_counts) / total_customers if total_customers > 0 else 0
        
        # Customer lifetime value (average total spent)
        avg_clv = sum(float(c['total_spent']) for c in customer_order_counts) / total_customers if total_customers > 0 else 0
        
        return {
            "customer_segments": {
                "one_time_buyers": one_time_customers,
                "repeat_customers": repeat_customers,
                "frequent_customers": frequent_customers,
                "one_time_percentage": round(one_time_customers / total_customers * 100, 2) if total_customers > 0 else 0,
                "repeat_percentage": round(repeat_customers / total_customers * 100, 2) if total_customers > 0 else 0,
            },
            "retention_metrics": {
                "total_customers": total_customers,
                "average_orders_per_customer": round(avg_orders, 2),
                "average_customer_lifetime_value": round(avg_clv, 2),
                "repeat_purchase_rate": round(repeat_customers / total_customers * 100, 2) if total_customers > 0 else 0,
            }
        }
    
    @staticmethod
    def get_hourly_order_distribution(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get distribution of orders by hour of day"""
        
        queryset = Order.objects.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        # Hourly distribution (0-23)
        hourly_data = []
        for hour in range(24):
            count = queryset.filter(created_at__hour=hour).count()
            revenue = queryset.filter(created_at__hour=hour).aggregate(
                total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
            )['total'] or Decimal('0.00')
            
            if count > 0 or revenue > 0:
                hourly_data.append({
                    "hour": hour,
                    "orders": count,
                    "revenue": float(revenue),
                    "display_hour": f"{hour}:00",
                })
        
        return hourly_data
    
    @staticmethod
    def get_day_of_week_distribution(
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """Get distribution of orders by day of week"""
        
        queryset = Order.objects.all()
        
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)
        
        days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
        total = queryset.count()
        result = []
        
        for idx, day in enumerate(days):
            count = queryset.filter(created_at__week_day=idx + 2).count()  # Monday = 2 in Django
            revenue = queryset.filter(created_at__week_day=idx + 2).aggregate(
                total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
            )['total'] or Decimal('0.00')
            
            result.append({
                "day": day,
                "day_index": idx,
                "orders": count,
                "revenue": float(revenue),
                "percentage": round(count / total * 100, 2) if total > 0 else 0,
            })
        
        return result