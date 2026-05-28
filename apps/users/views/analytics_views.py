"""
User Analytics Views - API views for user analytics endpoints
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse
from apps.users.selectors.analytics_selectors import UserAnalyticsSelector
from apps.users.schemas.analytics_schemas import (
    validate_date_range,
    validate_interval,
    validate_limit,
    serialize_user_overview_stats,
    serialize_user_growth_trends,
    serialize_user_engagement_analytics,
    serialize_geographic_distribution,
    serialize_user_activity_analytics,
    serialize_affiliate_analytics,
    serialize_affiliate_growth_trends,
    serialize_customer_demographics,
    serialize_top_customers,
)

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
def user_analytics_overview(request):
    """Get user analytics overview"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = UserAnalyticsSelector.get_user_overview_stats(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_user_overview_stats(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="User analytics overview retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"User analytics overview error: {str(e)}")
        import traceback
        traceback.print_exc()
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def user_growth_trends(request):
    """Get user growth trends over time"""
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
        
        data = UserAnalyticsSelector.get_user_growth_trends(
            start_date=start_date,
            end_date=end_date,
            interval=interval
        )
        
        serialized_data = serialize_user_growth_trends(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="User growth trends retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"User growth trends error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def user_engagement_analytics(request):
    """Get user engagement analytics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = UserAnalyticsSelector.get_user_engagement_analytics(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_user_engagement_analytics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="User engagement analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"User engagement analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def user_geographic_distribution(request):
    """Get user geographic distribution"""
    try:
        data = UserAnalyticsSelector.get_user_geographic_distribution()
        
        serialized_data = serialize_geographic_distribution(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="User geographic distribution retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"User geographic distribution error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def user_activity_analytics(request):
    """Get user activity analytics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = UserAnalyticsSelector.get_user_activity_analytics(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_user_activity_analytics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="User activity analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"User activity analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def affiliate_analytics(request):
    """Get affiliate performance analytics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = UserAnalyticsSelector.get_affiliate_analytics(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_affiliate_analytics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Affiliate analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Affiliate analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def affiliate_growth_trends(request):
    """Get affiliate growth trends"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        interval_str = request.GET.get('interval', 'month')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        interval, interval_error = validate_interval(interval_str)
        if interval_error:
            return APIResponse.bad_request(interval_error["error"])
        
        data = UserAnalyticsSelector.get_affiliate_growth_trends(
            start_date=start_date,
            end_date=end_date,
            interval=interval
        )
        
        serialized_data = serialize_affiliate_growth_trends(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Affiliate growth trends retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Affiliate growth trends error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def customer_demographics(request):
    """Get customer demographic analytics"""
    try:
        data = UserAnalyticsSelector.get_customer_demographics()
        
        serialized_data = serialize_customer_demographics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Customer demographics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Customer demographics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def top_customers_analytics(request):
    """Get top customers by spending"""
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
        
        data = UserAnalyticsSelector.get_top_customers_by_spending(
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
        logger.error(f"Top customers analytics error: {str(e)}")
        return APIResponse.server_error()