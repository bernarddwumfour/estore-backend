"""Read and prepare social post actions for the admin assistant."""

import json
from datetime import datetime

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.ai_assistant.services.admin_social_post_action_service import AdminSocialPostActionService
from apps.social.models import SocialPost
from apps.social.schemas import serialize_social_post
from apps.social.selectors import get_admin_social_posts, get_social_post_by_id
from apps.social.services import SocialPostService
from apps.social.zernio_service import ZernioService

User = get_user_model()


def _admin(config):
    user_id = (config.get("configurable") or {}).get("authenticated_user_id")
    return User.objects.filter(
        pk=user_id, is_active=True, role__in=[User.ROLE_ADMIN, User.ROLE_STAFF],
    ).first() if user_id else None


def _reply(config, data=None, error=None):
    if not _admin(config or {}):
        return json.dumps({"success": False, "error": "Admin access required."})
    return json.dumps({"success": error is None, "data": data, "error": error}, default=str)


def _find_post(post_id):
    try:
        return get_social_post_by_id(post_id)
    except (ValidationError, ValueError, TypeError):
        return None


class SocialPostSearchInput(BaseModel):
    search: str | None = Field(default=None, max_length=150)
    status: str | None = None
    source: str | None = None
    date_from: str | None = None
    date_to: str | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=20)


@tool(args_schema=SocialPostSearchInput)
def search_admin_social_posts(search: str | None = None, status: str | None = None,
                              source: str | None = None, date_from: str | None = None,
                              date_to: str | None = None, page: int = 1, limit: int = 10,
                              config: RunnableConfig = None) -> str:
    """Search social posts by caption, status, source, or creation date."""
    if not _admin(config or {}):
        return _reply(config)
    statuses = {choice for choice, _ in SocialPost.STATUS_CHOICES}
    sources = {choice for choice, _ in SocialPost.SOURCE_CHOICES}
    if status and status not in statuses:
        return _reply(config, error="Invalid social post status.")
    if source and source not in sources:
        return _reply(config, error="Invalid social post source.")
    for value, name in ((date_from, "date_from"), (date_to, "date_to")):
        if value:
            try:
                datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                return _reply(config, error=f"{name} must use YYYY-MM-DD format.")
    posts, total, pagination = get_admin_social_posts(
        page=page, limit=limit, status=status, source=source, search=search,
        date_from=date_from, date_to=date_to,
    )
    results = []
    for post in posts:
        results.append({
            "id": str(post.pk), "caption": post.caption[:180], "status": post.status,
            "source": post.source,
            "platforms": [item.get("platform") for item in (post.platforms or []) if isinstance(item, dict)],
            "media_count": len(post.media_items or []) or int(bool(post.image_url)),
            "scheduled_for": post.scheduled_for.isoformat() if post.scheduled_for else None,
            "created_at": post.created_at.isoformat(),
            "sent_at": post.sent_at.isoformat() if post.sent_at else None,
        })
    return _reply(config, {"posts": results, "total": total, "pagination": pagination})


class SocialPostDetailsInput(BaseModel):
    post_id: str = Field(min_length=1, max_length=36, description="Exact social post ID returned by search")


@tool(args_schema=SocialPostDetailsInput)
def get_admin_social_post_details(post_id: str, config: RunnableConfig = None) -> str:
    """Get the full caption, media, targets, schedule, and status for an exact social post ID."""
    if not _admin(config or {}):
        return _reply(config)
    post = _find_post(post_id)
    if not post:
        return _reply(config, error="Social post not found. Search posts and use the exact returned ID.")
    item = serialize_social_post(post)
    detail = {
        "id": item["id"], "caption": item["caption"], "media_items": item["media_items"],
        "platforms": [{"platform": value.get("platform")} for value in (item["platforms"] or [])
                       if isinstance(value, dict)],
        "status": item["status"], "source": item["source"],
        "scheduled_for": item["scheduled_for"], "created_at": item["created_at"],
        "sent_at": item["sent_at"], "updated_at": item["updated_at"],
    }
    return _reply(config, {"post": detail})


