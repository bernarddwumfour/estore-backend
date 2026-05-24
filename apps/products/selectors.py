# apps/products/selectors.py
"""
Database read operations - no business logic, just queries
"""

from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q, Avg
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from apps.products.models import (
    Product,
    ProductVariant,
    Category,
    ProductReview,
    Wishlist,
)
from .schemas import serialize_product, serialize_variant

# ==================== PRODUCT SELECTORS ====================


def get_product_by_id(
    product_id: str, include_inactive: bool = False
) -> Optional[Product]:
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


def get_admin_products_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    status: str = None,
    category_id: str = None,
    is_featured: bool = None,
    is_bestseller: bool = None,
    is_new: bool = None,
    has_stock: bool = None,
    min_price: float = None,
    max_price: float = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[Product], int, Dict]:
    """Get filtered and paginated products for admin"""

    # Start with base queryset
    queryset = Product.objects.select_related("category").prefetch_related("variants")

    # Filter by status
    if status:
        queryset = queryset.filter(status=status)

    # Search by title or description
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(slug__icontains=search)
        )

    # Filter by category
    if category_id:
        queryset = queryset.filter(category_id=category_id)

    # Filter by flags
    if is_featured is not None:
        queryset = queryset.filter(is_featured=is_featured)
    if is_bestseller is not None:
        queryset = queryset.filter(is_bestseller=is_bestseller)
    if is_new is not None:
        queryset = queryset.filter(is_new=is_new)

    # Get the list of products first (for property filtering)
    products_list = list(queryset)

    # Filter by stock (using property - can't filter in DB)
    if has_stock is not None:
        products_list = [p for p in products_list if p.has_stock == has_stock]

    # Filter by price range (using properties)
    if min_price is not None:
        products_list = [p for p in products_list if p.min_price >= min_price]
    if max_price is not None:
        products_list = [p for p in products_list if p.max_price <= max_price]

    # Apply sorting
    if sort_by == "title":
        products_list.sort(key=lambda p: p.title, reverse=(sort_order == "desc"))
    elif sort_by == "min_price":
        products_list.sort(key=lambda p: p.min_price, reverse=(sort_order == "desc"))
    elif sort_by == "max_price":
        products_list.sort(key=lambda p: p.max_price, reverse=(sort_order == "desc"))
    elif sort_by == "total_stock":
        products_list.sort(key=lambda p: p.total_stock, reverse=(sort_order == "desc"))
    elif sort_by == "status":
        products_list.sort(key=lambda p: p.status, reverse=(sort_order == "desc"))
    else:  # created_at or default
        products_list.sort(key=lambda p: p.created_at, reverse=(sort_order == "desc"))

    # Get total count
    total = len(products_list)

    # Apply pagination
    start = (page - 1) * limit
    end = start + limit
    paginated_products = products_list[start:end]

    # Calculate pagination metadata
    total_pages = (total + limit - 1) // limit if limit > 0 else 1
    has_next = page < total_pages
    has_previous = page > 1

    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_page": page + 1 if has_next else None,
        "previous_page": page - 1 if has_previous else None,
        "start_index": start + 1 if total > 0 else 0,
        "end_index": min(end, total),
    }

    return paginated_products, total, pagination_meta


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
) -> Tuple[List[Product], int, Dict]:
    """Get filtered and paginated products for customers"""

    queryset = Product.objects.select_related("category").prefetch_related("variants")

    # Filter by status - only published for customers
    if not include_drafts:
        queryset = queryset.filter(status=Product.STATUS_PUBLISHED)

    # Filter by category slug and respect hidden categories
    if category_slug:
        try:
            category = Category.objects.get(slug=category_slug, is_active=True)

            # Check if category is hidden (only for non-admin)
            if not is_admin and category.is_hidden:
                return [], 0, {}

            # Get all descendant categories
            descendant_categories = category.get_all_descendants()

            # Filter out hidden categories for non-admin
            if not is_admin:
                descendant_categories = [
                    cat for cat in descendant_categories if not cat.is_hidden
                ]

            if descendant_categories:
                category_ids = [cat.id for cat in descendant_categories]
                queryset = queryset.filter(category_id__in=category_ids)
            else:
                return [], 0, {}
        except Category.DoesNotExist:
            return [], 0, {}

    # Filter by brand
    if brand:
        queryset = queryset.filter(variants__attributes__brand=brand).distinct()

    # Filter by price range (using min_price/max_price fields for performance)
    if min_price is not None:
        queryset = queryset.filter(min_price__gte=min_price)
    if max_price is not None:
        queryset = queryset.filter(max_price__lte=max_price)

    # Filter by stock
    if in_stock is not None:
        if in_stock:
            queryset = queryset.filter(total_stock__gt=0)
        else:
            queryset = queryset.filter(total_stock=0)

    # Filter by flags
    if featured is not None:
        queryset = queryset.filter(is_featured=featured)
    if bestseller is not None:
        queryset = queryset.filter(is_bestseller=bestseller)
    if new is not None:
        queryset = queryset.filter(is_new=new)

    # Search
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(slug__icontains=search)
        )

    # Apply sorting
    sort_mapping = {
        "price_asc": "min_price",
        "price_desc": "-min_price",
        "rating": "-average_rating",
        "newest": "-created_at",
        "oldest": "created_at",
        "name_asc": "title",
        "name_desc": "-title",
    }

    sort_field = sort_mapping.get(sort_by, "-created_at")
    queryset = queryset.order_by(sort_field)

    # Get total count before pagination
    total = queryset.count()

    # Apply pagination
    paginator = Paginator(queryset, limit)

    try:
        products_page = paginator.page(page)
    except PageNotAnInteger:
        products_page = paginator.page(1)
        page = 1
    except EmptyPage:
        products_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages

    # Calculate pagination metadata
    total_pages = paginator.num_pages
    has_next = products_page.has_next()
    has_previous = products_page.has_previous()

    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_page": page + 1 if has_next else None,
        "previous_page": page - 1 if has_previous else None,
        "start_index": (page - 1) * limit + 1 if total > 0 else 0,
        "end_index": min(page * limit, total),
    }

    return list(products_page), total, pagination_meta


