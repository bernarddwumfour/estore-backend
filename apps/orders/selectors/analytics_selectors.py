"""
Order Analytics Selectors - Database read operations for order analytics
No business logic - just queries
"""

from django.db.models import Sum, Count, Avg, Q, F, Min, Max, DecimalField, IntegerField, FloatField, DurationField, ExpressionWrapper
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth, Coalesce, ExtractHour, ExtractWeekDay
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
        
        # Payment method distribution (single grouped query instead of one query per method)
        payment_method_stats = {}
        payment_method_agg = queryset.values('payment_method').annotate(
            count=Count('id'),
            total=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        )
        for row in payment_method_agg:
            count = row['count']
            if count > 0:
                payment_method_stats[row['payment_method']] = {
                    "count": count,
                    "revenue": float(row['total']),
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
        status_labels = dict(Order.STATUS_CHOICES)
        status_distribution = {}
        status_counts = queryset.values('status').annotate(count=Count('id'))
        for row in status_counts:
            count = row['count']
            if count > 0:
                status_distribution[row['status']] = {
                    "count": count,
                    "label": status_labels.get(row['status'], row['status']),
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
        payment_status_labels = dict(Order.PAYMENT_STATUS_CHOICES)
        payment_distribution = {}
        payment_status_counts = queryset.values('payment_status').annotate(count=Count('id'))
        for row in payment_status_counts:
            count = row['count']
            if count > 0:
                payment_distribution[row['payment_status']] = {
                    "count": count,
                    "label": payment_status_labels.get(row['payment_status'], row['payment_status']),
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
        
        # Fulfillment time (time from order to shipment) - computed DB-side via Avg on a
        # duration expression instead of pulling every order into Python.
        fulfillment_avg = queryset.filter(shipped_at__isnull=False).aggregate(
            avg_duration=Avg(
                ExpressionWrapper(F('shipped_at') - F('created_at'), output_field=DurationField())
            )
        )['avg_duration']
        avg_fulfillment_days = round(fulfillment_avg.total_seconds() / 86400, 2) if fulfillment_avg else 0

        # Delivery time (time from shipment to delivery). Original loop only counted
        # orders that had both shipped_at and delivered_at set, so filter both here too.
        delivery_avg = queryset.filter(
            shipped_at__isnull=False, delivered_at__isnull=False
        ).aggregate(
            avg_duration=Avg(
                ExpressionWrapper(F('delivered_at') - F('shipped_at'), output_field=DurationField())
            )
        )['avg_duration']
        avg_delivery_days = round(delivery_avg.total_seconds() / 86400, 2) if delivery_avg else 0
        
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
        
        # Refund reasons - single grouped query instead of loading every transaction
        refund_reasons = {}
        refund_reason_agg = refund_transactions.values('refund_reason').annotate(
            count=Count('id'),
            amount=Coalesce(Sum('amount'), Decimal('0.00'), output_field=DecimalField())
        )
        refund_transactions_count = 0
        for row in refund_reason_agg:
            reason = row['refund_reason'] or "No reason provided"
            if reason not in refund_reasons:
                refund_reasons[reason] = {"count": 0, "amount": Decimal('0.00')}
            refund_reasons[reason]["count"] += row['count']
            refund_reasons[reason]["amount"] += row['amount']
            refund_transactions_count += row['count']

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
                "refund_transactions": refund_transactions_count,
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
        
        # Hourly distribution (0-23) - single grouped query instead of one pair of
        # queries per hour.
        hourly_agg = queryset.annotate(
            hour=ExtractHour('created_at')
        ).values('hour').annotate(
            orders=Count('id'),
            revenue=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        ).order_by('hour')

        hourly_data = []
        for row in hourly_agg:
            count = row['orders']
            revenue = row['revenue']
            if count > 0 or revenue > 0:
                hourly_data.append({
                    "hour": row['hour'],
                    "orders": count,
                    "revenue": float(revenue),
                    "display_hour": f"{row['hour']}:00",
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

        # Single grouped query instead of one pair of queries per day. ExtractWeekDay
        # uses the same convention as the __week_day lookup (Sunday=1 ... Saturday=7),
        # so we key the lookup the same way the original per-day loop did (idx + 2).
        weekday_agg = queryset.annotate(
            weekday=ExtractWeekDay('created_at')
        ).values('weekday').annotate(
            orders=Count('id'),
            revenue=Coalesce(Sum('total'), Decimal('0.00'), output_field=DecimalField())
        )
        weekday_map = {row['weekday']: row for row in weekday_agg}

        for idx, day in enumerate(days):
            row = weekday_map.get(idx + 2)  # Monday = 2 in Django
            count = row['orders'] if row else 0
            revenue = row['revenue'] if row else Decimal('0.00')

            result.append({
                "day": day,
                "day_index": idx,
                "orders": count,
                "revenue": float(revenue),
                "percentage": round(count / total * 100, 2) if total > 0 else 0,
            })

        return result