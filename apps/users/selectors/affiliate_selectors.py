"""
Affiliate Selectors - Database read operations for affiliates
No business logic - just queries
"""

from typing import List, Dict, Optional, Tuple
from django.db.models import Q, Count, Sum, DecimalField
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from apps.users.models.affiliate import Affiliate
import logging

logger = logging.getLogger(__name__)


def get_affiliates_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    is_active: bool = None,
    email_verified: bool = None,
    level: str = None,
    min_earnings: float = None,
    max_earnings: float = None,
    min_referrals: int = None,
    sort_by: str = "joined_at",
    sort_order: str = "desc",
    include_addresses: bool = False,
) -> Tuple[List[Affiliate], int, Dict]:
    """Get filtered and paginated affiliate users"""
    
    queryset = Affiliate.objects.select_related('user').prefetch_related('user__addresses').annotate(
        attributed_orders_count=Count('attributed_orders', distinct=True),
        attributed_sales_total=Coalesce(
            Sum('attributed_orders__total', output_field=DecimalField(max_digits=12, decimal_places=2)),
            0,
            output_field=DecimalField(max_digits=12, decimal_places=2),
        ),
        pending_commissions_count=Count('commissions', filter=Q(commissions__status='pending'), distinct=True),
        accrued_commissions_count=Count('commissions', filter=Q(commissions__status='accrued'), distinct=True),
        reversed_commissions_count=Count('commissions', filter=Q(commissions__status='reversed'), distinct=True),
    )
    
    # Filter by affiliate active status
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    
    # Filter by affiliate level
    if level:
        queryset = queryset.filter(level=level)
    
    # Filter by user active status
    queryset = queryset.filter(user__is_active=True)
    
    # Filter by email verification
    if email_verified is not None:
        queryset = queryset.filter(user__email_verified=email_verified)
    
    # Filter by earnings range
    if min_earnings is not None:
        queryset = queryset.filter(total_earnings__gte=min_earnings)
    if max_earnings is not None:
        queryset = queryset.filter(total_earnings__lte=max_earnings)
    if min_referrals is not None:
        queryset = queryset.filter(total_referrals__gte=min_referrals)
    
    # Search by user email, first_name, last_name, phone
    if search:
        queryset = queryset.filter(
            Q(user__email__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__phone__icontains=search)
        )
    
    # Apply sorting
    allowed_sort_fields = ['joined_at', 'total_earnings', 'total_referrals', 'level', 'attributed_orders_count', 'attributed_sales_total']
    
    if sort_by in allowed_sort_fields:
        if sort_order == "desc":
            sort_by = f"-{sort_by}"
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by("-total_earnings")
    
    total = queryset.count()
    paginator = Paginator(queryset, limit)
    
    try:
        affiliates_page = paginator.page(page)
    except PageNotAnInteger:
        affiliates_page = paginator.page(1)
        page = 1
    except EmptyPage:
        affiliates_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    total_pages = paginator.num_pages
    has_next = affiliates_page.has_next()
    has_previous = affiliates_page.has_previous()
    
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
    
    return list(affiliates_page), total, pagination_meta


def get_affiliate_by_user(user_id: str) -> Optional[Affiliate]:
    """Get affiliate profile for a user"""
    try:
        return Affiliate.objects.select_related('user').get(user_id=user_id)
    except Affiliate.DoesNotExist:
        return None


def get_affiliate_by_referral_code(referral_code: str) -> Optional[Affiliate]:
    """Get affiliate by referral code"""
    try:
        return Affiliate.objects.select_related('user').get(referral_code=referral_code, is_active=True)
    except Affiliate.DoesNotExist:
        return None
