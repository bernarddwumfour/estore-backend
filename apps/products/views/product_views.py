import json
import logging
import time
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit
from estore.utils.responses import APIResponse
from ..services.product_service import ProductService, ReviewService, AdminProductService
from ..selectors import get_product_by_slug
from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
    role_required,
)
from ..schemas import (
    validate_product_create, validate_product_update,
    validate_review_create
)
from ..models import Product
from apps.common.utils import sanitize_search_query
from apps.common.logging import log_action, LogSeverity, get_user_info

logger = logging.getLogger(__name__)

# App name constant for filtering in UI
APP_NAME = "products"


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, 'user') or not request.user:
        return False
    return getattr(request.user, 'role', 'customer') in ['admin', 'staff']


def _log_product_request(request, action, start_time, status_code, extra=None):
    """Helper to log product requests consistently with app field"""
    duration_ms = (time.time() - start_time) * 1000
    user = request.user if hasattr(request, 'user') else None
    
    log_data = {
        "duration_ms": round(duration_ms, 2),
        "path": request.path,
        "method": request.method,
        "user_role": getattr(user, 'role', 'unknown') if user else 'anonymous',
        "user_id": str(user.id) if user and hasattr(user, 'id') else None,
    }
    if extra:
        log_data.update(extra)
    
    if status_code < 400:
        severity = LogSeverity.INFO
        description = "Product request successful"
    elif status_code == 429:
        severity = LogSeverity.WARNING
        description = "Product request rate limited"
    elif status_code < 500:
        severity = LogSeverity.WARNING
        description = "Product request failed - invalid parameters"
    else:
        severity = LogSeverity.ERROR
        description = "Product request failed with server error"
    
    log_action(
        logger=logger,
        severity=severity,
        action=action,
        description=description,
        status_code=status_code,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra=log_data
    )


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='200/h', method='GET', block=True)
def product_list(request):
    """Public: Get paginated product list with filtering for customers"""
    start_time = time.time()
    action = "product_list"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - retrieving product list",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        category_slug = request.GET.get("category")
        brand = request.GET.get("brand")
        search = sanitize_search_query(request.GET.get("search", ""))
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
        # Price range
        min_price = request.GET.get("min_price")
        max_price = request.GET.get("max_price")
        
        # Boolean filters
        in_stock = request.GET.get("in_stock")
        featured = request.GET.get("featured")
        bestseller = request.GET.get("bestseller")
        new = request.GET.get("new")
        
        # Convert string parameters
        if min_price:
            min_price = float(min_price)
        if max_price:
            max_price = float(max_price)
        if in_stock:
            in_stock = in_stock.lower() == "true"
        if featured:
            featured = featured.lower() == "true"
        if bestseller:
            bestseller = bestseller.lower() == "true"
        if new:
            new = new.lower() == "true"
        
        # Validate limit
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        
        is_admin = _is_admin(request)
        
        # Get products from service
        products, total, pagination_meta = ProductService.get_public_products(
            page=page,
            limit=limit,
            category_slug=category_slug,
            brand=brand,
            min_price=min_price,
            max_price=max_price,
            in_stock=in_stock,
            featured=featured,
            bestseller=bestseller,
            new=new,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            is_admin=is_admin,
        )
        
        _log_product_request(
            request, action, start_time, 200,
            extra={
                "total_products": total,
                "products_returned": len(products),
                "page": page,
                "limit": limit,
                "category_slug": category_slug,
                "brand": brand,
                "has_search": bool(search),
                "has_price_filter": bool(min_price or max_price),
                "in_stock_filter": in_stock,
                "featured_filter": featured,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "products": products,
                "total": total,
                "pagination": pagination_meta
            },
            message="Products retrieved successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        _log_product_request(request, action, start_time, 400, extra={"error": str(e)})
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product list error: {str(e)}", exc_info=True)
        _log_product_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='100/h', method='GET', block=True)
def product_search(request):
    """Public: Search products"""
    start_time = time.time()
    action = "product_search"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - product search",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        query = request.GET.get("q", "").strip()
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        
        if not query or len(query) < 2:
            _log_product_request(
                request, action, start_time, 400,
                extra={"error": "Search query too short", "query_length": len(query)}
            )
            return APIResponse.bad_request("Search query must be at least 2 characters")
        
        # Cap query length
        query = query[:200]
        
        # Validate limit
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        
        is_admin = _is_admin(request)
        
        products, total, pagination_meta = ProductService.get_public_products(
            page=page,
            limit=limit,
            search=query,
            is_admin=is_admin,
        )
        
        _log_product_request(
            request, action, start_time, 200,
            extra={
                "search_query": query,
                "total_results": total,
                "products_returned": len(products),
                "page": page,
                "limit": limit,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "products": products,
                "total": total,
                "pagination": pagination_meta,
                "query": query
            },
            message=f"Search results for '{query}'"
        )
        
    except ValueError as e:
        logger.error(f"Product search error: {str(e)}")
        _log_product_request(request, action, start_time, 400, extra={"error": str(e)})
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product search error: {str(e)}", exc_info=True)
        _log_product_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='200/h', method='GET', block=True)
