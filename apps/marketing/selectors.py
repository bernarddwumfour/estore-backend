"""
Marketing selectors — read-only queries for campaigns and audience segments.
"""

from typing import Dict, List, Optional, Tuple

from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q, QuerySet

from apps.marketing.models import EmailCampaign
from apps.users.models import User


def get_admin_campaigns(
    page: int = 1,
    limit: int = 20,
    status: str = None,
    campaign_type: str = None,
    search: str = None,
) -> Tuple[List[EmailCampaign], int, Dict]:
    queryset = EmailCampaign.objects.select_related("created_by")

    if status:
        queryset = queryset.filter(status=status)
    if campaign_type:
        queryset = queryset.filter(campaign_type=campaign_type)
    if search:
        queryset = queryset.filter(
            Q(name__icontains=search) | Q(subject__icontains=search)
        )

    queryset = queryset.order_by("-created_at")

    total = queryset.count()
    paginator = Paginator(queryset, limit)
    try:
        campaigns_page = paginator.page(page)
    except PageNotAnInteger:
        campaigns_page = paginator.page(1)
        page = 1
    except EmptyPage:
        campaigns_page = paginator.page(paginator.num_pages)
        page = paginator.num_pages

    pagination_meta = {
        "current_page": page,
        "per_page": limit,
        "total": total,
        "total_pages": paginator.num_pages,
        "has_next": campaigns_page.has_next(),
        "has_previous": campaigns_page.has_previous(),
        "next_page": page + 1 if campaigns_page.has_next() else None,
        "previous_page": page - 1 if campaigns_page.has_previous() else None,
    }

    return list(campaigns_page), total, pagination_meta


def get_campaign_by_id(campaign_id: str) -> Optional[EmailCampaign]:
    try:
        return EmailCampaign.objects.select_related("created_by").get(id=campaign_id)
    except (EmailCampaign.DoesNotExist, ValueError):
        return None


def get_segment_queryset(segment: str, campaign_type: str = None) -> QuerySet:
    """
    Single source of truth for campaign audiences.

    Base audience is active, non-guest users with an email address. Promotion
    campaigns additionally exclude anyone who opted out of marketing email,
    regardless of segment.
    """
    queryset = User.objects.filter(is_active=True, is_guest=False).exclude(email="")

    if segment == EmailCampaign.SEGMENT_CUSTOMERS:
        queryset = queryset.filter(role=User.ROLE_CUSTOMER)
    elif segment == EmailCampaign.SEGMENT_VERIFIED_CUSTOMERS:
        queryset = queryset.filter(role=User.ROLE_CUSTOMER, email_verified=True)
    elif segment == EmailCampaign.SEGMENT_AFFILIATES:
        queryset = queryset.filter(affiliate_profile__isnull=False)
    elif segment == EmailCampaign.SEGMENT_NEWSLETTER_SUBSCRIBERS:
        queryset = queryset.filter(customer_profile__receive_newsletter=True)
    elif segment == EmailCampaign.SEGMENT_MARKETING_OPTIN:
        queryset = queryset.filter(customer_profile__receive_marketing=True)
    # SEGMENT_ALL_USERS: no extra filter

    if campaign_type == EmailCampaign.TYPE_PROMOTION:
        queryset = queryset.exclude(customer_profile__receive_marketing=False)

    return queryset.distinct()


def get_segment_counts(campaign_type: str = None) -> Dict[str, int]:
    """Live recipient counts per segment for the UI picker."""
    return {
        segment: get_segment_queryset(segment, campaign_type).count()
        for segment, _label in EmailCampaign.SEGMENT_CHOICES
    }
