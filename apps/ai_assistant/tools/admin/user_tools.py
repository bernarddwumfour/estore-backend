"""Admin-only user and affiliate directory tools."""

import json
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.cache import cache
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.users.models import Affiliate
from apps.users.selectors.user_selectors import get_users_filtered

User = get_user_model()


def _admin(config):
    user_id = (config.get("configurable") or {}).get("authenticated_user_id")
    return User.objects.filter(pk=user_id, is_active=True, role=User.ROLE_ADMIN).first() if user_id else None


def _reply(config, data=None, error=None):
    return json.dumps({"success": error is None, "data": data, "error": error}) if _admin(config or {}) else json.dumps({"success": False, "error": "Admin access required."})


def _masked_user(user):
    """Keep users distinguishable while masking direct contact details."""
    return {
        "user_id": user.user_code,
        "first_name": user.first_name,
        "email": "***@***",
        "role": user.role,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "is_guest": user.is_guest,
    }


class UserSearchInput(BaseModel):
    search: str | None = Field(default=None, max_length=150, description="Search email, name, username, or phone")
    role: str | None = Field(default=None, description="admin, staff, or customer")
    is_active: bool | None = None
    email_verified: bool | None = None
    is_guest: bool | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=20)


@tool(args_schema=UserSearchInput)
def search_admin_users(search: str | None = None, role: str | None = None,
                       is_active: bool | None = None, email_verified: bool | None = None,
                       is_guest: bool | None = None, page: int = 1, limit: int = 10,
                       config: RunnableConfig = None) -> str:
    """Search users by contact, role, status, verification, or guest account; admin only."""
    if not _admin(config or {}):
        return _reply(config)
    if role and role not in {User.ROLE_ADMIN, User.ROLE_STAFF, User.ROLE_CUSTOMER}:
        return _reply(config, error="Invalid role filter.")
    users, total, pagination = get_users_filtered(
        search=search, role=role, is_active=is_active, email_verified=email_verified,
        is_guest=is_guest, page=page, limit=limit,
    )
    return _reply(config, {"users": [_masked_user(user) for user in users],
                           "total": total, "pagination": pagination})


class UserDetailInput(BaseModel):
    user_id: str = Field(min_length=8, max_length=36, description="Human-readable user ID, such as USR-ABC234DEF567")


@tool(args_schema=UserDetailInput)
def get_admin_user(user_id: str, config: RunnableConfig) -> str:
    """Inspect an account's role, status, verification, and guest status. Contact details are masked."""
    if not _admin(config):
        return _reply(config)
    user = User.objects.filter(user_code=user_id).first()
    if not user:
        return _reply(config, error="User not found.")
    return _reply(config, _masked_user(user))


class AffiliateSearchInput(BaseModel):
    search: str | None = Field(default=None, max_length=150)
    is_active: bool | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=20)


@tool(args_schema=AffiliateSearchInput)
def search_admin_affiliates(search: str | None = None, is_active: bool | None = None,
                            page: int = 1, limit: int = 10,
                            config: RunnableConfig = None) -> str:
    """Search affiliate accounts by email/name/referral code and active status; personal and financial details are masked."""
    if not _admin(config or {}):
        return _reply(config)
    affiliates = Affiliate.objects.select_related("user").filter(user__is_active=True)
    if is_active is not None:
        affiliates = affiliates.filter(is_active=is_active)
    if search:
        from django.db.models import Q
        affiliates = affiliates.filter(
            Q(user__email__icontains=search) | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search) | Q(referral_code__icontains=search)
        )
    total = affiliates.count()
    start = (page - 1) * limit
    results = [{"user_id": a.user.user_code, "first_name": a.user.first_name,
                "email": "***@***", "is_active": a.is_active,
                "is_approved": a.is_approved, "level": a.level}
               for a in affiliates.order_by("-total_earnings")[start:start + limit]]
    return _reply(config, {"affiliates": results, "total": total,
                           "page": page, "limit": limit})


class UpdateUserInput(BaseModel):
    user_id: str = Field(min_length=8, max_length=36, description="Human-readable user ID, such as USR-ABC234DEF567")
    changes: dict = Field(description="Allowed fields: first_name, last_name, phone, role, is_active")


@tool(args_schema=UpdateUserInput)
def prepare_admin_user_update(user_id: str, changes: dict,
                             config: RunnableConfig) -> str:
    """Prepare an account profile, role, or active status change for separate confirmation."""
    admin = _admin(config)
    if not admin:
        return _reply(config)
    allowed = {"first_name", "last_name", "phone", "role", "is_active"}
    if not changes or set(changes) - allowed:
        return _reply(config, error="Supply supported user fields to change.")
    for field in ("first_name", "last_name", "phone"):
        if field in changes and not isinstance(changes[field], str):
            return _reply(config, error=f"{field} must be text.")
    if "first_name" in changes and len(changes["first_name"]) > 150:
        return _reply(config, error="first_name cannot exceed 150 characters.")
    if "last_name" in changes and len(changes["last_name"]) > 150:
        return _reply(config, error="last_name cannot exceed 150 characters.")
    if "phone" in changes and len(changes["phone"]) > 20:
        return _reply(config, error="phone cannot exceed 20 characters.")
    if "is_active" in changes and type(changes["is_active"]) is not bool:
        return _reply(config, error="is_active must be a boolean.")
    if "role" in changes and changes["role"] not in {User.ROLE_ADMIN, User.ROLE_STAFF, User.ROLE_CUSTOMER}:
        return _reply(config, error="Invalid user role.")
    target = User.objects.filter(user_code=user_id).first()
    if not target:
        return _reply(config, error="User not found.")
    if target.is_superuser:
        return _reply(config, error="Superuser accounts cannot be changed through the agent.")
    if str(target.pk) == str(admin.pk) and changes.get("is_active") is False:
        return _reply(config, error="You cannot deactivate your own account.")
    if str(target.pk) == str(admin.pk) and changes.get("role", User.ROLE_ADMIN) != User.ROLE_ADMIN:
        return _reply(config, error="You cannot change your own administrator role.")
    action_id = str(uuid4())
    pending = {"action_id": action_id, "action": "update_user",
               "target_id": target.user_code, "changed_fields": sorted(changes),
               "expires_in_seconds": 600,
               "confirmation_path": f"/api/assistant/admin/users/actions/{action_id}/confirm/"}
    cache.set(f"admin_user_action:{action_id}",
              {"user_id": str(admin.pk), "target_id": str(target.pk), "changes": changes}, 600)
    return json.dumps({"success": True, "pending_action": pending})
