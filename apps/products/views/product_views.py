
import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from estore.utils.responses import APIResponse  # Your existing response class
from ..services.product_service import ProductService, ReviewService, WishlistService, AdminProductService,CategoryService
from ..selectors import ( get_product_by_slug)
from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
    multipart_request_allowed,
    role_required,
)
from ..schemas import (
    validate_product_create, validate_product_update,
 validate_review_create
)
from ..models import Product
import traceback


logger = logging.getLogger(__name__)
def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, 'user') or not request.user:
        return False
    return getattr(request.user, 'role', 'customer') in ['admin', 'staff']



@csrf_exempt
@require_http_methods(["GET"])
def product_list(request):
    """Public: Get paginated product list with filtering for customers"""
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        category_slug = request.GET.get("category")
        brand = request.GET.get("brand")
        search = request.GET.get("search", "").strip()
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
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def product_search(request):
    """Public: Search products"""
    try:
        query = request.GET.get("q", "").strip()
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        
        if not query or len(query) < 2:
            return APIResponse.bad_request("Search query must be at least 2 characters")
        
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
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product search error: {str(e)}")
        return APIResponse.server_error()
    

@csrf_exempt
@require_http_methods(["GET"])
def product_detail(request, slug):
    """Get detailed product information"""
    try:
        is_admin = _is_admin(request)
        product_data = ProductService.get_product_detail(slug, is_admin=is_admin)
        
        if not product_data:
            return APIResponse.not_found("Product not found")
        
        return APIResponse.success(product_data)
        
    except Exception as e:
        logger.error(f"Product detail error: {str(e)}")
        return APIResponse.server_error()


    

@csrf_exempt
@require_http_methods(["GET"])
def product_reviews(request, slug):
    """Get product reviews"""
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        rating = request.GET.get("rating")
        verified = request.GET.get("verified")
        
        if rating:
            rating = int(rating)
            if rating < 1 or rating > 5:
                return APIResponse.bad_request("Rating must be between 1 and 5")
        
        if verified:
            verified = verified.lower() == "true"
        
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
        logger.error(f"Product search error: {str(e)}")
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product reviews error: {str(e)}")
        return APIResponse.server_error()



@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
def create_review(request, slug):
    """Create product review"""
    try:
        user = request.user
        data = request.json_data
        
        # Validate input using schema
        cleaned, errors = validate_review_create(data)
        if errors:
            return APIResponse.validation_error(errors)
        
        # Create review
        review, error = ReviewService.create_review(
            user=user,
            product_slug=slug,
            **cleaned
        )
        
        if error:
            if "already" in str(error).get("review", "").lower():
                return APIResponse.conflict(error["review"])
            return APIResponse.validation_error(error)
        
        return APIResponse.created(
            data={"review_id": str(review.id)},
            message="Review submitted successfully"
        )
        
    except Exception as e:
        logger.error(f"Create review error: {str(e)}")
        return APIResponse.server_error()


# ==================== ADMIN VIEWS ====================

# apps/products/views.py - Updated admin_product_list

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_product_list(request):
    """Admin: List all products with filters, search, sorting, and pagination"""
    try:
        # Get query parameters
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        status = request.GET.get("status")
        search = request.GET.get("search", "").strip()
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
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Admin product list error: {str(e)}")
        traceback.print_exc()
        return APIResponse.server_error()

    
    