@tool
def list_admin_social_accounts(config: RunnableConfig = None) -> str:
    """List connected publishing accounts with their exact IDs, platform, and display name."""
    if not _admin(config or {}):
        return _reply(config)
    if not ZernioService.is_configured():
        return _reply(config, error="Social media service not configured.")
    accounts, error = ZernioService.list_accounts()
    if error:
        return _reply(config, error=error)
    results = [{
        "account_id": str(account.get("_id") or account.get("id")),
        "platform": account.get("platform"),
        "name": account.get("name") or account.get("username") or account.get("platform"),
    } for account in accounts or [] if isinstance(account, dict) and (account.get("_id") or account.get("id"))]
    return _reply(config, {"accounts": results})


class SocialPostAnalyticsInput(BaseModel):
    post_id: str = Field(min_length=1, max_length=36)
    account_id: str | None = Field(default=None, max_length=150)


@tool(args_schema=SocialPostAnalyticsInput)
def get_admin_social_post_analytics(post_id: str, account_id: str | None = None,
                                    config: RunnableConfig = None) -> str:
    """Get analytics for a published post; account_id must be one of the post's exact targets."""
    if not _admin(config or {}):
        return _reply(config)
    post = _find_post(post_id)
    if not post:
        return _reply(config, error="Social post not found. Use an exact ID from search results.")
    if not post.zernio_post_id:
        return _reply(config, error="This post has not been published yet.")
    targets = [item for item in (post.platforms or []) if isinstance(item, dict)]
    account_ids = [item.get("accountId") or item.get("account_id") for item in targets]
    account_ids = [str(value) for value in account_ids if value]
    selected = account_id or (account_ids[0] if account_ids else None)
    if selected and selected not in account_ids:
        return _reply(config, error="Choose an account listed among this post's targets.")
    analytics, error = ZernioService.get_post_analytics(post.zernio_post_id, account_id=selected)
    if error:
        return _reply(config, error=error)
    return _reply(config, {"post_id": str(post.pk), "analytics": analytics})


class SocialPostCreateInput(BaseModel):
    caption: str = Field(min_length=1, max_length=5000)
    account_ids: list[str] | None = Field(default=None, max_length=20,
        description="Exact account IDs returned by list_admin_social_accounts; omit to target all allowed connected accounts")
    media_ids: list[str] = Field(default_factory=list, max_length=10,
        description="IDs of images attached to this chat")
    scheduled_for: str | None = Field(default=None, description="Optional future ISO 8601 datetime")


@tool(args_schema=SocialPostCreateInput)
def prepare_admin_social_post(caption: str, account_ids: list[str] | None = None,
                              media_ids: list[str] | None = None, scheduled_for: str | None = None,
                              config: RunnableConfig = None) -> str:
    """Prepare a social post preview. It is published or scheduled only after explicit confirmation."""
    admin = _admin(config or {})
    if not admin:
        return _reply(config)
    configurable = (config or {}).get("configurable") or {}
    pending, errors = AdminSocialPostActionService.prepare(
        admin, action="create", data={
            "caption": caption, "account_ids": account_ids, "media_ids": media_ids or [],
            "scheduled_for": scheduled_for,
        }, allowed_media_ids=configurable.get("attached_media_ids", []),
    )
    return json.dumps({"success": errors is None, "pending_action": pending, "errors": errors}, default=str)


class SocialPostActionInput(BaseModel):
    post_id: str = Field(min_length=1, max_length=36, description="Exact social post ID returned by search")


@tool(args_schema=SocialPostActionInput)
def prepare_admin_social_post_approval(post_id: str, config: RunnableConfig = None) -> str:
    """Prepare approval and publishing of one pending or failed social post; confirmation is required."""
    return _prepare_existing_post(post_id, "approve", config)


@tool(args_schema=SocialPostActionInput)
def prepare_admin_social_post_rejection(post_id: str, config: RunnableConfig = None) -> str:
    """Prepare rejection of one pending social post; confirmation is required."""
    return _prepare_existing_post(post_id, "reject", config)


def _prepare_existing_post(post_id, action, config):
    admin = _admin(config or {})
    if not admin:
        return _reply(config)
    pending, errors = AdminSocialPostActionService.prepare(
        admin, action=action, post_id=post_id,
    )
    return json.dumps({"success": errors is None, "pending_action": pending, "errors": errors}, default=str)
