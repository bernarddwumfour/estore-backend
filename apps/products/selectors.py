# apps/products/selectors.py
"""
Database read operations - no business logic, just queries
"""
from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q, Avg
from django.core.paginator import Paginator
from apps.products.models import Product, ProductVariant, Category, ProductReview, Wishlist
from .schemas import serialize_product,serialize_variant

# ==================== PRODUCT SELECTORS ====================

def get_product_by_id(product_id: str, include_inactive: bool = False) -> Optional[Product]:
    """Get product by ID"""
    try:
        queryset = Product.objects.all()
        if not include_inactive:
            queryset = queryset.filter(status=Product.STATUS_PUBLISHED)
        return queryset.get(id=product_id)
    except (Product.DoesNotExist, ValueError):
        return None


def get_product_by_slug(slug: str, include_inactive: bool = False) -> Optional[Product]:
    """Get product by slug"""
    try:
        queryset = Product.objects.all()
        if not include_inactive:
            queryset = queryset.filter(status=Product.STATUS_PUBLISHED)
        return queryset.get(slug=slug)
    except Product.DoesNotExist:
        return None



# apps/products/selectors.py - Add status parameter

def get_products_filtered(
    page: int = 1,
    limit: int = 20,
    category_slug: str = None,
    brand: str = None,
    min_price: float = None,
    max_price: float = None,
    in_stock: bool = None,
    featured: bool = None,
    bestseller: bool = None,
    new: bool = None,
    search: str = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    include_drafts: bool = False,
    is_admin: bool = False,
    status: str = None,  # Add status parameter
) -> Tuple[List[Product], int]:
    """Get filtered and paginated products - respects hidden categories"""
    
    queryset = Product.objects.all().prefetch_related('variants').select_related('category')
    
    # Filter by status if provided
    if status:
        queryset = queryset.filter(status=status)
    elif not include_drafts:
        queryset = queryset.filter(status=Product.STATUS_PUBLISHED)
    
    # Rest of the function remains the same...
    if category_slug:
        descendant_categories = Category.get_descendants_from_slug(category_slug)
        if descendant_categories:
            if not is_admin:
                descendant_categories = [cat for cat in descendant_categories if not cat.is_hidden]
            
            if descendant_categories:
                category_ids = [cat.id for cat in descendant_categories]
                queryset = queryset.filter(category_id__in=category_ids)
            else:
                return [], 0
    if brand:
        queryset = queryset.filter(variants__attributes__brand=brand).distinct()
    
    if min_price is not None:
        queryset = queryset.filter(variants__price__gte=min_price).distinct()
    if max_price is not None:
        queryset = queryset.filter(variants__price__lte=max_price).distinct()
    
    # Stock filtering
    if in_stock is True:
        queryset = queryset.filter(variants__stock__gt=0).distinct()
    elif in_stock is False:
        queryset = queryset.filter(variants__stock=0).distinct()
    
    # Flags
    if featured:
        queryset = queryset.filter(is_featured=True)
    if bestseller:
        queryset = queryset.filter(is_bestseller=True)
    if new:
        queryset = queryset.filter(is_new=True)
    
    # Search
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) |
            Q(description__icontains=search) |
            Q(slug__icontains=search)
        )
    
    # Sorting
    sort_mapping = {
        "price_asc": "variants__price",
        "price_desc": "-variants__price",
        "rating": "-average_rating",
        "newest": "-created_at",
        "oldest": "created_at",
        "name_asc": "title",
        "name_desc": "-title",
    }
    
    sort_field = sort_mapping.get(sort_by, "-created_at")
    if sort_order == "asc" and sort_by not in ["price_asc", "price_desc"]:
        sort_field = sort_field.lstrip('-')
    
    queryset = queryset.order_by(sort_field).distinct()
    
    # Pagination
    paginator = Paginator(queryset, limit)
    page_obj = paginator.get_page(page)
    
    return list(page_obj), paginator.count


