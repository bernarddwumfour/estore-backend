"""
Product Selectors - Database read operations for products
No business logic - just queries
"""

from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from apps.products.models import Product, Category
from ..schemas import serialize_product


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