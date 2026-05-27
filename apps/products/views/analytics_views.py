"""
Product Analytics Views - Comprehensive e-commerce analytics
"""

import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse 
from apps.products.selectors.analytics_selectors import ProductAnalyticsSelector
from apps.products.schemas.analytics_schemas import (
    validate_date_range,
    validate_limit,
    serialize_overview_stats,
    serialize_sales_performance,
    serialize_product_funnel,
    serialize_inventory_health,
    serialize_pricing_analytics,
    serialize_category_analytics,
    serialize_top_products_response,
    serialize_variants_response,
    serialize_inventory_status,
    serialize_price_distribution,
    serialize_review_analytics,
    serialize_categories_response,
)

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["GET"])
def product_analytics_overview(request):
    """Get product analytics overview with summary statistics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = ProductAnalyticsSelector.get_overview_stats(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_overview_stats(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Product analytics overview retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Product analytics overview error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def sales_performance_analytics(request):
    """Get comprehensive sales performance metrics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        category_id = request.GET.get('category_id')
        brand_id = request.GET.get('brand_id')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = ProductAnalyticsSelector.get_sales_performance(
            start_date=start_date,
            end_date=end_date,
            category_id=category_id,
            brand_id=brand_id
        )
        
        serialized_data = serialize_sales_performance(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Sales performance analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Sales performance analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def product_funnel_analytics(request):
    """Get product conversion funnel metrics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = ProductAnalyticsSelector.get_product_funnel_analytics(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_product_funnel(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Product funnel analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Product funnel analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def inventory_health_analytics(request):
    """Get inventory health metrics and recommendations"""
    try:
        data = ProductAnalyticsSelector.get_inventory_health_metrics()
        
        serialized_data = serialize_inventory_health(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Inventory health analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Inventory health analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def pricing_analytics(request):
    """Get pricing analytics and optimization insights"""
    try:
        data = ProductAnalyticsSelector.get_pricing_analytics()
        
        serialized_data = serialize_pricing_analytics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Pricing analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Pricing analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def category_analytics(request):
    """Get detailed category analytics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        data = ProductAnalyticsSelector.get_category_analytics(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_category_analytics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Category analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Category analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def top_products_analytics(request):
    """Get top selling products analytics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        limit_str = request.GET.get('limit', '10')
        category_id = request.GET.get('category_id')
        brand_id = request.GET.get('brand_id')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        limit, limit_error = validate_limit(limit_str)
        if limit_error:
            return APIResponse.bad_request(limit_error["error"])
        
        products = ProductAnalyticsSelector.get_top_products(
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            category_id=category_id,
            brand_id=brand_id
        )
        
        serialized_data = serialize_top_products_response(
            products,
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Top products analytics retrieved successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid parameter in top products analytics: {str(e)}")
        return APIResponse.bad_request(f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Top products analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def category_performance_analytics(request):
    """Get category performance analytics (legacy)"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        categories = ProductAnalyticsSelector.get_category_performance(
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_categories_response(
            categories,
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Category performance analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Category performance analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def variant_analytics(request):
    """Get detailed variant analytics"""
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        product_id = request.GET.get('product_id')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            return APIResponse.bad_request(error["error"])
        
        variants = ProductAnalyticsSelector.get_variant_analytics(
            product_id=product_id,
            start_date=start_date,
            end_date=end_date
        )
        
        serialized_data = serialize_variants_response(
            variants,
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Variant analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Variant analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def inventory_status_analytics(request):
    """Get inventory status and alerts analytics"""
    try:
        data = ProductAnalyticsSelector.get_inventory_status()
        
        serialized_data = serialize_inventory_status(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Inventory status analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Inventory status analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def price_distribution_analytics(request):
    """Get price distribution analytics"""
    try:
        data = ProductAnalyticsSelector.get_price_distribution()
        
        serialized_data = serialize_price_distribution(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Price distribution analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Price distribution analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def review_analytics(request):
    """Get review and rating analytics"""
    try:
        data = ProductAnalyticsSelector.get_review_analytics()
        
        serialized_data = serialize_review_analytics(data)
        
        return APIResponse.success(
            data=serialized_data,
            message="Review analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Review analytics error: {str(e)}")
        return APIResponse.server_error()