def get_related_products(
    product: Product, limit: int = 4, include_drafts: bool = False
) -> List[Product]:
    """Get related products (same category)"""
    if not product.category:
        return []

    queryset = Product.objects.filter(category=product.category).exclude(id=product.id)

    if not include_drafts:
        queryset = queryset.filter(status=Product.STATUS_PUBLISHED)

    return list(queryset.order_by("-created_at")[:limit])


# ==================== VARIANT SELECTORS ====================


# apps/products/selectors.py - Add this function
def get_all_variants(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    product_id: str = None,
    is_active: bool = None,
    is_default: bool = None,
    min_price: float = None,
    max_price: float = None,
    in_stock: bool = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    is_admin: bool = False,
) -> Tuple[List[ProductVariant], int, Dict]:
    """Get all variants with optional filtering and pagination"""

    queryset = ProductVariant.objects.select_related("product").prefetch_related(
        "images"
    )

    # Filter by product
    if product_id:
        queryset = queryset.filter(product_id=product_id)

    # Filter by active status
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)

    # Filter by default status
    if is_default is not None:
        queryset = queryset.filter(is_default=is_default)

    # Filter by price range
    if min_price is not None:
        queryset = queryset.filter(price__gte=min_price)
    if max_price is not None:
        queryset = queryset.filter(price__lte=max_price)

    # Filter by stock
    if in_stock is True:
        queryset = queryset.filter(stock__gt=0)
    elif in_stock is False:
        queryset = queryset.filter(stock=0)

    # Search by SKU or product title
    if search:
        queryset = queryset.filter(
            Q(sku__icontains=search)
            | Q(product__title__icontains=search)
            | Q(product__slug__icontains=search)
        )

    # Apply admin filters (show inactive products only if admin)
    if not is_admin:
        queryset = queryset.filter(
            is_active=True, product__status=Product.STATUS_PUBLISHED
        )

    # Sorting
    sort_mapping = {
        "price_asc": "price",
        "price_desc": "-price",
        "stock_asc": "stock",
        "stock_desc": "-stock",
        "created_at": "-created_at",
        "updated_at": "-updated_at",
        "sku_asc": "sku",
        "sku_desc": "-sku",
        "product_title_asc": "product__title",
        "product_title_desc": "-product__title",
    }

    sort_field = sort_mapping.get(sort_by, "-created_at")
    if sort_order == "asc" and sort_by not in [
        "price_asc",
        "price_desc",
        "stock_asc",
        "stock_desc",
        "sku_asc",
        "sku_desc",
        "product_title_asc",
        "product_title_desc",
    ]:
        sort_field = sort_field.lstrip("-")

    queryset = queryset.order_by(sort_field)

    # Get total count before pagination
    total = queryset.count()

    # Apply pagination
    paginator = Paginator(queryset, limit)

    try:
        variants_page = paginator.page(page)
    except PageNotAnInteger:
        variants_page = paginator.page(1)
        page = 1
    except EmptyPage:
        variants_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages

    # Calculate pagination metadata
    total_pages = paginator.num_pages
    has_next = variants_page.has_next()
    has_previous = variants_page.has_previous()

    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_page": page + 1 if has_next else None,
        "previous_page": page - 1 if has_previous else None,
        "start_index": (page - 1) * limit + 1 if total > 0 else 0,
        "end_index": min(page * limit, total),
    }

    return list(variants_page), total, pagination_meta


