"""
Product views using shared APIResponse from estore.utils
Refactored to use selectors, schemas, and updated services
"""

import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .services.product_service import product_analytics_service
from django.core.cache import cache


# Your existing decorators
from users.decorators.auth import (
    json_request_required,
    jwt_required,
    multipart_request_allowed,
    role_required,
)
from estore.utils.responses import APIResponse  # Your existing response class

# New imports
from .selectors import ( get_product_by_slug)
from .schemas import (
    validate_product_create, validate_product_update,
    validate_variant_create, validate_review_create
)
from .services.product_service import ProductService, ReviewService, WishlistService, AdminProductService,CategoryService
from .models import Product

logger = logging.getLogger(__name__)


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, 'user') or not request.user:
        return False
    return getattr(request.user, 'role', 'customer') in ['admin', 'staff']


# ==================== PUBLIC PRODUCT VIEWS ====================

@csrf_exempt
@require_http_methods(["GET"])
def product_list(request):
    """Get paginated product list with filtering"""
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        category_slug = request.GET.get("category")
        brand = request.GET.get("brand")
        min_price = request.GET.get("min_price")
        max_price = request.GET.get("max_price")
        in_stock = request.GET.get("in_stock")
        featured = request.GET.get("featured")
        bestseller = request.GET.get("bestseller")
        new = request.GET.get("new")
        search = request.GET.get("search", "").strip()
        sort_by = request.GET.get("sort_by", "created_at")
        sort_order = request.GET.get("sort_order", "desc")
        
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
        
        is_admin = _is_admin(request)
        
        # Get products from service (now using selectors + schemas)
        products, total_count, filters = ProductService.get_products(
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
                "items": products,
                "total": total_count,
                "page": page,
                "limit": limit,
                "filters": filters
            },
            message="Products listed successfully"
        )
        
    except ValueError as e:
        logger.error(f"Invalid query parameter: {str(e)}")
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product list error: {str(e)}")
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
def variant_detail(request, variant_id):
    """Get detailed variant information"""
    try:
        is_admin = _is_admin(request)
        variant_data = ProductService.get_variant_detail(variant_id, is_admin=is_admin)
        
        if not variant_data:
            return APIResponse.not_found("Variant not found")
        
        return APIResponse.success(variant_data)
        
    except Exception as e:
        logger.error(f"Variant detail error: {str(e)}")
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
            from .selectors import get_product_rating_stats
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
@require_http_methods(["GET"])
def product_search(request):
    """Search products"""
    try:
        query = request.GET.get("q", "").strip()
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        
        if not query or len(query) < 2:
            return APIResponse.bad_request("Search query must be at least 2 characters")
        
        is_admin = _is_admin(request)
        
        products, total_count, filters = ProductService.get_products(
            page=page,
            limit=limit,
            search=query,
            is_admin=is_admin,
        )
        
        return APIResponse.success(
            data={
                "items": products,
                "total": total_count,
                "page": page,
                "limit": limit,
                "query": query
            },
            message=f"Results for {query}"
        )
        
    except ValueError as e:
        logger.error(f"Product search error: {str(e)}")
        return APIResponse.bad_request("Invalid query parameter")
    except Exception as e:
        logger.error(f"Product search error: {str(e)}")
        return APIResponse.server_error()


# ==================== AUTHENTICATED USER VIEWS ====================

# apps/products/views.py - Update wishlist_list

