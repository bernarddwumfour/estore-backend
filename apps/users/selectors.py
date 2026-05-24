# apps/users/selectors.py

from typing import List, Dict, Optional, Tuple
from django.db.models import Q, Prefetch
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from apps.users.models.user import User
from apps.users.models.address import Address
from apps.users.models.affiliate import Affiliate
import logging

logger = logging.getLogger(__name__)


def get_users_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    role: str = None,
    is_active: bool = None,
    email_verified: bool = None,
    is_guest: bool = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    include_addresses: bool = False,
) -> Tuple[List[User], int, Dict]:
    """Get filtered and paginated all users"""
    
    queryset = User.objects.all()
    
    # Prefetch addresses if needed
    if include_addresses:
        queryset = queryset.prefetch_related(
            Prefetch('addresses', queryset=Address.objects.filter(is_active=True))
        )
    
    # Filter by role
    if role:
        queryset = queryset.filter(role=role)
    
    # Filter by active status
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    
    # Filter by email verification
    if email_verified is not None:
        queryset = queryset.filter(email_verified=email_verified)
    
    # Filter by guest status - using the is_guest field
    if is_guest is not None:
        queryset = queryset.filter(is_guest=is_guest)
    
    # Search by email, username, phone, first_name, last_name
    if search:
        queryset = queryset.filter(
            Q(email__icontains=search) |
            Q(username__icontains=search) |
            Q(phone__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    
    # Apply sorting
    allowed_sort_fields = ['created_at', 'email', 'role', 'is_active', 'last_login', 'first_name', 'last_name']
    
    if sort_by in allowed_sort_fields:
        if sort_order == "desc":
            sort_by = f"-{sort_by}"
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by("-created_at")
    
    # Get total count before pagination
    total = queryset.count()
    
    # Apply pagination
    paginator = Paginator(queryset, limit)
    
    try:
        users_page = paginator.page(page)
    except PageNotAnInteger:
        users_page = paginator.page(1)
        page = 1
    except EmptyPage:
        users_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    # Calculate pagination metadata
    total_pages = paginator.num_pages
    has_next = users_page.has_next()
    has_previous = users_page.has_previous()
    
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
    
    return list(users_page), total, pagination_meta


def get_customers_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    is_active: bool = None,
    email_verified: bool = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    include_addresses: bool = True,
) -> Tuple[List[User], int, Dict]:
    """Get filtered and paginated customers only (registered users with customer role, not guests)"""
    
    queryset = User.objects.filter(role=User.ROLE_CUSTOMER, is_guest=False)
    
    # Prefetch addresses
    if include_addresses:
        queryset = queryset.prefetch_related(
            Prefetch('addresses', queryset=Address.objects.filter(is_active=True))
        )
    
    # Filter by active status
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    
    # Filter by email verification
    if email_verified is not None:
        queryset = queryset.filter(email_verified=email_verified)
    
    # Search by email, username, phone, first_name, last_name
    if search:
        queryset = queryset.filter(
            Q(email__icontains=search) |
            Q(username__icontains=search) |
            Q(phone__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search)
        )
    
    # Apply sorting
    allowed_sort_fields = ['created_at', 'email', 'is_active', 'last_login', 'first_name', 'last_name']
    
    if sort_by in allowed_sort_fields:
        if sort_order == "desc":
            sort_by = f"-{sort_by}"
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by("-created_at")
    
    total = queryset.count()
    paginator = Paginator(queryset, limit)
    
    try:
        users_page = paginator.page(page)
    except PageNotAnInteger:
        users_page = paginator.page(1)
        page = 1
    except EmptyPage:
        users_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    total_pages = paginator.num_pages
    has_next = users_page.has_next()
    has_previous = users_page.has_previous()
    
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
    
    return list(users_page), total, pagination_meta



def get_staff_users_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    role: str = None,
    is_active: bool = None,
    email_verified: bool = None,
    sort_by: str = "date_joined",
    sort_order: str = "desc",
) -> Tuple[List[User], int, Dict]:
    """Get filtered and paginated staff users (admin and staff roles only, not guests)"""
    
    queryset = User.objects.filter(role__in=['admin', 'staff'], is_guest=False)
    
    # Filter by role
    if role and role in ['admin', 'staff']:
        queryset = queryset.filter(role=role)
    
    # Filter by active status
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    
    # Filter by email verification
    if email_verified is not None:
        queryset = queryset.filter(email_verified=email_verified)
    
    # Search by email, first_name, last_name, phone
    if search:
        queryset = queryset.filter(
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(phone__icontains=search)
        )
    
    # Apply sorting
    allowed_sort_fields = ['date_joined', 'email', 'first_name', 'last_login']
    
    if sort_by in allowed_sort_fields:
        if sort_order == "desc":
            sort_by = f"-{sort_by}"
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by("-date_joined")
    
    total = queryset.count()
    paginator = Paginator(queryset, limit)
    
    try:
        users_page = paginator.page(page)
    except PageNotAnInteger:
        users_page = paginator.page(1)
        page = 1
    except EmptyPage:
        users_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    total_pages = paginator.num_pages
    has_next = users_page.has_next()
    has_previous = users_page.has_previous()
    
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
    
    return list(users_page), total, pagination_meta