def get_related_products(product: Product, limit: int = 4, include_drafts: bool = False) -> List[Product]:
    """Get related products (same category)"""
    if not product.category:
        return []
    
    queryset = Product.objects.filter(category=product.category).exclude(id=product.id)
    
    if not include_drafts:
        queryset = queryset.filter(status=Product.STATUS_PUBLISHED)
    
    return list(queryset.order_by("-created_at")[:limit])


# ==================== VARIANT SELECTORS ====================

def get_variant_by_id(variant_id: str, require_active: bool = True) -> Optional[ProductVariant]:
    """Get variant by ID"""
    try:
        queryset = ProductVariant.objects.all()
        if require_active:
            queryset = queryset.filter(is_active=True)
        return queryset.get(id=variant_id)
    except (ProductVariant.DoesNotExist, ValueError):
        return None


def get_variant_by_sku(sku: str) -> Optional[ProductVariant]:
    """Get variant by SKU"""
    try:
        return ProductVariant.objects.get(sku=sku)
    except ProductVariant.DoesNotExist:
        return None


def get_variants_by_product(product_id: str, only_active: bool = True) -> List[ProductVariant]:
    """Get all variants for a product"""
    queryset = ProductVariant.objects.filter(product_id=product_id)
    if only_active:
        queryset = queryset.filter(is_active=True)
    return list(queryset.order_by("-is_default", "sku"))


# ==================== CATEGORY SELECTORS ====================
# apps/products/selectors.py - Update category selectors

def get_category_by_id(category_id: str, is_admin: bool = False) -> Optional[Category]:
    """Get category by ID - respect hidden flag based on role"""
    try:
        queryset = Category.objects.all()
        if not is_admin:
            queryset = queryset.filter(is_hidden=False)  # Hide hidden categories from customers
        return queryset.get(id=category_id)
    except (Category.DoesNotExist, ValueError):
        return None


def get_category_by_slug(slug: str, only_active: bool = True, is_admin: bool = False) -> Optional[Category]:
    """Get category by slug - respect hidden flag based on role"""
    try:
        queryset = Category.objects.all()
        
        if only_active:
            queryset = queryset.filter(is_active=True)
        
        if not is_admin:
            queryset = queryset.filter(is_hidden=False)  # Hide hidden categories from customers
        
        return queryset.get(slug=slug)
    except Category.DoesNotExist:
        return None


def get_all_categories(only_active: bool = True, is_admin: bool = False) -> List[Category]:
    """Get all categories - respect hidden flag based on role"""
    queryset = Category.objects.all()
    print("IS ADMIN : ",is_admin)
    
    if only_active:
        queryset = queryset.filter(is_active=True)
    
    if not is_admin:
        queryset = queryset.filter(is_hidden=False)  # Hide hidden categories from customers
    
    return list(queryset.order_by("name"))


def get_subcategories(category_id: str, only_active: bool = True, is_admin: bool = False) -> List[Category]:
    """Get subcategories - respect hidden flag based on role"""
    category = get_category_by_id(category_id, is_admin=is_admin)
    if not category:
        return []
    
    queryset = category.children.all()
    
    if only_active:
        queryset = queryset.filter(is_active=True)
    
    if not is_admin:
        queryset = queryset.filter(is_hidden=False)  # Hide hidden subcategories from customers
    
    return list(queryset.order_by("name"))


def get_visible_categories_tree(is_admin: bool = False) -> List[Category]:
    """Get top-level categories with their visible children"""
    queryset = Category.objects.filter(parent__isnull=True)
    
    if not is_admin:
        queryset = queryset.filter(is_active=True, is_hidden=False)
    else:
        queryset = queryset.filter(is_active=True)
    
    categories = list(queryset.order_by("name"))
    
    # Recursively add children
    for category in categories:
        category.visible_children = get_subcategories(
            str(category.id), 
            only_active=True, 
            is_admin=is_admin
        )
    
    return categories
# ==================== REVIEW SELECTORS ====================

