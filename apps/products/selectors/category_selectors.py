"""
Category Selectors - Database read operations for categories
No business logic - just queries
"""

from typing import Optional, List, Dict, Any, Tuple
from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from apps.products.models import Category


# ==================== CATEGORY SELECTORS ====================

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