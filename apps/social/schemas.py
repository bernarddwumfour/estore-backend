"""
Social schemas — request validation and serialization for social posts.
"""

from datetime import datetime
from typing import Dict, Tuple

from django.utils import timezone as dj_timezone

from apps.social.models import SocialPost

CAPTION_MAX_LENGTH = 5000
COMMENT_ACTIONS = {"hide", "unhide", "like", "unlike", "delete"}
MEDIA_ITEM_TYPES = {"image", "video"}
MEDIA_ITEM_MAX_COUNT = 10


def _clean_caption(data: Dict, errors: Dict, cleaned: Dict, required: bool) -> None:
    caption = data.get("caption")
    if caption is None or (isinstance(caption, str) and not caption.strip()):
        if required:
            errors["caption"] = "Caption is required"
        elif "caption" in data:
            errors["caption"] = "Caption cannot be empty"
        return
    if not isinstance(caption, str):
        errors["caption"] = "Caption must be a string"
        return
    cleaned["caption"] = caption.strip()[:CAPTION_MAX_LENGTH]


def _clean_account_ids(data: Dict, errors: Dict, cleaned: Dict) -> None:
    account_ids = data.get("account_ids")
    if account_ids is None:
        return
    if not isinstance(account_ids, list) or not all(
        isinstance(a, str) and a.strip() for a in account_ids
    ):
        errors["account_ids"] = "Account ids must be a list of non-empty strings"
        return
    cleaned["account_ids"] = [a.strip() for a in account_ids]


def _clean_image_url(data: Dict, errors: Dict, cleaned: Dict) -> None:
    image_url = data.get("image_url")
    if image_url is None:
        return
    if not isinstance(image_url, str):
        errors["image_url"] = "Image URL must be a string"
        return
    image_url = image_url.strip()
    if image_url and not image_url.startswith(("http://", "https://")):
        errors["image_url"] = "Image URL must be a valid http(s) URL"
        return
    cleaned["image_url"] = image_url[:500]


def _media_type_for_url(url: str) -> str:
    path = url.split("?", 1)[0].lower()
    if path.endswith((".mp4", ".mov", ".webm")):
        return "video"
    return "image"


def _clean_media_items(data: Dict, errors: Dict, cleaned: Dict) -> None:
    if "media_items" not in data:
        return

    media_items = data.get("media_items")
    if media_items is None:
        cleaned["media_items"] = []
        return
    if not isinstance(media_items, list):
        errors["media_items"] = "Media items must be a list"
        return
    if len(media_items) > MEDIA_ITEM_MAX_COUNT:
        errors["media_items"] = f"Media items cannot exceed {MEDIA_ITEM_MAX_COUNT} files"
        return

    cleaned_items = []
    for index, item in enumerate(media_items):
        if not isinstance(item, dict):
            errors[f"media_items.{index}"] = "Media item must be an object"
            continue

        url = item.get("url")
        if not isinstance(url, str) or not url.strip():
            errors[f"media_items.{index}.url"] = "Media URL is required"
            continue
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            errors[f"media_items.{index}.url"] = "Media URL must be a valid http(s) URL"
            continue

        media_type = item.get("type") or item.get("media_type") or _media_type_for_url(url)
        if not isinstance(media_type, str) or media_type not in MEDIA_ITEM_TYPES:
            errors[f"media_items.{index}.type"] = "Media type must be image or video"
            continue

        cleaned_item = {"type": media_type, "url": url[:500]}
        title = item.get("title") or item.get("name")
        if title is not None:
            if not isinstance(title, str):
                errors[f"media_items.{index}.title"] = "Media title must be a string"
                continue
            if title.strip():
                cleaned_item["title"] = title.strip()[:120]
        cleaned_items.append(cleaned_item)

    if not any(key.startswith("media_items") for key in errors):
        cleaned["media_items"] = cleaned_items


