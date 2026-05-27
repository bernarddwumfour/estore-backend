import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

# Your existing decorators
from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
    multipart_request_allowed,
    role_required,
)
from estore.utils.responses import APIResponse  # Your existing response class
from ..services.product_service import (
    CategoryService,
)
from ..models import ProductVariant
from ..models import Product


logger = logging.getLogger(__name__)


def _is_admin(request) -> bool:
    """Check if user has admin/staff role"""
    if not hasattr(request, "user") or not request.user:
        return False
    return getattr(request.user, "role", "customer") in ["admin", "staff"]


@csrf_exempt
@require_http_methods(["GET"])
def category_list(request):
    try:
        from apps.products.selectors import get_all_categories
        from apps.products.schemas import serialize_category_list
        
        search = request.GET.get('search', None)
        parent_id = request.GET.get('parent_id', None)
        include_product_counts = request.GET.get('include_counts', 'true').lower() == 'true'
        as_tree = request.GET.get('as_tree', 'false').lower() == 'true'
        
        try:
            page = int(request.GET.get('page', 1))
            limit = int(request.GET.get('limit', 20))
        except ValueError:
            page = 1
            limit = 20
        
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        
        categories, total, pagination_meta = get_all_categories(
            only_active=True,
            is_admin=False, 
            search=search,
            parent_id=parent_id,
            is_hidden=None, 
            sort_by="name", 
            sort_order="asc",
            page=page,
            limit=limit
        )
        
        if include_product_counts:
            from apps.products.models import Product
            
            for category in categories:
                category.product_count = Product.objects.filter(
                    category=category, 
                    status=Product.STATUS_PUBLISHED
                ).count()
        
        categories_data = serialize_category_list(categories, is_admin=False)
        
        if include_product_counts:
            for i, category_data in enumerate(categories_data):
                category_data['product_count'] = categories[i].product_count if hasattr(categories[i], 'product_count') else 0
        
        if as_tree:
          
            all_categories, total_all, _ = get_all_categories(
                only_active=True,
                is_admin=False,
                search=search,
                parent_id=None,  # Get all for tree building
                is_hidden=None,
                sort_by="name",
                sort_order="asc",
                page=1,
                limit=1000  # Large limit for tree
            )
            
            all_categories_data = serialize_category_list(all_categories, is_admin=False)
            
            category_dict = {cat['id']: cat for cat in all_categories_data}
            
            tree = []
            for cat in all_categories_data:
                cat['children'] = []
                if cat['parent_id'] and cat['parent_id'] in category_dict:
                    category_dict[cat['parent_id']]['children'].append(cat)
                else:
                    tree.append(cat)
            
            categories_data = tree
            total = len(tree)
        
        response_data = {
            "categories": categories_data,
            "total": total,
            "pagination": pagination_meta if not as_tree else None
        }
        
        if as_tree:
            response_data.pop('pagination', None)
        
        return APIResponse.success(
            data=response_data,
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
# apps/products/views.py (update the admin_category_list view)

@csrf_exempt
@require_http_methods(["GET"])
@jwt_required
@role_required("admin", "staff")
def admin_category_list(request):
    """Admin: List all categories with filters, search, sorting, and pagination"""
    try:
        from apps.products.selectors import get_all_categories
        from apps.products.schemas import serialize_category_list, serialize_pagination_metadata
        
        # Get query parameters
        search = request.GET.get('search', None)
        parent_id = request.GET.get('parent_id', None)
        is_hidden_param = request.GET.get('is_hidden', None)
        is_active_param = request.GET.get('is_active', None)
        sort_by = request.GET.get('sort_by', 'name')
        sort_order = request.GET.get('sort_order', 'asc')
        
        # Pagination parameters
        try:
            page = int(request.GET.get('page', 1))
            limit = int(request.GET.get('limit', 20))
        except ValueError:
            page = 1
            limit = 20
        
        # Validate limit (max 100 items per page)
        if limit > 100:
            limit = 100
        if limit < 1:
            limit = 20
        
        # Convert string params to boolean
        is_hidden = None
        if is_hidden_param is not None and is_hidden_param != '':
            is_hidden = is_hidden_param.lower() == 'true'
        
        only_active = True
        if is_active_param is not None and is_active_param != '':
            only_active = is_active_param.lower() == 'true'
        
        # Get categories with filters
        categories, total, pagination_meta = get_all_categories(
            only_active=only_active,
            is_admin=True,
            search=search,
            parent_id=parent_id,
            is_hidden=is_hidden,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            limit=limit
        )
        
        return APIResponse.success(
            {
                "categories": serialize_category_list(categories, is_admin=True),
                "total": total,
                "pagination": serialize_pagination_metadata(pagination_meta)
            },
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
    
    