def get_guest_users_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    is_active: bool = None,
    email_verified: bool = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    include_addresses: bool = True,
) -> Tuple[List[User], int, Dict]:
    """Get filtered and paginated guest users (is_guest=True)"""
    
    queryset = User.objects.filter(is_guest=True)
    
    # Prefetch addresses
    if include_addresses:
        queryset = queryset.prefetch_related(
            Prefetch('addresses', queryset=Address.objects.filter(is_active=True))
        )
    
    # Filter by active status
    if is_active is not None:
        queryset = queryset.filter(is_active=is_active)
    
    # Filter by email verification
    if email_verified is not None:
        queryset = queryset.filter(email_verified=email_verified)
    
    # Search by email, first_name, last_name, phone
    if search:
        queryset = queryset.filter(
            Q(email__icontains=search) |
            Q(first_name__icontains=search) |
            Q(last_name__icontains=search) |
            Q(phone__icontains=search)
        )
    
    # Apply sorting
    allowed_sort_fields = ['created_at', 'email', 'first_name', 'last_name']
    
    if sort_by in allowed_sort_fields:
        if sort_order == "desc":
            sort_by = f"-{sort_by}"
        queryset = queryset.order_by(sort_by)
    else:
        queryset = queryset.order_by("-created_at")
    
    total = queryset.count()
    paginator = Paginator(queryset, limit)
    
    try:
        users_page = paginator.page(page)
    except PageNotAnInteger:
        users_page = paginator.page(1)
        page = 1
    except EmptyPage:
        users_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages
    
    total_pages = paginator.num_pages
    has_next = users_page.has_next()
    has_previous = users_page.has_previous()
    
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
    
    return list(users_page), total, pagination_meta


def get_affiliates_filtered(
    page: int = 1,
    limit: int = 20,
    search: str = None,
    is_active: bool = None,
    email_verified: bool = None,
    level: str = None,
    min_earnings: float = None,
    max_earnings: float = None,
    sort_by: str = "joined_at",
    sort_order: str = "desc",
    include_addresses: bool = False,
) -> Tuple[List[Affiliate], int, Dict]:
    """Get filtered and paginated affiliate users"""
    
    queryset = Affiliate.objects.select_related('user').prefetch_related('user__addresses')
    
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
    
    # Search by user email, first_name, last_name, phone
    if search:
        queryset = queryset.filter(
            Q(user__email__icontains=search) |
            Q(user__first_name__icontains=search) |
            Q(user__last_name__icontains=search) |
            Q(user__phone__icontains=search)
        )
    
    # Apply sorting
    allowed_sort_fields = ['joined_at', 'total_earnings', 'total_referrals', 'level']
    
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


def get_user_addresses(user_id: str) -> List[Address]:
    """Get all addresses for a user"""
    try:
        return list(Address.objects.filter(user_id=user_id, is_active=True).order_by('-is_default', '-created_at'))
    except Exception as e:
        logger.error(f"Failed to get addresses for user {user_id}: {str(e)}")
        return []


def get_user_default_address(user_id: str, address_type: str = 'shipping') -> Optional[Address]:
    """Get default address for a user by type"""
    try:
        return Address.objects.filter(
            user_id=user_id, 
            address_type=address_type, 
            is_default=True, 
            is_active=True
        ).first()
    except Exception as e:
        logger.error(f"Failed to get default address for user {user_id}: {str(e)}")
        return None


def get_user_statistics() -> Dict[str, int]:
    """Get user statistics counts"""
    from apps.users.models.affiliate import Affiliate
    
    stats = {
        "total_users": User.objects.count(),
        "total_customers": User.objects.filter(role=User.ROLE_CUSTOMER, is_guest=False).count(),
        "total_guests": User.objects.filter(is_guest=True).count(),
        "total_staff": User.objects.filter(role__in=['admin', 'staff'], is_guest=False).count(),
        "total_admins": User.objects.filter(role='admin', is_guest=False).count(),
        "total_affiliates": Affiliate.objects.filter(is_active=True).count(),
        "active_users": User.objects.filter(is_active=True).count(),
        "inactive_users": User.objects.filter(is_active=False).count(),
        "verified_emails": User.objects.filter(email_verified=True).count(),
        "unverified_emails": User.objects.filter(email_verified=False).count(),
    }
    
    return stats


def get_user_by_email(email: str) -> Optional[User]:
    """Get user by email"""
    try:
        return User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return None


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