@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_product_create(request):
    """Admin: Create new product"""
    try:
        data = request.json_data
        
        # Validate input with admin privileges
        cleaned, errors = validate_product_create(data, is_admin=True)
        if errors:
            return APIResponse.validation_error(errors)
        
        product, errors = AdminProductService.create_product(cleaned, request.user)
        
        if errors:
            return APIResponse.validation_error(errors)
        
        return APIResponse.created(
            data={"product_id": str(product.id), "slug": product.slug},
            message="Product created successfully"
        )
        
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin product create error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "PUT", "DELETE"])
@jwt_required
@role_required("admin", "staff")
def admin_product_detail(request, product_id):
    """Admin: Get, update, or delete product"""
    try:
        if request.method == "GET":
            from ..selectors import get_product_by_id
            product = get_product_by_id(product_id, include_inactive=True)
            
            if not product:
                return APIResponse.not_found("Product not found")
            
            from ..schemas import serialize_product
            product_data = serialize_product(product, is_admin=True)
            
            return APIResponse.success(product_data)
        
        elif request.method == "PUT" or request.method == "PATCH":
            data = json.loads(request.body)
            
            # Validate input with admin privileges
            cleaned, errors = validate_product_update(data, is_admin=True)
            if errors:
                return APIResponse.validation_error(errors)
            
            product, errors = AdminProductService.update_product(product_id, cleaned, request.user)
            
            if errors:
                return APIResponse.validation_error(errors)
            
            return APIResponse.success(
                data={"product_id": str(product.id), "slug": product.slug},
                message="Product updated successfully"
            )
        
        elif request.method == "DELETE":
            product, errors = AdminProductService.update_product(
                product_id, {"status": Product.STATUS_ARCHIVED}, request.user
            )
            
            if errors:
                return APIResponse.not_found("Product not found")
            
            return APIResponse.success(message="Product archived successfully")
            
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin product detail error: {str(e)}")
        return APIResponse.server_error()

@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_product_bulk_action(request):
    """Admin: Perform bulk actions on products"""
    try:
        from apps.products.schemas import validate_product_bulk_action, serialize_product_bulk_action_result
        
        # Validate request data
        cleaned, errors = validate_product_bulk_action(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)
        
        # Execute bulk action
        results, error = ProductService.bulk_action_products(
            product_ids=cleaned['product_ids'],
            action=cleaned['action'],
            user=request.user
        )
        
        
        if error:
            return APIResponse.validation_error(error)
        
        # Serialize and return response
        serialized_results = serialize_product_bulk_action_result(results)
        
        if serialized_results['failed_count'] == 0:
            message = f"Successfully {cleaned['action']}ed {serialized_results['success_count']} products"
        else:
            message = f"Processed {serialized_results['success_count']} successfully, {serialized_results['failed_count']} failed"
        print("hereeee")
        
        return APIResponse.success(
            data=serialized_results,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Admin product bulk action error: {str(e)}")
        return APIResponse.server_error()
    
    


@csrf_exempt
@require_http_methods(["GET"])
def product_reviews(request, slug):
    """Get product reviews"""
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        rating = request.GET.get("rating")
        verified = request.GET.get("verified")
        
        if rating:
            rating = int(rating)
            if rating < 1 or rating > 5:
                return APIResponse.bad_request("Rating must be between 1 and 5")
        
        if verified:
            verified = verified.lower() == "true"
        
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
        logger.error(f"Product search error: {str(e)}")
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product reviews error: {str(e)}")
        return APIResponse.server_error()


# @csrf_exempt
# @require_http_methods(["GET"])
# @jwt_required
# @role_required("admin", "staff")
# def product_analytics(request):
#     """
#     Get product analytics with caching and optimized queries
#     Query params:
#     - chart_type: specific chart to fetch (optional, reduces response size)
#     - refresh: force refresh cache (optional)
#     """
#     try:
#         chart_type = request.GET.get('chart_type')
#         refresh = request.GET.get('refresh', '').lower() == 'true'
        
#         # Clear cache if refresh requested
#         if refresh:
#             cache_key = f"analytics:products:dashboard:{chart_type or 'all'}"
#             cache.delete(cache_key)
        
#         # Get analytics data
#         if chart_type and chart_type != 'all':
#             # Fetch only specific chart
#             chart_data = product_analytics_service.get_chart_data(request, chart_type)
#             return APIResponse.success(
#                 data={"charts": {chart_type: chart_data.get(chart_type)}},
#                 message=f"Product {chart_type} chart data retrieved"
#             )
#         else:
#             # Fetch complete dashboard
#             dashboard_data = product_analytics_service.get_dashboard_data(request)
#             return APIResponse.success(
#                 data=dashboard_data,
#                 message="Product analytics retrieved successfully"
#             )
        
#     except Exception as e:
#         logger.error(f"Product analytics error: {str(e)}")
#         return APIResponse.server_error()
# apps/products/views.py - Update category views

    
admin_product_update = admin_product_detail  