def get_variant_by_id(
    variant_id: str, require_active: bool = True
) -> Optional[ProductVariant]:
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


def get_variants_by_product(
    product_id: str, only_active: bool = True
) -> List[ProductVariant]:
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
            queryset = queryset.filter(
                is_hidden=False
            )  # Hide hidden categories from customers
        return queryset.get(id=category_id)
    except (Category.DoesNotExist, ValueError):
        return None


def get_category_by_slug(
    slug: str, only_active: bool = True, is_admin: bool = False
) -> Optional[Category]:
    """Get category by slug - respect hidden flag based on role"""
    try:
        queryset = Category.objects.all()

        if only_active:
            queryset = queryset.filter(is_active=True)

        if not is_admin:
            queryset = queryset.filter(
                is_hidden=False
            )  # Hide hidden categories from customers

        return queryset.get(slug=slug)
    except Category.DoesNotExist:
        return None


def get_all_categories(
    only_active: bool = True,
    is_admin: bool = False,
    search: Optional[str] = None,
    parent_id: Optional[str] = None,
    is_hidden: Optional[bool] = None,
    sort_by: str = "name",
    sort_order: str = "asc",
    page: int = 1,
    limit: int = 20,
) -> Tuple[List[Category], int, Dict]:
    """
    Get all categories with filters, sorting, and pagination

    Returns:
        Tuple of (categories list, total count, pagination metadata)
    """
    queryset = Category.objects.select_related("parent").all()

    if only_active:
        queryset = queryset.filter(is_active=True)

    if not is_admin:
        queryset = queryset.filter(is_hidden=False)

    # Admin can filter by hidden status
    if is_admin and is_hidden is not None:
        queryset = queryset.filter(is_hidden=is_hidden)

    # Search by name or description
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search)
            | Q(description__icontains=search)
            | Q(slug__icontains=search)
        )

    # Filter by parent category
    if parent_id:
        if parent_id.lower() == "null":
            queryset = queryset.filter(parent__isnull=True)
        else:
            queryset = queryset.filter(parent_id=parent_id)

    # Apply sorting
    allowed_sort_fields = ["name", "created_at", "updated_at", "is_active", "is_hidden"]

    if sort_by in allowed_sort_fields:
        if sort_order == "desc":
            sort_by = f"-{sort_by}"
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by("name")

    # Get total count before pagination
    total = queryset.count()

    # Apply pagination
    paginator = Paginator(queryset, limit)

    try:
        categories_page = paginator.page(page)
    except PageNotAnInteger:
        categories_page = paginator.page(1)
        page = 1
    except EmptyPage:
        categories_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages

    # Calculate pagination metadata
    total_pages = paginator.num_pages
    has_next = categories_page.has_next()
    has_previous = categories_page.has_previous()

    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_page": page + 1 if has_next else None,
        "previous_page": page - 1 if has_previous else None,
        "start_index": (page - 1) * limit + 1 if total > 0 else 0,
        "end_index": min(page * limit, total),
    }

    return list(categories_page), total, pagination_meta


