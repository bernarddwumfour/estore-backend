"""
Social selectors — read queries for social posts.
"""

from datetime import date
from typing import Dict, Optional, Tuple

from django.core.paginator import Paginator
from django.db.models import Q

from apps.social.models import SocialPost

VALID_STATUSES = {choice for choice, _ in SocialPost.STATUS_CHOICES}
VALID_SOURCES = {choice for choice, _ in SocialPost.SOURCE_CHOICES}


def _parse_date(value: Optional[str]):
    """Parse YYYY-MM-DD, returning None for missing or malformed values."""
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def get_social_post_by_id(post_id) -> Optional[SocialPost]:
    return (
        SocialPost.objects.select_related("created_by", "reviewed_by")
        .filter(id=post_id)
        .first()
    )


def get_admin_social_posts(
    page: int = 1,
    limit: int = 20,
    status: Optional[str] = None,
    source: Optional[str] = None,
    search: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> Tuple[list, int, Dict]:
    queryset = SocialPost.objects.select_related("created_by", "reviewed_by")

    if status in VALID_STATUSES:
        queryset = queryset.filter(status=status)
    if source in VALID_SOURCES:
        queryset = queryset.filter(source=source)
    if search:
        queryset = queryset.filter(Q(caption__icontains=search))
    date_from = _parse_date(date_from)
    date_to = _parse_date(date_to)
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)

    paginator = Paginator(queryset, limit)
    page_obj = paginator.get_page(page)

    pagination_meta = {
        "current_page": page_obj.number,
        "per_page": limit,
        "total": paginator.count,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "next_page": page_obj.number + 1 if page_obj.has_next() else None,
        "previous_page": page_obj.number - 1 if page_obj.has_previous() else None,
    }
    return list(page_obj.object_list), paginator.count, pagination_meta


def pending_or_sent_post_exists(source: str, object_id) -> bool:
    """Idempotency guard for auto-queued posts."""
    return SocialPost.objects.filter(
        source=source,
        object_id=object_id,
        status__in=[SocialPost.STATUS_PENDING_APPROVAL, SocialPost.STATUS_SENT],
    ).exists()


def get_media_library(
    page: int = 1,
    limit: int = 24,
    media_type: Optional[str] = None,
    search: Optional[str] = None,
) -> Tuple[list, int, Dict]:
    from apps.social.models import SocialMedia

    queryset = SocialMedia.objects.select_related("uploaded_by")
    if media_type in (SocialMedia.TYPE_IMAGE, SocialMedia.TYPE_VIDEO):
        queryset = queryset.filter(media_type=media_type)
    if search:
        queryset = queryset.filter(name__icontains=search)

    paginator = Paginator(queryset, limit)
    page_obj = paginator.get_page(page)

    pagination_meta = {
        "current_page": page_obj.number,
        "per_page": limit,
        "total": paginator.count,
        "total_pages": paginator.num_pages,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "next_page": page_obj.number + 1 if page_obj.has_next() else None,
        "previous_page": page_obj.number - 1 if page_obj.has_previous() else None,
    }
    return list(page_obj.object_list), paginator.count, pagination_meta