def _clean_scheduled_for(data: Dict, errors: Dict, cleaned: Dict) -> None:
    scheduled_for = data.get("scheduled_for")
    if scheduled_for is None:
        return
    if not isinstance(scheduled_for, str) or not scheduled_for.strip():
        errors["scheduled_for"] = "Scheduled time must be an ISO 8601 datetime string"
        return
    try:
        parsed = datetime.fromisoformat(scheduled_for.strip().replace("Z", "+00:00"))
    except ValueError:
        errors["scheduled_for"] = "Scheduled time must be an ISO 8601 datetime string"
        return
    if dj_timezone.is_naive(parsed):
        parsed = dj_timezone.make_aware(parsed)
    if parsed <= dj_timezone.now():
        errors["scheduled_for"] = "Scheduled time must be in the future"
        return
    cleaned["scheduled_for"] = parsed


def validate_post_create(data: Dict) -> Tuple[Dict, Dict]:
    errors: Dict = {}
    cleaned: Dict = {}
    _clean_caption(data, errors, cleaned, required=True)
    _clean_account_ids(data, errors, cleaned)
    _clean_image_url(data, errors, cleaned)
    _clean_media_items(data, errors, cleaned)
    _clean_scheduled_for(data, errors, cleaned)
    return cleaned, errors


def validate_post_approve(data: Dict) -> Tuple[Dict, Dict]:
    errors: Dict = {}
    cleaned: Dict = {}
    _clean_caption(data, errors, cleaned, required=False)
    _clean_account_ids(data, errors, cleaned)
    _clean_image_url(data, errors, cleaned)
    _clean_media_items(data, errors, cleaned)
    _clean_scheduled_for(data, errors, cleaned)
    return cleaned, errors


def _clean_message(data: Dict, errors: Dict, cleaned: Dict, field: str = "message") -> None:
    message = data.get(field)
    if not message or not isinstance(message, str) or not message.strip():
        errors[field] = "Message is required"
        return
    cleaned[field] = message.strip()[:CAPTION_MAX_LENGTH]


def _clean_optional_string(data: Dict, errors: Dict, cleaned: Dict, field: str, *, alias: str = None) -> None:
    value = data.get(field)
    if value is None and alias:
        value = data.get(alias)
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        errors[field] = f"{field.replace('_', ' ').title()} must be a non-empty string"
        return
    cleaned[field] = value.strip()


def _clean_required_string(data: Dict, errors: Dict, cleaned: Dict, field: str, *, alias: str = None) -> None:
    value = data.get(field)
    if value is None and alias:
        value = data.get(alias)
    if not isinstance(value, str) or not value.strip():
        errors[field] = f"{field.replace('_', ' ').title()} is required"
        return
    cleaned[field] = value.strip()


def validate_comment_reply(data: Dict) -> Tuple[Dict, Dict]:
    errors: Dict = {}
    cleaned: Dict = {}
    comment_id = data.get("comment_id")
    if not comment_id or not isinstance(comment_id, str) or not comment_id.strip():
        errors["comment_id"] = "Comment id is required"
    else:
        cleaned["comment_id"] = comment_id.strip()
    _clean_message(data, errors, cleaned)
    _clean_optional_string(data, errors, cleaned, "account_id", alias="accountId")
    _clean_optional_string(data, errors, cleaned, "parent_cid", alias="parentCid")
    _clean_optional_string(data, errors, cleaned, "root_uri", alias="rootUri")
    _clean_optional_string(data, errors, cleaned, "root_cid", alias="rootCid")
    return cleaned, errors


def validate_comment_action(data: Dict) -> Tuple[Dict, Dict]:
    errors: Dict = {}
    cleaned: Dict = {}
    comment_id = data.get("comment_id")
    if not comment_id or not isinstance(comment_id, str) or not comment_id.strip():
        errors["comment_id"] = "Comment id is required"
    else:
        cleaned["comment_id"] = comment_id.strip()
    action = data.get("action")
    if action not in COMMENT_ACTIONS:
        errors["action"] = (
            f"Invalid action. Must be one of: {', '.join(sorted(COMMENT_ACTIONS))}"
        )
    else:
        cleaned["action"] = action
    _clean_optional_string(data, errors, cleaned, "account_id", alias="accountId")
    _clean_optional_string(data, errors, cleaned, "cid")
    _clean_optional_string(data, errors, cleaned, "like_uri", alias="likeUri")
    return cleaned, errors


