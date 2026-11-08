"""Admin marketing reads and confirmed campaign-management actions."""

import json
import re
from datetime import datetime
from typing import Literal

from django.contrib.auth import get_user_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.ai_assistant.services.admin_marketing_action_service import AdminMarketingActionService
from apps.blog.models import BlogPost
from apps.blog.schemas import serialize_post
from apps.blog.selectors import list_posts
from apps.products.services.review_service import AdminReviewService
from apps.promotions.schemas import serialize_promotion
from apps.promotions.selectors import get_admin_discount_codes, get_admin_promotions

User = get_user_model()
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\w)(?:\+?\d[\d ().-]{7,}\d)(?!\w)")


def _admin(config):
    user_id = (config.get("configurable") or {}).get("authenticated_user_id")
    return User.objects.filter(pk=user_id, is_active=True,
                               role__in=[User.ROLE_ADMIN, User.ROLE_STAFF]).first() if user_id else None


def _reply(config, data=None, error=None):
    if not _admin(config or {}):
        return json.dumps({"success": False, "error": "Admin access required."})
    return json.dumps({"success": error is None, "data": data, "error": error}, default=str)


class MarketingSearchInput(BaseModel):
    search: str | None = Field(default=None, max_length=150)
    status: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=20)


@tool(args_schema=MarketingSearchInput)
def search_admin_promotions(search: str | None = None, status: str | None = None,
                            page: int = 1, limit: int = 10,
                            config: RunnableConfig = None) -> str:
    """Search marketing bundle promotions by name and status; admin/staff only."""
    if not _admin(config or {}):
        return _reply(config)
    if status and status not in {"draft", "active", "paused", "ended"}:
        return _reply(config, error="Invalid promotion status.")
    promotions, total, pagination = get_admin_promotions(
        page=page, limit=limit, status=status, search=search,
    )
    results = []
    for promotion in promotions:
        item = serialize_promotion(promotion, is_admin=True)
        results.append({key: item.get(key) for key in (
            "id", "name", "slug", "description", "bundle_price", "original_total",
            "savings_amount", "savings_percentage", "starts_at", "ends_at", "items",
            "free_items", "images", "has_stock", "status",
        )})
    return _reply(config, {"promotions": results, "total": total, "pagination": pagination})


class DiscountCodeSearchInput(BaseModel):
    search: str | None = Field(default=None, max_length=150)
    is_active: bool | None = None
    affiliate_only: bool | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=20)


@tool(args_schema=DiscountCodeSearchInput)
def search_admin_discount_codes(search: str | None = None, is_active: bool | None = None,
                                affiliate_only: bool | None = None, page: int = 1,
                                limit: int = 10, config: RunnableConfig = None) -> str:
    """Search checkout discount codes and their rules without exposing affiliate contact details."""
    if not _admin(config or {}):
        return _reply(config)
    codes, total, pagination = get_admin_discount_codes(
        page=page, limit=limit, search=search, is_active=is_active,
        affiliate_only=affiliate_only,
    )
    results = [{
        "id": str(code.id), "code": code.code, "name": code.name,
        "discount_type": code.discount_type, "value": float(code.value),
        "min_subtotal": float(code.min_subtotal),
        "max_discount_amount": float(code.max_discount_amount) if code.max_discount_amount is not None else None,
        "is_active": code.is_active, "is_currently_active": code.is_currently_active,
        "starts_at": code.starts_at.isoformat() if code.starts_at else None,
        "ends_at": code.ends_at.isoformat() if code.ends_at else None,
        "is_affiliate_code": bool(code.affiliate_id),
    } for code in codes]
    return _reply(config, {"discount_codes": results, "total": total, "pagination": pagination})


class BlogSearchInput(BaseModel):
    search: str | None = Field(default=None, max_length=150)
    status: str | None = None
    is_featured: bool | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=20)


@tool(args_schema=BlogSearchInput)
def search_admin_blog_posts(search: str | None = None, status: str | None = None,
                            is_featured: bool | None = None, page: int = 1,
                            limit: int = 10, config: RunnableConfig = None) -> str:
    """Search blog posts by title, status, or featured state. Returns summaries, not full article content."""
    if not _admin(config or {}):
        return _reply(config)
    if status and status not in dict(BlogPost.STATUS_CHOICES):
        return _reply(config, error="Invalid blog post status.")
    posts, total, pagination = list_posts(
        admin=True, search=search, status=status, is_featured=is_featured,
        page=page, limit=limit,
    )
    results = []
    for post in posts:
        item = serialize_post(post, is_admin=True)
        results.append({key: item.get(key) for key in (
            "id", "title", "slug", "excerpt", "cover_image_url", "category",
            "is_featured", "published_at", "status",
        )})
    return _reply(config, {"posts": results, "total": total, "pagination": pagination})


class ReviewSearchInput(BaseModel):
    review_type: Literal["all", "product", "order"] = "all"
    status: Literal["pending", "approved"] | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    search: str | None = Field(default=None, max_length=150)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=20)


@tool(args_schema=ReviewSearchInput)
def search_admin_reviews(review_type: str = "all", status: str | None = None,
                         rating: int | None = None, search: str | None = None,
                         page: int = 1, limit: int = 10,
                         config: RunnableConfig = None) -> str:
    """Search product and order reviews for moderation; reviewer contact details are removed."""
    if not _admin(config or {}):
        return _reply(config)
    reviews, total, pagination = AdminReviewService.get_all_reviews(
        review_type=review_type, status=status, rating=rating,
        search=search, page=page, limit=limit,
    )
    results = []
    for review in reviews:
        preview = EMAIL_RE.sub("[email removed]", review.get("comment_preview", ""))
        preview = PHONE_RE.sub("[phone removed]", preview)
        results.append({key: value for key, value in review.items()
                        if key not in {"user_email", "user_id"} and key != "comment_preview"}
                       | {"comment_preview": preview})
    return _reply(config, {"reviews": results, "total": total, "pagination": pagination})