def product_detail(request, slug):
    """Get detailed product information"""
    start_time = time.time()
    action = "product_detail"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - retrieving product detail for slug: {slug}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "slug": slug}
    )
    
    try:
        is_admin = _is_admin(request)
        product_data = ProductService.get_product_detail(slug, is_admin=is_admin)
        
        if not product_data:
            _log_product_request(
                request, action, start_time, 404,
                extra={"slug": slug, "reason": "Product not found"}
            )
            return APIResponse.not_found("Product not found")
        
        _log_product_request(
            request, action, start_time, 200,
            extra={
                "product_id": product_data.get("id"),
                "product_title": product_data.get("title"),
                "slug": slug,
                "has_variants": bool(product_data.get("variants")),
                "variants_count": len(product_data.get("variants", [])),
                "has_related": bool(product_data.get("related_products")),
                "is_admin_access": is_admin,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(product_data)
        
    except Exception as e:
        logger.error(f"Product detail error: {str(e)}", exc_info=True)
        _log_product_request(request, action, start_time, 500, extra={"slug": slug, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
@ratelimit(key='user', rate='10/h', method='POST', block=True)
def create_review(request, slug):
    """Create product review"""
    start_time = time.time()
    action = "create_review"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - creating review for product: {slug}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "slug": slug}
    )
    
    try:
        data = request.json_data
        
        # Validate input using schema
        cleaned, errors = validate_review_create(data)
        if errors:
            _log_product_request(
                request, action, start_time, 400,
                extra={"slug": slug, "errors": errors}
            )
            return APIResponse.validation_error(errors)
        
        # Create review
        review, error = ReviewService.create_review(
            user=user,
            product_slug=slug,
            **cleaned
        )
        
        if error:
            if "already" in str(error).get("review", "").lower():
                _log_product_request(
                    request, action, start_time, 409,
                    extra={"slug": slug, "reason": "Duplicate review"}
                )
                return APIResponse.conflict(error["review"])
            
            _log_product_request(
                request, action, start_time, 400,
                extra={"slug": slug, "error": error}
            )
            return APIResponse.validation_error(error)
        
        _log_product_request(
            request, action, start_time, 201,
            extra={
                "review_id": str(review.id),
                "product_slug": slug,
                "rating": cleaned.get("rating"),
                "has_title": bool(cleaned.get("title")),
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.created(
            data={"review_id": str(review.id)},
            message="Review submitted successfully"
        )
        
    except Exception as e:
        logger.error(f"Create review error: {str(e)}", exc_info=True)
        _log_product_request(request, action, start_time, 500, extra={"slug": slug, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='200/h', method='GET', block=True)
def product_reviews(request, slug):
    """Get product reviews"""
    start_time = time.time()
    action = "product_reviews"
    user = request.user if hasattr(request, 'user') else None
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - retrieving reviews for product: {slug}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "slug": slug}
    )
    
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        rating = request.GET.get("rating")
        verified = request.GET.get("verified")
        
        if rating:
            rating = int(rating)
            if rating < 1 or rating > 5:
                _log_product_request(
                    request, action, start_time, 400,
                    extra={"slug": slug, "error": "Invalid rating", "rating": rating}
                )
                return APIResponse.bad_request("Rating must be between 1 and 5")
        
        if verified:
            verified = verified.lower() == "true"
        
        if limit > 50:
            limit = 50
        if limit < 1:
            limit = 20
        
        is_admin = _is_admin(request)
        
        reviews, total = ReviewService.get_product_reviews(
            product_slug=slug,
            page=page,
            limit=limit,
            rating=rating,
            verified=verified,
            is_admin=is_admin,
        )
        
        # Get rating stats
        product = get_product_by_slug(slug, include_inactive=is_admin)
        stats = None
        if product:
            from ..selectors import get_product_rating_stats
            stats = get_product_rating_stats(product.id)
        
        _log_product_request(
            request, action, start_time, 200,
            extra={
                "product_slug": slug,
                "total_reviews": total,
                "reviews_returned": len(reviews),
                "page": page,
                "limit": limit,
                "rating_filter": rating,
                "verified_filter": verified,
                "is_admin_access": is_admin,
                "avg_rating": stats.get("average") if stats else None,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "items": reviews,
                "total": total,
                "page": page,
                "limit": limit,
                "stats": stats
            },
            message=f"Reviews for {slug}"
        )
        
    except ValueError as e:
        logger.error(f"Product reviews error: {str(e)}")
        _log_product_request(request, action, start_time, 400, extra={"slug": slug, "error": str(e)})
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product reviews error: {str(e)}", exc_info=True)
        _log_product_request(request, action, start_time, 500, extra={"slug": slug, "error": str(e)})
        return APIResponse.server_error()


# ==================== ADMIN VIEWS ====================

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
def admin_product_list(request):
    """Admin: List all products with filters, search, sorting, and pagination"""
    start_time = time.time()
    action = "admin_product_list"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - admin retrieving product list",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        status = request.GET.get("status")
        search = sanitize_search_query(request.GET.get("search", ""))
        category_id = request.GET.get("category_id")
        is_featured = request.GET.get("is_featured")
        is_bestseller = request.GET.get("is_bestseller")
        is_new = request.GET.get("is_new")
        has_stock = request.GET.get("has_stock")
        min_price = request.GET.get("min_price")
        max_price = request.GET.get("max_price")
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
        # Convert string parameters
        if min_price:
            min_price = float(min_price)
        if max_price:
            max_price = float(max_price)
        if is_featured:
            is_featured = is_featured.lower() == "true"
        if is_bestseller:
            is_bestseller = is_bestseller.lower() == "true"
        if is_new:
            is_new = is_new.lower() == "true"
        if has_stock:
            has_stock = has_stock.lower() == "true"
        
        # Validate limit
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        
        # Get products with filters
        products, total, pagination_meta = ProductService.get_admin_products(
            page=page,
            limit=limit,
            search=search,
            status=status,
            category_id=category_id,
            is_featured=is_featured,
            is_bestseller=is_bestseller,
            is_new=is_new,
            has_stock=has_stock,
            min_price=min_price,
            max_price=max_price,
            sort_by=sort_by,
            sort_order=sort_order,
        )
        
        _log_product_request(
            request, action, start_time, 200,
            extra={
                "total_products": total,
                "products_returned": len(products),
                "page": page,
                "limit": limit,
                "status_filter": status,
                "category_filter": category_id,
                "has_search": bool(search),
                "has_price_filter": bool(min_price or max_price),
                "featured_filter": is_featured,
                "bestseller_filter": is_bestseller,
                "new_filter": is_new,
                "has_stock_filter": has_stock,
                "sort_by": sort_by,
                "sort_order": sort_order,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data={
                "products": products,
                "total": total,
                "pagination": pagination_meta
            },
            message="Products retrieved successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        _log_product_request(request, action, start_time, 400, extra={"error": str(e)})
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Admin product list error: {str(e)}", exc_info=True)
        _log_product_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='50/h', method='POST', block=True)
def admin_product_create(request):
    """Admin: Create new product"""
    start_time = time.time()
    action = "admin_product_create"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - admin creating new product",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        data = request.json_data
        
        # Validate input with admin privileges
        cleaned, errors = validate_product_create(data, is_admin=True)
        if errors:
            _log_product_request(
                request, action, start_time, 400,
                extra={"errors": errors}
            )
            return APIResponse.validation_error(errors)
        
        product, errors = AdminProductService.create_product(cleaned, request.user)
        
        if errors:
            _log_product_request(
                request, action, start_time, 400,
                extra={"errors": errors, "product_title": cleaned.get("title")}
            )
            return APIResponse.validation_error(errors)
        
        _log_product_request(
            request, action, start_time, 201,
            extra={
                "product_id": str(product.id),
                "product_title": product.title,
                "slug": product.slug,
                "status": product.status,
                "category_id": str(product.category_id) if product.category_id else None,
                "is_featured": product.is_featured,
                "is_bestseller": product.is_bestseller,
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.created(
            data={"product_id": str(product.id), "slug": product.slug},
            message="Product created successfully"
        )
        
    except json.JSONDecodeError:
        _log_product_request(request, action, start_time, 400, extra={"error": "Invalid JSON data"})
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin product create error: {str(e)}", exc_info=True)
        _log_product_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='100/h', method='GET', block=True)
@ratelimit(key='user', rate='50/h', method='PUT', block=True)
@ratelimit(key='user', rate='20/h', method='DELETE', block=True)
def admin_product_detail(request, product_id):
    """Admin: Get, update, or delete product"""
    start_time = time.time()
    action = f"admin_product_{request.method.lower()}"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description=f"Request started - admin product operation for ID: {product_id}",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time, "product_id": product_id, "method": request.method}
    )
    
    try:
        if request.method == "GET":
            from ..selectors import get_product_by_id
            product = get_product_by_id(product_id, include_inactive=True)
            
            if not product:
                _log_product_request(
                    request, action, start_time, 404,
                    extra={"product_id": product_id, "reason": "Product not found"}
                )
                return APIResponse.not_found("Product not found")
            
            from ..schemas import serialize_product
            product_data = serialize_product(product, is_admin=True)
            
            _log_product_request(
                request, action, start_time, 200,
                extra={
                    "product_id": str(product.id),
                    "product_title": product.title,
                    "slug": product.slug,
                    "status": product.status,
                    "variants_count": product.variants.count(),
                    "has_category": bool(product.category),
                    "requested_by": get_user_info(user)
                }
            )
            
            return APIResponse.success(product_data)
        
        elif request.method == "PUT" or request.method == "PATCH":
            data = json.loads(request.body)
            
            # Validate input with admin privileges
            cleaned, errors = validate_product_update(data, is_admin=True)
            if errors:
                _log_product_request(
                    request, action, start_time, 400,
                    extra={"product_id": product_id, "errors": errors}
                )
                return APIResponse.validation_error(errors)
            
            product, errors = AdminProductService.update_product(product_id, cleaned, request.user)
            
            if errors:
                _log_product_request(
                    request, action, start_time, 400,
                    extra={"product_id": product_id, "errors": errors}
                )
                return APIResponse.validation_error(errors)
            
            _log_product_request(
                request, action, start_time, 200,
                extra={
                    "product_id": str(product.id),
                    "product_title": product.title,
                    "updated_fields": list(cleaned.keys()),
                    "requested_by": get_user_info(user)
                }
            )
            
            return APIResponse.success(
                data={"product_id": str(product.id), "slug": product.slug},
                message="Product updated successfully"
            )
        
        elif request.method == "DELETE":
            product, errors = AdminProductService.update_product(
                product_id, {"status": Product.STATUS_ARCHIVED}, request.user
            )
            
            if errors:
                _log_product_request(
                    request, action, start_time, 404,
                    extra={"product_id": product_id, "reason": "Product not found"}
                )
                return APIResponse.not_found("Product not found")
            
            _log_product_request(
                request, action, start_time, 200,
                extra={
                    "product_id": product_id,
                    "product_title": product.title if product else None,
                    "action": "archived",
                    "requested_by": get_user_info(user)
                }
            )
            
            return APIResponse.success(message="Product archived successfully")
            
    except json.JSONDecodeError:
        _log_product_request(request, action, start_time, 400, extra={"error": "Invalid JSON data"})
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin product detail error: {str(e)}", exc_info=True)
        _log_product_request(request, action, start_time, 500, extra={"product_id": product_id, "error": str(e)})
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key='user', rate='30/h', method='POST', block=True)
def admin_product_bulk_action(request):
    """Admin: Perform bulk actions on products"""
    start_time = time.time()
    action = "admin_product_bulk_action"
    user = request.user
    
    log_action(
        logger=logger,
        severity=LogSeverity.DEBUG,
        action=action,
        description="Request started - admin bulk action on products",
        status_code=0,
        user=user,
        request=request,
        app_name=APP_NAME,
        extra={"start_time": start_time}
    )
    
    try:
        from apps.products.schemas import validate_product_bulk_action, serialize_product_bulk_action_result
        
        # Validate request data
        cleaned, errors = validate_product_bulk_action(request.json_data)
        if errors:
            _log_product_request(
                request, action, start_time, 400,
                extra={"errors": errors}
            )
            return APIResponse.validation_error(errors)
        
        # Execute bulk action
        results, error = ProductService.bulk_action_products(
            product_ids=cleaned['product_ids'],
            action=cleaned['action'],
            user=request.user
        )
        
        if error:
            _log_product_request(
                request, action, start_time, 400,
                extra={"error": error, "action": cleaned['action']}
            )
            return APIResponse.validation_error(error)
        
        # Serialize and return response
        serialized_results = serialize_product_bulk_action_result(results)
        
        if serialized_results['failed_count'] == 0:
            message = f"Successfully {cleaned['action']}ed {serialized_results['success_count']} products"
        else:
            message = f"Processed {serialized_results['success_count']} successfully, {serialized_results['failed_count']} failed"
        
        _log_product_request(
            request, action, start_time, 200,
            extra={
                "action": cleaned['action'],
                "total_products": len(cleaned['product_ids']),
                "success_count": serialized_results['success_count'],
                "failed_count": serialized_results['failed_count'],
                "requested_by": get_user_info(user)
            }
        )
        
        return APIResponse.success(
            data=serialized_results,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Admin product bulk action error: {str(e)}", exc_info=True)
        _log_product_request(request, action, start_time, 500, extra={"error": str(e)})
        return APIResponse.server_error()


# Alias for backward compatibility
admin_product_update = admin_product_detail