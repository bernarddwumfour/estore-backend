"""
Order Analytics Schemas - Serialization and validation for order analytics
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal

from apps.common.schemas.analytics_schemas import (
    validate_date_range,
    validate_interval,
    validate_limit,
)


# ==================== HELPER FUNCTIONS ====================

def format_decimal(value: Decimal, default: float = 0.0) -> float:
    """Format decimal to float for JSON response"""
    if value is None:
        return default
    return float(value)


# ==================== SUMMARY STATS SERIALIZER ====================

def serialize_order_summary_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize order summary statistics"""
    return {
        "summary": {
            "total_orders": stats["summary"]["total_orders"],
            "total_revenue": format_decimal(stats["summary"]["total_revenue"]),
            "average_order_value": stats["summary"]["average_order_value"],
            "total_items_sold": stats["summary"]["total_items_sold"],
            "paid_orders": stats["summary"]["paid_orders"],
            "paid_revenue": format_decimal(stats["summary"]["paid_revenue"]),
            "unpaid_orders": stats["summary"]["unpaid_orders"],
            "unpaid_revenue": format_decimal(stats["summary"]["unpaid_revenue"]),
        },
        "customer_breakdown": {
            "registered_orders": stats["customer_breakdown"]["registered_orders"],
            "guest_orders": stats["customer_breakdown"]["guest_orders"],
            "registered_customers": stats["customer_breakdown"]["registered_customers"],
            "guest_customers": stats["customer_breakdown"]["guest_customers"],
            "registered_percentage": stats["customer_breakdown"]["registered_percentage"],
            "guest_percentage": stats["customer_breakdown"]["guest_percentage"],
        },
        "payment_method_stats": stats["payment_method_stats"],
        "payment_type_stats": stats["payment_type_stats"],
    }


# ==================== SALES TRENDS SERIALIZER ====================

def serialize_sales_trends(trends: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize sales trends"""
    return [
        {
            "period": t["period"],
            "revenue": format_decimal(t["revenue"]),
            "orders": t["orders"],
            "items_sold": t["items_sold"],
            "average_order_value": format_decimal(t["average_order_value"]),
        }
        for t in trends
    ]


# ==================== STATUS DISTRIBUTION SERIALIZERS ====================

def serialize_status_distribution(distribution: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize order status distribution"""
    return distribution


def serialize_payment_status_distribution(distribution: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize payment status distribution"""
    return distribution


# ==================== TOP CUSTOMERS SERIALIZER ====================

def serialize_top_customers(customers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize top customers"""
    return [
        {
            "customer_id": c["customer_id"],
            "email": c["email"],
            "name": c["name"],
            "type": c["type"],
            "total_spent": format_decimal(c["total_spent"]),
            "order_count": c["order_count"],
            "average_order_value": format_decimal(c["average_order_value"]),
            "first_order": c["first_order"],
            "last_order": c["last_order"],
        }
        for c in customers
    ]


# ==================== FULFILLMENT ANALYTICS SERIALIZER ====================

def serialize_fulfillment_analytics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize fulfillment analytics"""
    return {
        "shipping_methods": [
            {
                "method": m["method"],
                "count": m["count"],
                "revenue": format_decimal(m["revenue"]),
                "percentage": m["percentage"],
            }
            for m in data["shipping_methods"]
        ],
        "fulfillment_times": {
            "average_fulfillment_days": data["fulfillment_times"]["average_fulfillment_days"],
            "average_delivery_days": data["fulfillment_times"]["average_delivery_days"],
            "total_fulfillment_time_days": data["fulfillment_times"]["total_fulfillment_time_days"],
        },
        "fulfillment_status": data["fulfillment_status"],
    }


# ==================== REFUND ANALYTICS SERIALIZER ====================

def serialize_refund_analytics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize refund analytics"""
    return {
        "summary": {
            "refunded_orders": data["summary"]["refunded_orders"],
            "refunded_amount": format_decimal(data["summary"]["refunded_amount"]),
            "total_refunded": format_decimal(data["summary"]["total_refunded"]),
            "refund_rate": data["summary"]["refund_rate"],
            "refund_transactions": data["summary"]["refund_transactions"],
        },
        "refund_reasons": [
            {
                "reason": r["reason"],
                "count": r["count"],
                "amount": format_decimal(r["amount"]),
            }
            for r in data["refund_reasons"]
        ],
    }


# ==================== CUSTOMER RETENTION SERIALIZER ====================

def serialize_customer_retention_analytics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize customer retention analytics"""
    return {
        "customer_segments": {
            "one_time_buyers": data["customer_segments"]["one_time_buyers"],
            "repeat_customers": data["customer_segments"]["repeat_customers"],
            "frequent_customers": data["customer_segments"]["frequent_customers"],
            "one_time_percentage": data["customer_segments"]["one_time_percentage"],
            "repeat_percentage": data["customer_segments"]["repeat_percentage"],
        },
        "retention_metrics": {
            "total_customers": data["retention_metrics"]["total_customers"],
            "average_orders_per_customer": data["retention_metrics"]["average_orders_per_customer"],
            "average_customer_lifetime_value": format_decimal(data["retention_metrics"]["average_customer_lifetime_value"]),
            "repeat_purchase_rate": data["retention_metrics"]["repeat_purchase_rate"],
        }
    }


# ==================== HOURLY DISTRIBUTION SERIALIZER ====================

def serialize_hourly_distribution(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize hourly order distribution"""
    return [
        {
            "hour": d["hour"],
            "display_hour": d["display_hour"],
            "orders": d["orders"],
            "revenue": format_decimal(d["revenue"]),
        }
        for d in data
    ]


# ==================== DAY OF WEEK DISTRIBUTION SERIALIZER ====================

def serialize_day_of_week_distribution(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize day of week distribution"""
    return [
        {
            "day": d["day"],
            "day_index": d["day_index"],
            "orders": d["orders"],
            "revenue": format_decimal(d["revenue"]),
            "percentage": d["percentage"],
        }
        for d in data
    ]