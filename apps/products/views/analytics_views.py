"""
Product Analytics Views - Comprehensive e-commerce analytics
"""

import logging
import time
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
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
from apps.users.decorators.auth import jwt_required, role_required
from apps.common.logging import log_action, LogSeverity, get_user_info, log_analytics_request
from apps.common.analytics_cache import cached_analytics

logger = logging.getLogger(__name__)

# App name constant for filtering in UI
APP_NAME = "products"


def _log_analytics_request(request, action, start_time, status_code, extra=None):
    """Thin wrapper over the shared apps.common.logging.log_analytics_request,
    kept under this name/signature so the many call sites below don't need to change."""
    log_analytics_request(logger, request, action, start_time, status_code, APP_NAME, extra)


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def product_analytics_overview(request):
    """Get product analytics overview with summary statistics"""
    start_time = time.time()
    action = "analytics_overview"
    user = request.user if hasattr(request, 'user') else None
    
    # Log request start
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving product analytics overview",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            _log_analytics_request(request, action, start_time, 400, extra={"error": error["error"]})
            return APIResponse.bad_request(error["error"])
        
        data = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_overview_stats(start_date=start_date, end_date=end_date),
            start_date=start_date_str, end_date=end_date_str,
        )
        
        serialized_data = serialize_overview_stats(data)
        
        _log_analytics_request(
            request, action, start_time, 200, 
            extra={
                "total_products": data["summary"]["total_products"],
                "total_variants": data["summary"]["total_variants"],
                "active_products": data["summary"]["active_products"],
                "low_stock_variants": data["inventory_summary"]["low_stock_variants"],
                "date_range_start": start_date_str or "all",
                "date_range_end": end_date_str or "all",
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Product analytics overview retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Product analytics overview error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def sales_performance_analytics(request):
    """Get comprehensive sales performance metrics"""
    start_time = time.time()
    action = "analytics_sales_performance"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving sales performance analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        category_id = request.GET.get('category_id')
        brand_id = request.GET.get('brand_id')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            _log_analytics_request(request, action, start_time, 400, extra={"error": error["error"]})
            return APIResponse.bad_request(error["error"])
        
        data = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_sales_performance(
                start_date=start_date,
                end_date=end_date,
                category_id=category_id,
                brand_id=brand_id
            ),
            start_date=start_date_str, end_date=end_date_str, category_id=category_id, brand_id=brand_id,
        )
        
        serialized_data = serialize_sales_performance(data)
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "total_revenue": float(data["sales_summary"]["total_revenue"]),
                "total_orders": data["sales_summary"]["total_orders"],
                "total_quantity_sold": data["sales_summary"]["total_quantity_sold"],
                "average_order_value": float(data["sales_summary"]["average_order_value"]),
                "category_id": category_id,
                "brand_id": brand_id,
                "date_range_start": start_date_str or "all",
                "date_range_end": end_date_str or "all",
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Sales performance analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Sales performance analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def product_funnel_analytics(request):
    """Get product conversion funnel metrics"""
    start_time = time.time()
    action = "analytics_product_funnel"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving product funnel analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            _log_analytics_request(request, action, start_time, 400, extra={"error": error["error"]})
            return APIResponse.bad_request(error["error"])
        
        data = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_product_funnel_analytics(start_date=start_date, end_date=end_date),
            start_date=start_date_str, end_date=end_date_str,
        )
        
        serialized_data = serialize_product_funnel(data)
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "total_products": data["total_products"],
                "products_with_wishlists": data["products_with_wishlists"],
                "products_with_purchases": data["products_with_purchases"],
                "wishlist_to_cart_rate": data["conversion_rates"]["wishlist_to_cart"],
                "cart_to_purchase_rate": data["conversion_rates"]["cart_to_purchase"],
                "overall_conversion_rate": data["conversion_rates"]["overall_conversion"],
                "date_range_start": start_date_str or "all",
                "date_range_end": end_date_str or "all",
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Product funnel analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Product funnel analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='50/h', method='GET', block=True)
def inventory_health_analytics(request):
    """Get inventory health metrics and recommendations"""
    start_time = time.time()
    action = "analytics_inventory_health"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving inventory health analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_inventory_health_metrics(),
        )
        
        serialized_data = serialize_inventory_health(data)
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "total_variants_analyzed": data["summary"]["total_variants_analyzed"],
                "slow_movers_count": data["summary"]["slow_movers_count"],
                "fast_movers_count": data["summary"]["fast_movers_count"],
                "average_turnover_rate": data["summary"]["average_turnover_rate"],
                "reorder_recommendations_count": len(data["reorder_recommendations"]),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Inventory health analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Inventory health analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def pricing_analytics(request):
    """Get pricing analytics and optimization insights"""
    start_time = time.time()
    action = "analytics_pricing"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving pricing analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_pricing_analytics(),
        )
        
        serialized_data = serialize_pricing_analytics(data)
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "total_variants": data["statistics"]["total_variants"],
                "avg_price": data["statistics"]["avg_price"],
                "min_price": data["statistics"]["min_price"],
                "max_price": data["statistics"]["max_price"],
                "discounted_percentage": data["discount_analysis"]["discounted_percentage"],
                "average_discount_percentage": data["discount_analysis"]["average_discount_percentage"],
                "optimal_price_point": data["optimal_price_point"]["price"],
                "estimated_revenue_at_optimal": data["optimal_price_point"]["estimated_revenue"],
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Pricing analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Pricing analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def category_analytics(request):
    """Get detailed category analytics"""
    start_time = time.time()
    action = "analytics_category"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving category analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            _log_analytics_request(request, action, start_time, 400, extra={"error": error["error"]})
            return APIResponse.bad_request(error["error"])
        
        data = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_category_analytics(start_date=start_date, end_date=end_date),
            start_date=start_date_str, end_date=end_date_str,
        )
        
        serialized_data = serialize_category_analytics(data)
        
        total_categories = len(data)
        total_revenue = sum(c["metrics"]["total_revenue"] for c in data) if data else 0
        top_category = data[0]["name"] if data else None
        top_category_revenue = data[0]["metrics"]["total_revenue"] if data else 0
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "total_categories": total_categories,
                "total_revenue": float(total_revenue),
                "top_category": top_category,
                "top_category_revenue": float(top_category_revenue),
                "date_range_start": start_date_str or "all",
                "date_range_end": end_date_str or "all",
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Category analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Category analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def top_products_analytics(request):
    """Get top selling products analytics"""
    start_time = time.time()
    action = "analytics_top_products"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving top products analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        limit_str = request.GET.get('limit', '10')
        category_id = request.GET.get('category_id')
        brand_id = request.GET.get('brand_id')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            _log_analytics_request(request, action, start_time, 400, extra={"error": error["error"]})
            return APIResponse.bad_request(error["error"])
        
        limit, limit_error = validate_limit(limit_str)
        if limit_error:
            _log_analytics_request(request, action, start_time, 400, extra={"error": limit_error["error"]})
            return APIResponse.bad_request(limit_error["error"])
        
        products = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_top_products(
                start_date=start_date,
                end_date=end_date,
                limit=limit,
                category_id=category_id,
                brand_id=brand_id
            ),
            start_date=start_date_str, end_date=end_date_str, limit=limit_str, category_id=category_id, brand_id=brand_id,
        )
        
        serialized_data = serialize_top_products_response(
            products,
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        total_revenue = sum(p["metrics"]["total_revenue"] for p in products) if products else 0
        top_product = products[0]["title"] if products else None
        top_product_revenue = products[0]["metrics"]["total_revenue"] if products else 0
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "limit_requested": limit,
                "products_returned": len(products),
                "total_revenue": float(total_revenue),
                "top_product": top_product,
                "top_product_revenue": float(top_product_revenue),
                "top_product_percentage": products[0]["metrics"]["revenue_percentage"] if products else 0,
                "category_filter": category_id,
                "brand_filter": brand_id,
                "date_range_start": start_date_str or "all",
                "date_range_end": end_date_str or "all",
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Top products analytics retrieved successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid parameter in top products analytics: {str(e)}")
        _log_analytics_request(request, action, start_time, 400, extra={"error": str(e)})
        return APIResponse.bad_request(f"Invalid parameter: {str(e)}")
    except Exception as e:
        logger.error(f"Top products analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def category_performance_analytics(request):
    """Get category performance analytics (legacy)"""
    start_time = time.time()
    action = "analytics_category_performance"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving category performance analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            _log_analytics_request(request, action, start_time, 400, extra={"error": error["error"]})
            return APIResponse.bad_request(error["error"])
        
        categories = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_category_performance(start_date=start_date, end_date=end_date),
            start_date=start_date_str, end_date=end_date_str,
        )
        
        serialized_data = serialize_categories_response(
            categories,
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        total_revenue = sum(c["metrics"]["total_revenue"] for c in categories) if categories else 0
        top_category = categories[0]["name"] if categories else None
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "total_categories": len(categories),
                "total_revenue": float(total_revenue),
                "top_category": top_category,
                "date_range_start": start_date_str or "all",
                "date_range_end": end_date_str or "all",
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Category performance analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Category performance analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def variant_analytics(request):
    """Get detailed variant analytics"""
    start_time = time.time()
    action = "analytics_variant"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving variant analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        start_date_str = request.GET.get('start_date')
        end_date_str = request.GET.get('end_date')
        product_id = request.GET.get('product_id')
        
        start_date, end_date, error = validate_date_range(start_date_str, end_date_str)
        if error:
            _log_analytics_request(request, action, start_time, 400, extra={"error": error["error"]})
            return APIResponse.bad_request(error["error"])
        
        variants = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_variant_analytics(
                product_id=product_id,
                start_date=start_date,
                end_date=end_date
            ),
            product_id=product_id, start_date=start_date_str, end_date=end_date_str,
        )
        
        serialized_data = serialize_variants_response(
            variants,
            start_date=start_date_str,
            end_date=end_date_str
        )
        
        total_revenue = sum(v["metrics"]["revenue"] for v in variants) if variants else 0
        total_quantity = sum(v["metrics"]["quantity_sold"] for v in variants) if variants else 0
        avg_conversion = sum(v["metrics"]["conversion_rate"] for v in variants) / len(variants) if variants else 0
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "variants_returned": len(variants),
                "total_revenue": float(total_revenue),
                "total_quantity_sold": total_quantity,
                "avg_conversion_rate": round(avg_conversion, 2),
                "product_id_filter": product_id,
                "date_range_start": start_date_str or "all",
                "date_range_end": end_date_str or "all",
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Variant analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Variant analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='50/h', method='GET', block=True)
def inventory_status_analytics(request):
    """Get inventory status and alerts analytics"""
    start_time = time.time()
    action = "analytics_inventory_status"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving inventory status analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_inventory_status(),
        )
        
        serialized_data = serialize_inventory_status(data)
        
        critical_alerts = len([a for a in data["low_stock_alerts"] if a.get("severity") == "critical"])
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "total_variants": data["summary"]["total_variants"],
                "total_stock": data["summary"]["total_stock"],
                "total_inventory_value": data["summary"]["total_inventory_value"],
                "avg_stock_per_variant": data["summary"]["avg_stock_per_variant"],
                "in_stock_count": data["stock_status"]["in_stock"],
                "low_stock_count": data["stock_status"]["low_stock"],
                "out_of_stock_count": data["stock_status"]["out_of_stock"],
                "critical_alerts": critical_alerts,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Inventory status analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Inventory status analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def price_distribution_analytics(request):
    """Get price distribution analytics"""
    start_time = time.time()
    action = "analytics_price_distribution"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving price distribution analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_price_distribution(),
        )
        
        serialized_data = serialize_price_distribution(data)
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "total_variants": data["statistics"]["total_variants"],
                "total_products": data["statistics"]["total_products"],
                "min_price": data["statistics"]["min_price"],
                "max_price": data["statistics"]["max_price"],
                "avg_price": data["statistics"]["avg_price"],
                "price_ranges": len(data["ranges"]),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Price distribution analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Price distribution analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def review_analytics(request):
    """Get review and rating analytics"""
    start_time = time.time()
    action = "analytics_reviews"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving review analytics",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = cached_analytics(
            APP_NAME, action,
            lambda: ProductAnalyticsSelector.get_review_analytics(),
        )
        
        serialized_data = serialize_review_analytics(data)
        
        _log_analytics_request(
            request, action, start_time, 200,
            extra={
                "total_reviews": data["summary"]["total_reviews"],
                "average_rating": data["summary"]["average_rating"],
                "verified_purchases": data["summary"]["verified_purchases"],
                "verified_percentage": data["summary"]["verified_percentage"],
                "products_with_reviews": data["summary"]["products_with_reviews"],
                "products_without_reviews": data["summary"]["products_without_reviews"],
                "rating_5_stars": data["rating_distribution"].get("5_stars", 0),
                "rating_4_stars": data["rating_distribution"].get("4_stars", 0),
                "rating_3_stars": data["rating_distribution"].get("3_stars", 0),
                "rating_2_stars": data["rating_distribution"].get("2_stars", 0),
                "rating_1_star": data["rating_distribution"].get("1_star", 0),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_data,
            message="Review analytics retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Review analytics error: {str(e)}", exc_info=True)
        _log_analytics_request(request, action, start_time, 500, extra={"error": str(e), "exception_type": type(e).__name__})
        return APIResponse.server_error()