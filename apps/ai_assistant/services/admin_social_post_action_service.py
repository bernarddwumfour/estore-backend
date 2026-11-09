"""Prepare and confirm social post actions for authorized administrators."""

from uuid import uuid4

from django.core.cache import cache
from django.contrib.auth import get_user_model

from apps.social.models import SocialMedia, SocialPost
from apps.social.schemas import validate_post_create
from apps.social.services import SocialPostService
from apps.social.zernio_service import ZernioService

User = get_user_model()
ACTION_TTL_SECONDS = 600
ACTION_KEY_PREFIX = "admin_social_post_action:"


class AdminSocialPostActionService:
    @staticmethod
    def prepare(user, *, action, data=None, post_id=None, allowed_media_ids=None):
        if not user.is_active or user.role not in {User.ROLE_ADMIN, User.ROLE_STAFF}:
            return None, {"permission": "Admin access required"}
        if action not in {"create", "approve", "reject"}:
            return None, {"action": "Unsupported social post action"}
        if not ZernioService.is_configured():
            return None, {"social": "Social media service not configured"}

        data = data or {}
        payload = {"action": action}
        preview = None
        target_id = ""
        ids = []

        if action == "create":
            media_ids = data.pop("media_ids", [])
            allowed_media_ids = set(allowed_media_ids or [])
            if not isinstance(media_ids, list) or len(media_ids) > 10:
                return None, {"media_ids": "Choose up to 10 attached images"}
            if any(not isinstance(value, str) for value in media_ids):
                return None, {"media_ids": "Image IDs must be strings"}
            if len(media_ids) != len(set(media_ids)) or any(value not in allowed_media_ids for value in media_ids):
                return None, {"media_ids": "Use distinct images attached to this chat message"}
            media = list(SocialMedia.objects.filter(
                pk__in=media_ids, media_type=SocialMedia.TYPE_IMAGE,
            )) if media_ids else []
            if len(media) != len(media_ids) or any(not item.url for item in media):
                return None, {"media_ids": "One or more selected images are unavailable"}

            media_items = [{"type": "image", "url": item.url, "title": item.name}
                           for item in media]
            request_data = {key: value for key, value in data.items() if key != "media_ids"}
            if media_items:
                request_data["media_items"] = media_items
            cleaned, errors = validate_post_create(request_data)
            if errors:
                return None, errors
            account_ids = cleaned.get("account_ids")
            platforms, error = SocialPostService.resolve_platforms(account_ids)
            if error:
                return None, {"accounts": error}
            payload.update({"data": cleaned, "media_ids": media_ids})
            preview = {
                "type": "social_post", "caption": cleaned["caption"],
                "image_urls": [item["url"] for item in media_items],
                "targets": platforms,
                "scheduled_for": cleaned.get("scheduled_for").isoformat()
                if cleaned.get("scheduled_for") else None,
            }
            target_summary = ", ".join(item["platform"] for item in platforms)
        else:
            try:
                post = SocialPost.objects.get(pk=post_id)
            except (SocialPost.DoesNotExist, ValueError, TypeError):
                return None, {"post_id": "Social post not found. Use an exact ID from search results."}
            if action == "approve" and post.status not in {
                SocialPost.STATUS_PENDING_APPROVAL, SocialPost.STATUS_FAILED,
            }:
                return None, {"status": "Only pending or failed posts can be approved"}
            if action == "reject" and post.status != SocialPost.STATUS_PENDING_APPROVAL:
                return None, {"status": "Only pending posts can be rejected"}
            target_id = str(post.pk)
            ids = [target_id]
            payload["post_id"] = target_id
            preview = {
                "type": "social_post", "caption": post.caption,
                "image_urls": [item.get("url") for item in (post.media_items or []) if item.get("url")]
                    or ([post.image_url] if post.image_url else []),
                "targets": post.platforms or [],
                "scheduled_for": post.scheduled_for.isoformat() if post.scheduled_for else None,
            }
            platform_names = [item.get("platform", "") for item in (post.platforms or [])
                              if isinstance(item, dict)]
            target_summary = f"{post.status} · {', '.join(platform_names)}"

        action_id = str(uuid4())
        cache.set(f"{ACTION_KEY_PREFIX}{action_id}",
                  {"user_id": str(user.pk), "payload": payload}, ACTION_TTL_SECONDS)
        pending = {
            "action_id": action_id,
            "action": f"social_post_{action}",
            "details": {
                "target_id": target_id, "target_summary": target_summary,
                "data": {}, "preview": preview, "ids": ids, "bulk_action": action,
            },
            "expires_in_seconds": ACTION_TTL_SECONDS,
            "confirmation_path": f"/api/assistant/admin/social/posts/actions/{action_id}/confirm/",
        }
        return pending, None

    @staticmethod
    def confirm(user, action_id):
        if not user.is_active or user.role not in {User.ROLE_ADMIN, User.ROLE_STAFF}:
            return None, {"permission": "Admin access required"}
        key = f"{ACTION_KEY_PREFIX}{action_id}"
        record = cache.get(key)
        if not record or record["user_id"] != str(user.pk):
            return None, {"action": "Pending action not found or expired"}
        if not cache.add(f"{key}:used", True, ACTION_TTL_SECONDS):
            return None, {"action": "Action has already been confirmed"}

        payload = record["payload"]
        action = payload["action"]
        if not ZernioService.is_configured():
            cache.delete(key)
            return None, {"social": "Social media service is no longer configured"}
        if action == "create":
            data = dict(payload["data"])
            if payload.get("media_ids"):
                selected = {str(item.pk): item for item in SocialMedia.objects.filter(
                    pk__in=payload["media_ids"], media_type=SocialMedia.TYPE_IMAGE,
                )}
                if len(selected) != len(payload["media_ids"]):
                    cache.delete(key)
                    return None, {"media_ids": "One or more selected images are no longer available"}
            account_ids = data.pop("account_ids", None)
            data["account_ids"] = account_ids
            post, error = SocialPostService.create_manual_post(data, user)
            result = {"post_id": str(post.pk), "status": post.status} if post else None
            errors = {"social": error} if error else None
        else:
            try:
                post = SocialPost.objects.get(pk=payload["post_id"])
            except (SocialPost.DoesNotExist, ValueError, TypeError):
                cache.delete(key)
                return None, {"post_id": "Social post no longer exists"}
            if action == "approve":
                post, error = SocialPostService.approve_post(post, {}, user)
                result = {"post_id": str(post.pk), "status": post.status} if post else None
                errors = {"social": error} if error else None
            else:
                post, error = SocialPostService.reject_post(post, user)
                result = {"post_id": str(post.pk), "status": post.status} if post else None
                errors = {"social": error} if error else None
        cache.delete(key)
        return result, errors