@csrf_exempt
@require_http_methods(["GET", "POST"])
@jwt_required
def wishlist_list(request):
    """Get or add to wishlist"""
    try:
        user = request.user
        is_admin = _is_admin(request)
        
        if request.method == "GET":
            page = int(request.GET.get("page", 1))
            limit = int(request.GET.get("limit", 20))
            grouped = request.GET.get("grouped", "true").lower() == "true"  # Allow client to choose
            
            items, total = WishlistService.get_user_wishlist(
                user, page, limit, is_admin=is_admin, grouped=grouped
            )
            
            return APIResponse.success(
                data={
                    "items": items,
                    "total": total,
                    "page": page,
                    "limit": limit,
                    "grouped": grouped
                },
                message="Wishlist retrieved successfully"
            )
        
        elif request.method == "POST":
            data = json.loads(request.body)
            
            if "variant_id" not in data:
                return APIResponse.bad_request("variant_id is required")
            
            wishlist_item, error = WishlistService.add_to_wishlist(user, data["variant_id"])
            
            if error:
                if "already" in error.lower():
                    return APIResponse.conflict(error)
                return APIResponse.bad_request(error)
            
            return APIResponse.created(
                data={"wishlist_id": str(wishlist_item.id)},
                message="Added to wishlist"
            )
            
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Wishlist error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
def wishlist_remove(request, variant_id):
    """Remove from wishlist"""
    try:
        user = request.user
        
        success, error = WishlistService.remove_from_wishlist(user, variant_id)
        
        if not success:
            return APIResponse.not_found(error)
        
        return APIResponse.success(message="Removed from wishlist")
        
    except Exception as e:
        logger.error(f"Wishlist remove error: {str(e)}")
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
    """Admin: List all products (including drafts)"""
    try:
        page = int(request.GET.get("page", 1))
        limit = int(request.GET.get("limit", 20))
        status = request.GET.get("status")  # Get status filter
        search = request.GET.get("search", "").strip()
        
        # Call get_products with status parameter
        products_data, total, filters_used = ProductService.get_products(
            page=page,
            limit=limit,
            search=search,
            is_admin=True,  # Admin sees all
            status=status,  # Pass status filter
        )
        
        return APIResponse.success(
            data={
                "products": products_data,
                "total": total,
                "page": page,
                "limit": limit
            },
            message="Products listed successfully"
        )
        
    except Exception as e:
        logger.error(f"Admin product list error: {str(e)}")
        import traceback
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
            from .selectors import get_product_by_id
            product = get_product_by_id(product_id, include_inactive=True)
            
            if not product:
                return APIResponse.not_found("Product not found")
            
            from .schemas import serialize_product
            product_data = serialize_product(product, is_admin=True, include_variants=True)
            
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
        from apps.products.services.product_service import AdminProductService
        
        # Validate request data
        cleaned, errors = validate_product_bulk_action(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)
        
        # Execute bulk action
        results, error = AdminProductService.bulk_action_products(
            product_ids=cleaned['product_ids'],
            action=cleaned['action'],
            user=request.user
        )
        
        if error:
            return APIResponse.validation_error(error)
        
        # Serialize and return response
        serialized_results = serialize_product_bulk_action_result(results)
        
        if results['failed_count'] == 0:
            message = f"Successfully {cleaned['action']}ed {results['success_count']} products"
        else:
            message = f"Processed {results['success_count']} successfully, {results['failed_count']} failed"
        
        return APIResponse.success(
            data=serialized_results,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Admin product bulk action error: {str(e)}")
        return APIResponse.server_error()

@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@multipart_request_allowed
def admin_variant_create(request, product_id):
    """Admin: Create product variant with images"""
    try:
        data = request.json_data if hasattr(request, 'json_data') else {}
        files = request.files_data if hasattr(request, 'files_data') else request.FILES
        
        # Handle boolean field
        if "is_default" in data:
            data["is_default"] = data["is_default"] in ["true", "True", True, "1", 1]
        
        # Validate input with admin privileges
        cleaned, errors = validate_variant_create(data, is_admin=True)
        if errors:
            return APIResponse.validation_error(errors)
        
        variant, errors = AdminProductService.create_variant(
            product_id=product_id,
            data=cleaned,
            user=request.user,
            image_files=files
        )
        
        if errors:
            return APIResponse.validation_error(errors)
        
        return APIResponse.created(
            data={"variant_id": str(variant.id), "sku": variant.sku},
            message="Variant created successfully"
        )
        
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin variant create error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_variant_update(request, variant_id):
    """Admin: Update product variant"""
    try:
        data = request.json_data
        
        variant, errors = AdminProductService.update_variant(variant_id, data, request.user)
        
        if errors:
            return APIResponse.validation_error(errors)
        
        return APIResponse.success(
            data={"variant_id": str(variant.id)},
            message="Variant updated successfully"
        )
        
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin variant update error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
def admin_variant_image_upload(request, variant_id):
    """Admin: Upload variant image"""
    try:
        if "image" not in request.FILES:
            return APIResponse.bad_request("No image file provided")
        
        image_file = request.FILES["image"]
        image_type = request.POST.get("image_type", "gallery")
        alt_text = request.POST.get("alt_text", "")
        
        # Validate file type
        allowed_extensions = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
        import os
        ext = os.path.splitext(image_file.name)[1].lower()
        if ext not in allowed_extensions:
            return APIResponse.bad_request(f"Invalid file type. Allowed: {', '.join(allowed_extensions)}")
        
        # Validate file size (max 5MB)
        if image_file.size > 5 * 1024 * 1024:
            return APIResponse.bad_request("Image file too large. Maximum size is 5MB")
        
        image, errors = AdminProductService.add_variant_image(
            variant_id=variant_id,
            image_file=image_file,
            image_type=image_type,
            alt_text=alt_text,
            user=request.user,
        )
        
        if errors:
            return APIResponse.validation_error(errors)
        
        return APIResponse.created(
            data={"image_id": str(image.id), "url": image.image.url},
            message="Image uploaded successfully"
        )
        
    except Exception as e:
        logger.error(f"Admin image upload error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_variant_detail(request, variant_id):
    """Admin: Get single variant details"""
    try:
        from apps.products.selectors import get_variant_by_id
        from apps.products.schemas import serialize_variant
        
        variant = get_variant_by_id(variant_id, require_active=False)
        if not variant:
            return APIResponse.not_found("Variant not found")
        
        variant_data = serialize_variant(variant, is_admin=True, include_images=True)
        variant_data["product"] = {
            "id": str(variant.product.id),
            "title": variant.product.title,
            "slug": variant.product.slug,
        }
        
        return APIResponse.success(
            data=variant_data,
            message="Variant retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Admin variant detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
@role_required("admin", "staff")
def admin_variant_delete(request, variant_id):
    """Admin: Delete product variant"""
    try:
        from apps.products.selectors import get_variant_by_id
        
        variant = get_variant_by_id(variant_id, require_active=False)
        if not variant:
            return APIResponse.not_found("Variant not found")
        
        variant.delete()
        
        logger.info(f"Variant deleted by admin {request.user.email}: {variant.sku}")
        
        return APIResponse.success(message="Variant deleted successfully")
        
    except Exception as e:
        logger.error(f"Admin variant delete error: {str(e)}")
        return APIResponse.server_error()

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def product_analytics(request):
    """
    Get product analytics with caching and optimized queries
    Query params:
    - chart_type: specific chart to fetch (optional, reduces response size)
    - refresh: force refresh cache (optional)
    """
    try:
        chart_type = request.GET.get('chart_type')
        refresh = request.GET.get('refresh', '').lower() == 'true'
        
        # Clear cache if refresh requested
        if refresh:
            cache_key = f"analytics:products:dashboard:{chart_type or 'all'}"
            cache.delete(cache_key)
        
        # Get analytics data
        if chart_type and chart_type != 'all':
            # Fetch only specific chart
            chart_data = product_analytics_service.get_chart_data(request, chart_type)
            return APIResponse.success(
                data={"charts": {chart_type: chart_data.get(chart_type)}},
                message=f"Product {chart_type} chart data retrieved"
            )
        else:
            # Fetch complete dashboard
            dashboard_data = product_analytics_service.get_dashboard_data(request)
            return APIResponse.success(
                data=dashboard_data,
                message="Product analytics retrieved successfully"
            )
        
    except Exception as e:
        logger.error(f"Product analytics error: {str(e)}")
        return APIResponse.server_error()
# apps/products/views.py - Update category views

@csrf_exempt
@require_http_methods(["GET"])
def category_list(request):
    """Get all categories (hide hidden from customers)"""
    try:
        is_admin = _is_admin(request)
        
        # Use the updated selector that respects hidden flag
        from apps.products.selectors import get_all_categories
        categories = get_all_categories(only_active=True, is_admin=is_admin)
        
        # Also get product counts for visible categories only
        for category in categories:
            if is_admin:
                # Admin sees all products in category
                category.product_count = Product.objects.filter(category=category).count()
            else:
                # Customers only see published products in non-hidden categories
                category.product_count = Product.objects.filter(
                    category=category, 
                    status=Product.STATUS_PUBLISHED
                ).count()
        
        from apps.products.schemas import serialize_category_list
        categories_data = serialize_category_list(categories, is_admin=is_admin)
        
        return APIResponse.success(
            data={"categories": categories_data},
            message="Categories retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Category list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
def category_detail(request, slug):
    """Get detailed category information (hide hidden from customers)"""
    try:
        is_admin = _is_admin(request)
        
        from apps.products.selectors import get_category_by_slug
        category = get_category_by_slug(slug, only_active=True, is_admin=is_admin)
        
        if not category:
            return APIResponse.not_found("Category not found")
        
        # If category is hidden and user is not admin, 404
        if category.is_hidden and not is_admin:
            return APIResponse.not_found("Category not found")
        
        from apps.products.schemas import serialize_category
        from apps.products.selectors import get_subcategories
        
        category_data = serialize_category(category, is_admin=is_admin)
        
        # Get subcategories (respecting hidden flag)
        subcategories = get_subcategories(str(category.id), only_active=True, is_admin=is_admin)
        
        subcategories_data = []
        for sub in subcategories:
            sub_data = {
                "id": str(sub.id),
                "name": sub.name,
                "slug": sub.slug,
            }
            # Count products in subcategory
            if is_admin:
                product_count = Product.objects.filter(category=sub).count()
            else:
                product_count = Product.objects.filter(
                    category=sub, 
                    status=Product.STATUS_PUBLISHED
                ).count()
            sub_data["product_count"] = product_count
            subcategories_data.append(sub_data)
        
        category_data["subcategories"] = subcategories_data
        
        return APIResponse.success(category_data)
        
    except Exception as e:
        logger.error(f"Category detail error: {str(e)}")
        return APIResponse.server_error()



# apps/products/views.py - Separate admin category views

# ==================== ADMIN CATEGORY VIEWS ====================

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_category_list(request):
    """Admin: List all categories (including hidden and inactive)"""
    try:
        from apps.products.selectors import get_all_categories
        from apps.products.schemas import serialize_category_list
        
        categories = get_all_categories(only_active=False, is_admin=True)
        
        return APIResponse.success(
            {"categories": serialize_category_list(categories, is_admin=True)},
            "Categories retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Admin category list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_category_detail(request, category_id):
    """Admin: Get single category details"""
    try:
        from apps.products.selectors import get_category_by_id
        from apps.products.schemas import serialize_category
        
        category = get_category_by_id(category_id, is_admin=True)
        if not category:
            return APIResponse.not_found("Category not found")
        
        category_data = serialize_category(category, is_admin=True)
        return APIResponse.success(category_data, "Category details retrieved")
    except Exception as e:
        logger.error(f"Admin category detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
def admin_category_create(request):
    """Admin: Create new category"""
    try:
        from apps.products.services.product_service import CategoryService
        
        # Handle multipart form data
        if request.content_type and 'multipart/form-data' in request.content_type:
            data = request.POST.dict()
            image_file = request.FILES.get('image')
        else:
            data = json.loads(request.body)
            image_file = None
        
        # Extract data with proper defaults
        name = data.get("name")
        if not name:
            return APIResponse.bad_request("Category name is required")
        
        category, errors = CategoryService.create_category(
            name=name,
            description=data.get("description", ""),
            parent_id=data.get("parent_id"),
            is_active=data.get("is_active", "true").lower() == "true",
            is_hidden=data.get("is_hidden", "false").lower() == "true",
            meta_title=data.get("meta_title", ""),
            meta_description=data.get("meta_description", ""),
            image_file=image_file,
            user=request.user
        )
        
        if errors:
            return APIResponse.validation_error(errors)
        
        return APIResponse.created(
            data={
                "category_id": str(category.id),
                "slug": category.slug,
                "name": category.name,
                "is_hidden": category.is_hidden
            },
            message="Category created successfully"
        )
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin category create error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST", "PUT"])  # Support both POST (with _method) and PUT
@jwt_required
@role_required("admin", "staff")
def admin_category_update(request, category_id):
    """Admin: Update category"""
    try:    
        
        # Parse data based on content type
        if request.content_type and 'multipart/form-data' in request.content_type:
            # For POST with multipart, request.POST works
            if request.method == "POST":
                data = request.POST.dict()
                image_file = request.FILES.get('image')
            else:
                # For PUT with multipart, we need to parse manually
                # Let's require POST with _method=PUT instead
                return APIResponse.bad_request(
                    "For image updates, please use POST with _method=PUT parameter"
                )
        else:
            # JSON data (works for both POST and PUT)
            data = json.loads(request.body)
            image_file = None
        
        # Prepare update data
        update_data = {}
        
        if 'name' in data and data['name']:
            update_data['name'] = data['name']
        if 'description' in data:
            update_data['description'] = data['description']
        if 'parent_id' in data:
            parent_val = data['parent_id']
            if parent_val and parent_val not in ['null', 'none', '']:
                update_data['parent_id'] = parent_val
            else:
                update_data['parent_id'] = None
        if 'is_active' in data:
            val = data['is_active']
            update_data['is_active'] = val.lower() == 'true' if isinstance(val, str) else bool(val)
        if 'is_hidden' in data:
            val = data['is_hidden']
            update_data['is_hidden'] = val.lower() == 'true' if isinstance(val, str) else bool(val)
        if 'meta_title' in data:
            update_data['meta_title'] = data['meta_title']
        if 'meta_description' in data:
            update_data['meta_description'] = data['meta_description']
        
        if not update_data:
            return APIResponse.bad_request("No data provided for update")
        
        # Handle image removal flag
        remove_image = data.get('remove_image', 'false').lower() == 'true' if isinstance(data.get('remove_image'), str) else bool(data.get('remove_image', False))
        
        category, errors = CategoryService.update_category(
            category_id=category_id,
            data=update_data,
            image_file=image_file,
            remove_image=remove_image,
            user=request.user
        )
        
        if errors:
            return APIResponse.validation_error(errors)
        
        return APIResponse.success(
            data={
                "category_id": str(category.id),
                "slug": category.slug,
                "name": category.name,
                "is_hidden": category.is_hidden
            },
            message="Category updated successfully"
        )
    except json.JSONDecodeError:
        return APIResponse.bad_request("Invalid JSON data")
    except Exception as e:
        logger.error(f"Admin category update error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@jwt_required
@role_required("admin", "staff")
def admin_category_delete(request, category_id):
    """Admin: Delete category"""
    try:
        from apps.products.selectors import get_category_by_id
        from apps.products.models import Product
        
        category = get_category_by_id(category_id, is_admin=True)
        if not category:
            return APIResponse.not_found("Category not found")
        
        # Check for subcategories
        if category.children.exists():
            return APIResponse.bad_request("Cannot delete category with subcategories")
        
        # Check for products
        if Product.objects.filter(category=category).exists():
            return APIResponse.bad_request("Cannot delete category with products")
        
        category.delete()
        
        logger.info(f"Category deleted by admin {request.user.email}: {category.name}")
        
        return APIResponse.success(message="Category deleted successfully")
    except Exception as e:
        logger.error(f"Admin category delete error: {str(e)}")
        return APIResponse.server_error()
    
    
@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_category_bulk_action(request):
    """Admin: Perform bulk actions on categories"""
    try:
        from apps.products.schemas import validate_bulk_action, serialize_bulk_action_result
        from apps.products.services.product_service import CategoryService
        
        # Validate request data
        cleaned, errors = validate_bulk_action(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)
        
        # Execute bulk action
        results, error = CategoryService.bulk_action_categories(
            category_ids=cleaned['category_ids'],
            action=cleaned['action'],
            user=request.user
        )
        
        if error:
            return APIResponse.validation_error(error)
        
        # Serialize and return response
        serialized_results = serialize_bulk_action_result(results)
        
        if serialized_results['failed_count'] == 0:
            print("BULKKK",serialized_results["failed_count"])
            message = f"Successfully {cleaned['action']}ed {serialized_results['success_count']} categories"
        else:
            message = f"Processed {serialized_results['success_count']} successfully, {serialized_results['failed_count']} failed"
        
        return APIResponse.success(
            data=serialized_results,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Admin category bulk action error: {str(e)}")
        return APIResponse.server_error()
    
    
admin_product_update = admin_product_detail  