def validate_message_send(data: Dict) -> Tuple[Dict, Dict]:
    errors: Dict = {}
    cleaned: Dict = {}
    _clean_message(data, errors, cleaned)
    _clean_required_string(data, errors, cleaned, "account_id", alias="accountId")
    return cleaned, errors


def serialize_social_post(post: SocialPost) -> Dict:
    return {
        "id": str(post.id),
        "source": post.source,
        "object_id": str(post.object_id) if post.object_id else None,
        "caption": post.caption,
        "image_url": post.image_url,
        "media_items": post.media_items,
        "platforms": post.platforms,
        "status": post.status,
        "zernio_post_id": post.zernio_post_id,
        "scheduled_for": post.scheduled_for.isoformat() if post.scheduled_for else None,
        "created_by": post.created_by.email if post.created_by else None,
        "reviewed_by": post.reviewed_by.email if post.reviewed_by else None,
        "created_at": post.created_at.isoformat() if post.created_at else None,
        "updated_at": post.updated_at.isoformat() if post.updated_at else None,
        "sent_at": post.sent_at.isoformat() if post.sent_at else None,
    }


def serialize_social_post_list(posts) -> list:
    return [serialize_social_post(p) for p in posts]


def validate_config_update(data: Dict) -> Tuple[Dict, Dict]:
    from apps.social.models import SocialConfig

    errors: Dict = {}
    cleaned: Dict = {}
    mode = data.get("mode")
    valid_modes = {choice for choice, _ in SocialConfig.MODE_CHOICES}
    if mode not in valid_modes:
        errors["mode"] = f"Invalid mode. Must be one of: {', '.join(sorted(valid_modes))}"
    else:
        cleaned["mode"] = mode
    return cleaned, errors


CONNECT_PLATFORMS = {
    "instagram", "tiktok", "twitter", "facebook", "linkedin", "youtube",
    "whatsapp", "threads", "pinterest", "reddit", "bluesky", "telegram",
    "googlebusiness", "snapchat", "discord",
}


def validate_profile_upsert(data: Dict, partial: bool = False) -> Tuple[Dict, Dict]:
    errors: Dict = {}
    cleaned: Dict = {}

    name = data.get("name")
    if name is None or (isinstance(name, str) and not name.strip()):
        if not partial:
            errors["name"] = "Name is required"
        elif "name" in data:
            errors["name"] = "Name cannot be empty"
    elif not isinstance(name, str):
        errors["name"] = "Name must be a string"
    else:
        cleaned["name"] = name.strip()[:100]

    if "description" in data:
        description = data.get("description") or ""
        if not isinstance(description, str):
            errors["description"] = "Description must be a string"
        else:
            cleaned["description"] = description.strip()[:255]

    return cleaned, errors


def validate_account_move(data: Dict) -> Tuple[Dict, Dict]:
    errors: Dict = {}
    cleaned: Dict = {}
    profile_id = data.get("profile_id")
    if not profile_id or not isinstance(profile_id, str) or not profile_id.strip():
        errors["profile_id"] = "Profile id is required"
    else:
        cleaned["profile_id"] = profile_id.strip()
    return cleaned, errors


def validate_connect(data: Dict) -> Tuple[Dict, Dict]:
    errors: Dict = {}
    cleaned: Dict = {}
    platform = data.get("platform")
    if platform not in CONNECT_PLATFORMS:
        errors["platform"] = (
            f"Invalid platform. Must be one of: {', '.join(sorted(CONNECT_PLATFORMS))}"
        )
    else:
        cleaned["platform"] = platform
    _clean_required_string(data, errors, cleaned, "profile_id", alias="profileId")
    return cleaned, errors


def serialize_social_media(media) -> Dict:
    return {
        "id": str(media.id),
        "url": media.url,
        "media_type": media.media_type,
        "name": media.name,
        "uploaded_by": media.uploaded_by.email if media.uploaded_by else None,
        "created_at": media.created_at.isoformat() if media.created_at else None,
    }