def get_subcategories(
    category_id: str, only_active: bool = True, is_admin: bool = False
) -> List[Category]:
    """Get subcategories - respect hidden flag based on role"""
    category = get_category_by_id(category_id, is_admin=is_admin)
    if not category:
        return []

    queryset = category.children.all()

    if only_active:
        queryset = queryset.filter(is_active=True)

    if not is_admin:
        queryset = queryset.filter(
            is_hidden=False
        )  # Hide hidden subcategories from customers

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
            str(category.id), only_active=True, is_admin=is_admin
        )

    return categories


# ==================== REVIEW SELECTORS ====================


def get_reviews_by_product(
    product_slug: str,
    page: int = 1,
    limit: int = 20,
    rating: int = None,
    verified: bool = None,
    only_approved: bool = True,
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
            "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0},
        }

    distribution = {}
    for i in range(1, 6):
        distribution[i] = reviews.filter(rating=i).count()

    return {
        "average": float(reviews.aggregate(Avg("rating"))["avg"] or 0),
        "total": reviews.count(),
        "distribution": distribution,
    }


# ==================== WISHLIST SELECTORS ====================


def get_wishlist_items(
    user, page: int = 1, limit: int = 20, is_admin: bool = False
) -> Tuple[List[Dict], int]:
    """Get user's wishlist items grouped by product with variants"""

    # Get all wishlist items with eager loading
    wishlist_items = (
        Wishlist.objects.filter(user=user)
        .order_by("-created_at")
        .select_related("variant")
        .prefetch_related(
            "variant__product",
            "variant__product__category",
            "variant__images",
        )
    )

    # Group by product
    products_dict = {}

    for item in wishlist_items:
        variant = item.variant
        product = variant.product
        product_id = str(product.id)

        # Serialize variant using your schema
        variant_data = serialize_variant(variant, is_admin=is_admin)

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
        product_data = serialize_product(group_data["product"], is_admin=is_admin)
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
    paginated_result = result[offset : offset + limit]

    return paginated_result, total


def get_wishlist_items_flat(
    user, page: int = 1, limit: int = 20, is_admin: bool = False
) -> Tuple[List[Dict], int]:
    """Get user's wishlist items as flat list (each variant as separate item)"""

    queryset = (
        Wishlist.objects.filter(user=user)
        .order_by("-created_at")
        .select_related("variant")
        .prefetch_related(
            "variant__product",
            "variant__product__category",
            "variant__images",
        )
    )

    total = queryset.count()

    # Paginate
    offset = (page - 1) * limit
    paginated_items = queryset[offset : offset + limit]

    # Serialize using schema
    from apps.products.schemas import serialize_wishlist_item

    items_data = [
        serialize_wishlist_item(item, is_admin=is_admin) for item in paginated_items
    ]

    return items_data, total


def is_in_wishlist(user, variant_id: str) -> bool:
    """Check if variant is in user's wishlist"""
    return Wishlist.objects.filter(user=user, variant_id=variant_id).exists()
