"""
Order Analytics Views - API views for order analytics endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse

from apps.orders.selectors.analytics_selectors import OrderAnalyticsSelector
from apps.orders.schemas.analytics_schemas import (
    validate_date_range,
    validate_interval,
    validate_limit,
    serialize_order_summary_stats,
    serialize_sales_trends,
    serialize_status_distribution,
    serialize_payment_status_distribution,
    serialize_top_customers,
    serialize_fulfillment_analytics,
    serialize_refund_analytics,
    serialize_customer_retention_analytics,
    serialize_hourly_distribution,
    serialize_day_of_week_distribution,
)

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
def order_analytics_summary(request):
    """Get order analytics summary"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = OrderAnalyticsSelector.get_order_summary_stats(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_order_summary_stats(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Order analytics summary retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Order analytics summary error: {str(e)}")
        import traceback
        traceback.print_exc()
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def sales_trends_analytics(request):
    """Get sales trends over time"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        interval_str = request.GET.get('interval', 'day')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        interval, interval_error = validate_interval(interval_str)
        if interval_error:
            return APIResponse.bad_request(interval_error["error"])
        
        data = OrderAnalyticsSelector.get_sales_trends(
            start_date=start_date,
            end_date=end_date,
            interval=interval
        )
        
        serialized_data = serialize_sales_trends(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Sales trends retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Sales trends error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def order_status_distribution_analytics(request):
    """Get order status distribution"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = OrderAnalyticsSelector.get_order_status_distribution(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_status_distribution(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Order status distribution retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Order status distribution error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def payment_status_distribution_analytics(request):
    """Get payment status distribution"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = OrderAnalyticsSelector.get_payment_status_distribution(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_payment_status_distribution(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Payment status distribution retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Payment status distribution error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def top_customers_analytics(request):
    """Get top customers by total spent"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        limit_str = request.GET.get('limit', '10')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        limit, limit_error = validate_limit(limit_str)
        if limit_error:
            return APIResponse.bad_request(limit_error["error"])
        
        data = OrderAnalyticsSelector.get_top_customers(
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )
        
        serialized_data = serialize_top_customers(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Top customers retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Top customers error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def fulfillment_analytics(request):
    """Get fulfillment and shipping analytics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = OrderAnalyticsSelector.get_fulfillment_analytics(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_fulfillment_analytics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Fulfillment analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Fulfillment analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def refund_analytics(request):
    """Get refund analytics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = OrderAnalyticsSelector.get_refund_analytics(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_refund_analytics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Refund analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Refund analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def customer_retention_analytics(request):
    """Get customer retention analytics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = OrderAnalyticsSelector.get_customer_retention_analytics(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_customer_retention_analytics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Customer retention analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Customer retention analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def hourly_order_distribution_analytics(request):
    """Get distribution of orders by hour of day"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = OrderAnalyticsSelector.get_hourly_order_distribution(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_hourly_distribution(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Hourly order distribution retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Hourly order distribution error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def day_of_week_distribution_analytics(request):
    """Get distribution of orders by day of week"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = OrderAnalyticsSelector.get_day_of_week_distribution(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_day_of_week_distribution(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Day of week distribution retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Day of week distribution error: {str(e)}")
        return APIResponse.server_error()