class MarketingActionInput(BaseModel):
    entity: Literal["promotion", "discount_code", "blog_post", "review"]
    action: str
    ids: list[str] = Field(min_length=1, max_length=20)
    review_type: Literal["product", "order"] | None = None


@tool(args_schema=MarketingActionInput)
def prepare_admin_marketing_action(entity: str, action: str, ids: list[str],
                                   review_type: str | None = None,
                                   config: RunnableConfig = None) -> str:
    """Prepare a marketing status or moderation change. A staff member must confirm it separately."""
    admin = _admin(config or {})
    if not admin:
        return _reply(config)
    pending, errors = AdminMarketingActionService.prepare(
        admin, entity=entity, action=action, ids=ids, review_type=review_type,
    )
    return json.dumps({"success": errors is None, "pending_action": pending, "errors": errors}, default=str)


class PromotionItemInput(BaseModel):
    variant_id: str
    quantity: int = Field(default=1, ge=1)
    is_free: bool = False


class CreatePromotionInput(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    bundle_price: float = Field(ge=0)
    starts_at: datetime
    ends_at: datetime | None = None
    items: list[PromotionItemInput] = Field(min_length=1, max_length=20)
    meta_title: str = ""
    meta_description: str = ""


@tool(args_schema=CreatePromotionInput)
def prepare_admin_promotion_create(name: str, bundle_price: float, starts_at: datetime,
                                   items: list[dict], description: str = "",
                                   ends_at: datetime | None = None, meta_title: str = "",
                                   meta_description: str = "",
                                   config: RunnableConfig = None) -> str:
    """Prepare a bundle promotion from existing variant IDs; it is created only after confirmation."""
    admin = _admin(config or {})
    if not admin:
        return _reply(config)
    pending, errors = AdminMarketingActionService.prepare(
        admin, entity="promotion", action="create", data={
            "name": name, "bundle_price": bundle_price, "starts_at": starts_at,
            "ends_at": ends_at, "items": items, "description": description,
            "meta_title": meta_title, "meta_description": meta_description,
        },
    )
    return json.dumps({"success": errors is None, "pending_action": pending, "errors": errors}, default=str)


class CreateDiscountCodeInput(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=120)
    discount_type: Literal["percentage", "fixed"]
    value: float = Field(gt=0)
    description: str = ""
    min_subtotal: float = Field(default=0, ge=0)
    max_discount_amount: float | None = Field(default=None, ge=0)
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    is_active: bool = True


@tool(args_schema=CreateDiscountCodeInput)
def prepare_admin_discount_code_create(code: str, name: str, discount_type: str,
                                       value: float, description: str = "",
                                       min_subtotal: float = 0,
                                       max_discount_amount: float | None = None,
                                       starts_at: datetime | None = None,
                                       ends_at: datetime | None = None,
                                       is_active: bool = True,
                                       config: RunnableConfig = None) -> str:
    """Prepare a checkout discount code; the code is created only after confirmation."""
    admin = _admin(config or {})
    if not admin:
        return _reply(config)
    pending, errors = AdminMarketingActionService.prepare(
        admin, entity="discount_code", action="create", data={
            "code": code, "name": name, "discount_type": discount_type, "value": value,
            "description": description, "min_subtotal": min_subtotal,
            "max_discount_amount": max_discount_amount, "starts_at": starts_at,
            "ends_at": ends_at, "is_active": is_active,
        },
    )
    return json.dumps({"success": errors is None, "pending_action": pending, "errors": errors}, default=str)


class CreateBlogPostInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=30000, description="Plain text article body; line breaks become paragraphs, do not include HTML")
    excerpt: str = Field(default="", max_length=300)
    category_id: str | None = None
    cover_image_url: str = Field(default="", max_length=500)
    author_name: str = Field(default="Store Team", max_length=120)
    status: Literal["draft", "published", "archived"] = "draft"
    is_featured: bool = False
    meta_title: str = Field(default="", max_length=200)
    meta_description: str = Field(default="", max_length=500)


@tool(args_schema=CreateBlogPostInput)
def prepare_admin_blog_post_create(title: str, content: str, excerpt: str = "",
                                   category_id: str | None = None,
                                   cover_image_url: str = "", author_name: str = "Store Team",
                                   status: str = "draft", is_featured: bool = False,
                                   meta_title: str = "", meta_description: str = "",
                                   config: RunnableConfig = None) -> str:
    """Prepare a blog post; it is published or saved as a draft only after confirmation."""
    admin = _admin(config or {})
    if not admin:
        return _reply(config)
    pending, errors = AdminMarketingActionService.prepare(
        admin, entity="blog_post", action="create", data={
            "title": title, "content": content, "excerpt": excerpt,
            "category_id": category_id, "cover_image_url": cover_image_url,
            "author_name": author_name, "status": status, "is_featured": is_featured,
            "meta_title": meta_title, "meta_description": meta_description,
        },
    )
    return json.dumps({"success": errors is None, "pending_action": pending, "errors": errors}, default=str)
