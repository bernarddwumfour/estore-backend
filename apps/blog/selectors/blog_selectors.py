"""
Blog Selectors — read-only database queries.
No business logic, no mutations.
"""

from typing import Dict, List, Optional, Tuple

from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q

from apps.blog.models import BlogCategory, BlogPost


# ---------------------------------------------------------------------------
# Post selectors
# ---------------------------------------------------------------------------

def get_post_by_slug(slug: str, admin: bool = False) -> Optional[BlogPost]:
    """Get a single post by slug.  Public callers only see published posts."""
    try:
        qs = BlogPost.objects.select_related("category", "author_user").all()
        if not admin:
            qs = qs.filter(status=BlogPost.STATUS_PUBLISHED)
        return qs.get(slug=slug)
    except (BlogPost.DoesNotExist, ValueError, ValidationError):
        return None


def get_post_by_id(post_id: str, admin: bool = False) -> Optional[BlogPost]:
    """Get a single post by id."""
    try:
        qs = BlogPost.objects.select_related("category", "author_user").all()
        if not admin:
            qs = qs.filter(status=BlogPost.STATUS_PUBLISHED)
        return qs.get(id=post_id)
    except (BlogPost.DoesNotExist, ValueError, ValidationError):
        return None


def list_posts(
    *,
    admin: bool = False,
    category_slug: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    is_featured: Optional[bool] = None,
    sort_by: str = "created_at",
    sort_order: str = "desc",
    page: int = 1,
    limit: int = 20,
) -> Tuple[List[BlogPost], int, Dict]:
    """List blog posts with filters and pagination.

    Returns:
        (posts, total, pagination_meta)
    """
    qs = BlogPost.objects.select_related("category", "author_user").all()

    if not admin:
        qs = qs.filter(status=BlogPost.STATUS_PUBLISHED)
    elif status is not None:
        qs = qs.filter(status=status)

    if category_slug:
        qs = qs.filter(category__slug=category_slug)

    if search:
        qs = qs.filter(
            Q(title__icontains=search)
            | Q(excerpt__icontains=search)
            | Q(content__icontains=search)
        )

    if is_featured is not None:
        qs = qs.filter(is_featured=is_featured)

    # Sorting
    allowed_sort_fields = {"title", "created_at", "updated_at", "published_at", "status"}
    if sort_by in allowed_sort_fields:
        order = f"-{sort_by}" if sort_order == "desc" else sort_by
    else:
        order = "-created_at"
    qs = qs.order_by(order)

    total = qs.count()
    paginator = Paginator(qs, limit)

    try:
        posts_page = paginator.page(page)
    except PageNotAnInteger:
        posts_page = paginator.page(1)
        page = 1
    except EmptyPage:
        posts_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages

    total_pages = paginator.num_pages
    has_next = posts_page.has_next()
    has_previous = posts_page.has_previous()

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

    return list(posts_page), total, pagination_meta


# ---------------------------------------------------------------------------
# Category selectors
# ---------------------------------------------------------------------------

def list_categories(active_only: bool = True) -> List[BlogCategory]:
    """List blog categories, optionally filtered to active only."""
    qs = BlogCategory.objects.all()
    if active_only:
        qs = qs.filter(is_active=True)
    return list(qs.order_by("name"))


def get_category_by_id(category_id: str) -> Optional[BlogCategory]:
    """Get a category by id."""
    try:
        return BlogCategory.objects.get(id=category_id)
    except (BlogCategory.DoesNotExist, ValueError, ValidationError):
        return None


def get_category_by_slug(slug: str) -> Optional[BlogCategory]:
    """Get a category by slug."""
    try:
        return BlogCategory.objects.get(slug=slug)
    except BlogCategory.DoesNotExist:
        return None
