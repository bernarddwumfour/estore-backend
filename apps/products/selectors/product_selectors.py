"""
Product Selectors - Database read operations for products
No business logic - just queries
"""

from typing import Optional, List, Dict, Tuple
from django.db.models import (
    Q, Min, Max, Sum, OuterRef, Subquery, Case, When,
    Value, BooleanField, Exists, DecimalField, IntegerField
)
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models.functions import Coalesce
from apps.products.models import Product, Category, ProductVariant


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
    """Get filtered and paginated products for admin - OPTIMIZED"""
    
    # Start with base queryset with annotations for filtering
    queryset = Product.objects.select_related("category").prefetch_related("variants")
    
    # Annotate with aggregated values from variants
    variant_subquery = ProductVariant.objects.filter(product=OuterRef('pk'))
    
    queryset = queryset.annotate(
        db_min_price=Coalesce(
            Subquery(
                variant_subquery.values('product_id')
                .annotate(min_price=Min('price'))
                .values('min_price')[:1]
            ),
            Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
        ),
        db_max_price=Coalesce(
            Subquery(
                variant_subquery.values('product_id')
                .annotate(max_price=Max('price'))
                .values('max_price')[:1]
            ),
            Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
        ),
        db_total_stock=Coalesce(
            Subquery(
                variant_subquery.values('product_id')
                .annotate(total=Sum('stock'))
                .values('total')[:1]
            ),
            Value(0, output_field=IntegerField())
        ),
        db_has_stock=Case(
            When(
                Exists(variant_subquery.filter(stock__gt=0)),
                then=Value(True)
            ),
            default=Value(False),
            output_field=BooleanField()
        )
    )
    
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
    
    # Filter using annotations
    if has_stock is not None:
        queryset = queryset.filter(db_has_stock=has_stock)
    
    if min_price is not None:
        queryset = queryset.filter(db_min_price__gte=min_price)
    if max_price is not None:
        queryset = queryset.filter(db_max_price__lte=max_price)
    
    # Apply sorting using annotations
    sort_mapping = {
        "title": "title",
        "min_price": "db_min_price",
        "max_price": "db_max_price",
        "total_stock": "db_total_stock",
        "status": "status",
        "created_at": "created_at",
    }
    
    sort_field = sort_mapping.get(sort_by, "created_at")
    if sort_order == "desc":
        sort_field = f"-{sort_field}"
    
    queryset = queryset.order_by(sort_field)
    
    # Get total count
    total = queryset.count()
    
    # Apply pagination using Django's Paginator (doesn't load all into memory)
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
    """Get filtered and paginated products for customers - OPTIMIZED"""
    
    queryset = Product.objects.select_related("category").prefetch_related("variants")
    
    # Annotate with aggregated values for filtering
    variant_subquery = ProductVariant.objects.filter(product=OuterRef('pk'))
    
    queryset = queryset.annotate(
        db_min_price=Coalesce(
            Subquery(
                variant_subquery.values('product_id')
                .annotate(min_price=Min('price'))
                .values('min_price')[:1]
            ),
            Value(0, output_field=DecimalField(max_digits=10, decimal_places=2))
        ),
        db_total_stock=Coalesce(
            Subquery(
                variant_subquery.values('product_id')
                .annotate(total=Sum('stock'))
                .values('total')[:1]
            ),
            Value(0, output_field=IntegerField())
        ),
        db_has_stock=Case(
            When(
                Exists(variant_subquery.filter(stock__gt=0)),
                then=Value(True)
            ),
            default=Value(False),
            output_field=BooleanField()
        )
    )
    
    # Filter by status - only published for customers
    if not include_drafts:
        queryset = queryset.filter(status=Product.STATUS_PUBLISHED)
    
    # Filter by category slug and respect hidden categories
    if category_slug:
        try:
            category = Category.objects.get(slug=category_slug, is_active=True)
            
            if not is_admin and category.is_hidden:
                return [], 0, {}
            
            descendant_categories = category.get_all_descendants()
            
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
    
    # Filter using annotations
    if min_price is not None:
        queryset = queryset.filter(db_min_price__gte=min_price)
    if max_price is not None:
        queryset = queryset.filter(db_min_price__lte=max_price)
    
    if in_stock is not None:
        queryset = queryset.filter(db_has_stock=in_stock)
    else:
        # Store-wide toggle: hide out-of-stock products from public listings
        # unless the client explicitly filtered on stock
        try:
            from apps.common.models import GeneralConfig
            if GeneralConfig.get_cached().hide_out_of_stock:
                queryset = queryset.filter(db_has_stock=True)
        except Exception:
            pass

    # Filter by flags
    if featured is not None:
        queryset = queryset.filter(is_featured=featured)
    if bestseller is not None:
        queryset = queryset.filter(is_bestseller=bestseller)
    if new is not None:
        queryset = queryset.filter(is_new=new)
    
    # Search
    if search:
        # Cap search length
        search = search[:200]
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(slug__icontains=search)
        )
    
    # Apply sorting using annotations
    sort_mapping = {
        "price_asc": "db_min_price",
        "price_desc": "-db_min_price",
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