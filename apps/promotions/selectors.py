"""
Promotion Selectors - Database read operations for promotions
No business logic - just queries
"""

from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q, Count, Sum
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.utils import timezone
from apps.promotions.models import Promotion, PromotionItem, PromotionImage


def get_active_promotions(
    page: int = 1,
    limit: int = 20,
) -> Tuple[List[Promotion], int, Dict]:
    """Get active promotions for customers"""
    now = timezone.now()
    
    queryset = Promotion.objects.filter(
        status=Promotion.STATUS_ACTIVE,
        # starts_at__lte=now,
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gte=now)
    ).prefetch_related(
        'items',
        'items__variant',
        'items__variant__product',
        'items__variant__images',
        'images',
    ).order_by('-created_at')
    
    total = queryset.count()
    
    paginator = Paginator(queryset, limit)
    
    try:
        promotions_page = paginator.page(page)
    except PageNotAnInteger:
        promotions_page = paginator.page(1)
        page = 1
    except EmptyPage:
        promotions_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    total_pages = paginator.num_pages
    has_next = promotions_page.has_next()
    has_previous = promotions_page.has_previous()
    
    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_page": page + 1 if has_next else None,
        "previous_page": page - 1 if has_previous else None,
    }
    
    return list(promotions_page), total, pagination_meta


def get_promotion_by_slug(
    slug: str,
    is_admin: bool = False
) -> Optional[Promotion]:
    """Get promotion by slug"""
    try:
        queryset = Promotion.objects.prefetch_related(
            'items',
            'items__variant',
            'items__variant__product',
            'items__variant__images',
            'images',
        )
        
        if not is_admin:
            now = timezone.now()
            queryset = queryset.filter(
                status=Promotion.STATUS_ACTIVE,
                starts_at__lte=now,
            ).filter(
                Q(ends_at__isnull=True) | Q(ends_at__gte=now)
            )
        
        return queryset.get(slug=slug)
    except Promotion.DoesNotExist:
        return None


def get_admin_promotions(
    page: int = 1,
    limit: int = 20,
    status: str = None,
    search: str = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
) -> Tuple[List[Promotion], int, Dict]:
    """Get all promotions for admin with filters"""
    queryset = Promotion.objects.select_related('created_by').prefetch_related(
        'items',
        'items__variant',
        'items__variant__product',
        'images',
    )
    
    if status:
        queryset = queryset.filter(status=status)
    
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) |
            Q(slug__icontains=search) |
            Q(description__icontains=search)
        )
    
    # Apply sorting
    sort_mapping = {
        "name": "name",
        "status": "status",
        "bundle_price": "bundle_price",
        "starts_at": "starts_at",
        "created_at": "created_at",
    }
    
    sort_field = sort_mapping.get(sort_by, "-created_at")
    if sort_order == "desc" and not sort_field.startswith("-"):
        sort_field = f"-{sort_field}"
    elif sort_order == "asc" and sort_field.startswith("-"):
        sort_field = sort_field[1:]
    
    queryset = queryset.order_by(sort_field)
    
    total = queryset.count()
    
    paginator = Paginator(queryset, limit)
    
    try:
        promotions_page = paginator.page(page)
    except PageNotAnInteger:
        promotions_page = paginator.page(1)
        page = 1
    except EmptyPage:
        promotions_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    total_pages = paginator.num_pages
    has_next = promotions_page.has_next()
    has_previous = promotions_page.has_previous()
    
    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": total_pages,
        "has_next": has_next,
        "has_previous": has_previous,
        "next_page": page + 1 if has_next else None,
        "previous_page": page - 1 if has_previous else None,
    }
    
    return list(promotions_page), total, pagination_meta


def get_promotions_containing_variant(variant_id: str) -> List[Promotion]:
    """Get active promotions that contain a specific variant"""
    now = timezone.now()
    
    return list(Promotion.objects.filter(
        status=Promotion.STATUS_ACTIVE,
        starts_at__lte=now,
        items__variant_id=variant_id,
        items__is_available=True,
    ).filter(
        Q(ends_at__isnull=True) | Q(ends_at__gte=now)
    ).distinct())


def get_promotion_item_by_variant(promotion_id: str, variant_id: str) -> Optional[PromotionItem]:
    """Get a specific promotion item by promotion and variant"""
    try:
        return PromotionItem.objects.get(promotion_id=promotion_id, variant_id=variant_id)
    except PromotionItem.DoesNotExist:
        return None