def get_reviews_by_product(
    product_slug: str,
    page: int = 1,
    limit: int = 20,
    rating: int = None,
    verified: bool = None,
    only_approved: bool = True
) -> Tuple[List[ProductReview], int]:
    """Get reviews for a product"""
    product = get_product_by_slug(product_slug)
    if not product:
        return [], 0
    
    queryset = ProductReview.objects.filter(product=product)
    
    if only_approved:
        queryset = queryset.filter(is_approved=True)
    
    if rating:
        queryset = queryset.filter(rating=rating)
    
    if verified is not None:
        queryset = queryset.filter(is_verified_purchase=verified)
    
    queryset = queryset.order_by("-created_at")
    
    paginator = Paginator(queryset, limit)
    page_obj = paginator.get_page(page)
    
    return list(page_obj), paginator.count


def get_product_rating_stats(product_id: str) -> Dict[str, Any]:
    """Get rating statistics for a product"""
    reviews = ProductReview.objects.filter(product_id=product_id, is_approved=True)
    
    if not reviews.exists():
        return {
            "average": 0,
            "total": 0,
            "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        }
    
    distribution = {}
    for i in range(1, 6):
        distribution[i] = reviews.filter(rating=i).count()
    
    return {
        "average": float(reviews.aggregate(Avg("rating"))["avg"] or 0),
        "total": reviews.count(),
        "distribution": distribution
    }


# ==================== WISHLIST SELECTORS ====================

def get_wishlist_items(user, page: int = 1, limit: int = 20, is_admin: bool = False) -> Tuple[List[Dict], int]:
    """Get user's wishlist items grouped by product with variants"""
    
    # Get all wishlist items with eager loading
    wishlist_items = Wishlist.objects.filter(user=user).order_by("-created_at").select_related(
        "variant"
    ).prefetch_related(
        "variant__product",
        "variant__product__category",
        "variant__images",
    )
    
    # Group by product
    products_dict = {}
    
    for item in wishlist_items:
        variant = item.variant
        product = variant.product
        product_id = str(product.id)
        
        # Serialize variant using your schema
        variant_data = serialize_variant(variant, is_admin=is_admin, include_images=True)
        
        if product_id not in products_dict:
            products_dict[product_id] = {
                "product": product,
                "variants": [],
                "wishlist_items": [],  # Store original items if needed
            }
        
        products_dict[product_id]["variants"].append(variant_data)
        products_dict[product_id]["wishlist_items"].append(item)
    
    
    # Convert to list of serialized products
    result = []
    for group_data in products_dict.values():
        product_data = serialize_product(group_data["product"], is_admin=is_admin, include_variants=False)
        product_data["variants"] = group_data["variants"]
        
        # Set default variant from the variants list
        default_variant = None
        for variant in group_data["variants"]:
            if variant.get("is_default"):
                default_variant = variant
                break
        
        if not default_variant and group_data["variants"]:
            default_variant = group_data["variants"][0]
        
        product_data["default_variant"] = default_variant
        product_data["variant"] = default_variant
        
        result.append(product_data)
    
    # Apply pagination
    total = len(result)
    offset = (page - 1) * limit
    paginated_result = result[offset:offset + limit]
    
    return paginated_result, total


def get_wishlist_items_flat(user, page: int = 1, limit: int = 20, is_admin: bool = False) -> Tuple[List[Dict], int]:
    """Get user's wishlist items as flat list (each variant as separate item)"""
    
    queryset = Wishlist.objects.filter(user=user).order_by("-created_at").select_related(
        "variant"
    ).prefetch_related(
        "variant__product",
        "variant__product__category",
        "variant__images",
    )
    
    total = queryset.count()
    
    # Paginate
    offset = (page - 1) * limit
    paginated_items = queryset[offset:offset + limit]
    
    # Serialize using schema
    from apps.products.schemas import serialize_wishlist_item
    
    items_data = [serialize_wishlist_item(item, is_admin=is_admin) for item in paginated_items]
    
    return items_data, total


def is_in_wishlist(user, variant_id: str) -> bool:
    """Check if variant is in user's wishlist"""
    return Wishlist.objects.filter(user=user, variant_id=variant_id).exists()