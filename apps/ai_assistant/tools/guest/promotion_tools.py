"""Read-only tools for currently public promotions."""

import json

from django.db.models import Q
from django.utils import timezone
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.promotions.models import Promotion
from apps.promotions.selectors import get_promotion_by_slug


class PromotionSearchInput(BaseModel):
    search: str | None = Field(default=None, max_length=150)
    limit: int = Field(default=5, ge=1, le=10)


def _serialize_public_promotion(promotion: Promotion) -> dict:
    images = []
    for image in promotion.images.filter(is_active=True).order_by("order"):
        try:
            images.append({"url": image.image.url, "alt_text": image.alt_text or promotion.name})
        except ValueError:
            continue

    items = []
    for item in promotion.items.select_related("variant__product").prefetch_related("variant__images"):
        variant_image = next(
            (image for image in item.variant.images.all() if image.is_active and image.image),
            None,
        )
        try:
            image_url = variant_image.image.url if variant_image else None
        except ValueError:
            image_url = None
        items.append({
            "product_title": item.variant.product.title,
            "product_slug": item.variant.product.slug,
            "quantity": item.quantity,
            "is_free": item.is_free,
            "attributes": item.variant.attributes or {},
            "image_url": image_url,
        })

    original_total = promotion.original_total
    savings_amount = promotion.savings_amount
    return {
        "slug": promotion.slug,
        "name": promotion.name,
        "description": promotion.description,
        "bundle_price": float(promotion.bundle_price),
        "original_total": original_total,
        "savings_amount": savings_amount,
        "savings_percentage": round(savings_amount / original_total * 100, 2) if original_total else 0,
        "starts_at": promotion.starts_at.isoformat() if promotion.starts_at else None,
        "ends_at": promotion.ends_at.isoformat() if promotion.ends_at else None,
        "images": images,
        "items": items,
        "has_stock": promotion.has_stock,
    }


@tool(args_schema=PromotionSearchInput)
def search_active_promotions(search: str | None = None, limit: int = 5) -> str:
    """Search current public promotions and bundle offers available to shoppers."""
    now = timezone.now()
    promotions = Promotion.objects.filter(
        status=Promotion.STATUS_ACTIVE,
        starts_at__lte=now,
    ).filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))
    if search and search.strip():
        promotions = promotions.filter(
            Q(name__icontains=search.strip())
            | Q(description__icontains=search.strip())
            | Q(items__variant__product__title__icontains=search.strip())
        ).distinct()
    rows = list(promotions.prefetch_related("images", "items__variant__product", "items__variant__images").order_by("-created_at")[:limit])
    return json.dumps({
        "success": True,
        "promotions": [_serialize_public_promotion(promotion) for promotion in rows],
        "total": len(rows),
    }, ensure_ascii=False)


class PromotionDetailsInput(BaseModel):
    slug: str = Field(min_length=1, max_length=200, description="Exact slug from search_active_promotions")


@tool(args_schema=PromotionDetailsInput)
def get_public_promotion_details(slug: str) -> str:
    """Get details for one active public promotion using its exact verified slug."""
    promotion = get_promotion_by_slug(slug.strip(), is_admin=False)
    if not promotion:
        return json.dumps({"success": False, "error": "Promotion not found or no longer available."})
    return json.dumps({
        "success": True,
        "promotion": _serialize_public_promotion(promotion),
    }, ensure_ascii=False)
