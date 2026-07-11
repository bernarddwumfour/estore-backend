"""
Variant Selectors - Database read operations for variants
No business logic - just queries
"""

from typing import Optional, List, Dict,  Tuple
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from apps.products.models import ProductVariant, Product


# ==================== VARIANT SELECTORS ====================

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
    except (ProductVariant.DoesNotExist, ValueError, ValidationError):
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