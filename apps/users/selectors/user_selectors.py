"""
User Selectors - Database read operations for users
No business logic - just queries
"""

from typing import List, Dict, Optional, Tuple
from django.db.models import Q, Prefetch
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from apps.users.models.user import User
from apps.users.models.address import Address
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


def get_user_by_email(email: str) -> Optional[User]:
    """Get user by email"""
    try:
        return User.objects.get(email__iexact=email)
    except User.DoesNotExist:
        return None