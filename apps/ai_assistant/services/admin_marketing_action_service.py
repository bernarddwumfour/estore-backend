"""Prepare and confirm administrator-initiated marketing actions."""

from html import escape
from urllib.parse import urlsplit
from uuid import uuid4

from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError

from apps.blog.models import BlogPost
from apps.blog.schemas import validate_post
from apps.blog.services.blog_post_service import BlogPostService
from apps.products.models import OrderReview, ProductReview
from apps.products.models import ProductVariant
from apps.products.services.review_service import AdminReviewService
from apps.promotions.models import DiscountCode, Promotion
from apps.promotions.schemas import validate_discount_code_upsert, validate_promotion_create
from apps.promotions.services import PromotionService
from apps.social.models import SocialMedia
from apps.users.models import Affiliate

User = get_user_model()
ACTION_TTL_SECONDS = 600
ACTION_KEY_PREFIX = "admin_marketing_action:"
ALLOWED_ACTIONS = {
    "promotion": {"activate", "pause", "delete", "create"},
    "discount_code": {"activate", "deactivate", "create"},
    "blog_post": {"publish", "archive", "delete", "create"},
    "review": {"approve", "reject"},
}


class AdminMarketingActionService:
    @staticmethod
    def prepare(user, *, entity, action, ids=None, data=None, review_type=None, media_ids=None):
        if not user.is_active or user.role not in {User.ROLE_ADMIN, User.ROLE_STAFF}:
            return None, {"permission": "Admin access required"}
        if entity not in ALLOWED_ACTIONS or action not in ALLOWED_ACTIONS.get(entity, set()):
            return None, {"action": "Unsupported marketing action"}
        data = data or {}
        media_ids = media_ids or []
        is_create = action == "create" and entity in {"promotion", "discount_code", "blog_post"}
        if is_create:
            ids = []
        else:
            ids = ids or []
            if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
                return None, {"ids": "Supply 1 to 20 IDs"}
            if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
                return None, {"ids": "IDs must be distinct non-empty strings"}

        payload = {"entity": entity, "action": action, "ids": ids}
        if is_create:
            cover_media_id = data.pop("cover_media_id", None)
            if entity == "promotion" and (not isinstance(media_ids, list) or len(media_ids) > 10):
                return None, {"media_ids": "Choose up to 10 promotion images"}
            if entity != "promotion" and media_ids:
                return None, {"media_ids": "Images are only accepted for promotions"}
            selected_media_ids = list(media_ids)
            if entity == "blog_post" and cover_media_id:
                selected_media_ids.append(cover_media_id)
            if len(selected_media_ids) != len(set(selected_media_ids)):
                return None, {"media_ids": "Choose distinct images"}
            media = {}
            if selected_media_ids:
                if any(not isinstance(value, str) for value in selected_media_ids):
                    return None, {"media_ids": "Invalid image selection"}
                try:
                    media = {str(item.pk): item for item in SocialMedia.objects.filter(
                        pk__in=selected_media_ids, media_type=SocialMedia.TYPE_IMAGE,
                    )}
                except (TypeError, ValueError, ValidationError):
                    return None, {"media_ids": "One or more selected image IDs are invalid"}
                if len(media) != len(selected_media_ids) or any(not item.url for item in media.values()):
                    return None, {"media_ids": "One or more selected images are unavailable"}
            if entity == "blog_post" and cover_media_id:
                data["cover_image_url"] = media[cover_media_id].url
            if entity == "promotion":
                cleaned, errors = validate_promotion_create(data)
            elif entity == "discount_code":
                cleaned, errors = validate_discount_code_upsert(data)
            else:
                cleaned, errors = validate_post(data)
            if errors:
                return None, errors
            if entity == "promotion":
                variant_ids = [str(item["variant_id"]) for item in cleaned["items"]]
                if len(variant_ids) != len(set(variant_ids)):
                    return None, {"items": "A variant can only appear once in a promotion"}
                try:
                    if ProductVariant.objects.filter(pk__in=variant_ids).count() != len(variant_ids):
                        return None, {"items": "One or more variants were not found"}
                except (ValueError, TypeError, ValidationError):
                    return None, {"items": "One or more variant IDs are invalid"}
            elif entity == "discount_code":
                if cleaned["discount_type"] == DiscountCode.TYPE_PERCENTAGE and cleaned["value"] > 100:
                    return None, {"value": "Percentage discounts cannot exceed 100"}
                if DiscountCode.objects.filter(code=cleaned["code"]).exists():
                    return None, {"code": "Discount code already exists"}
                if Affiliate.objects.filter(referral_code=cleaned["code"]).exists():
                    return None, {"code": "Code is already used as an affiliate reference"}
                if cleaned.get("starts_at") and cleaned.get("ends_at"):
                    try:
                        if cleaned["ends_at"] <= cleaned["starts_at"]:
                            return None, {"ends_at": "End date must be after the start date"}
                    except TypeError:
                        return None, {"dates": "Start and end dates must use compatible time zones"}
            elif entity == "blog_post":
                cover_url = cleaned.get("cover_image_url", "").strip()
                if cover_url and urlsplit(cover_url).scheme not in {"http", "https"}:
                    return None, {"cover_image_url": "Cover images must use an HTTP or HTTPS URL"}
                paragraphs = [part.strip() for part in cleaned["content"].splitlines() if part.strip()]
                cleaned["content"] = "".join(f"<p>{escape(paragraph)}</p>" for paragraph in paragraphs)
            payload["data"] = cleaned
            if entity == "promotion":
                payload["media_ids"] = selected_media_ids
            model = None
        elif entity == "promotion":
            model = Promotion
        elif entity == "discount_code":
            model = DiscountCode
        elif entity == "blog_post":
            model = BlogPost
        else:
            if review_type not in {"product", "order"}:
                return None, {"review_type": "Choose product or order reviews"}
            model = ProductReview if review_type == "product" else OrderReview
            payload["review_type"] = review_type

        if not is_create:
            try:
                if model.objects.filter(pk__in=ids).count() != len(ids):
                    return None, {"ids": "One or more selected records were not found"}
            except (ValueError, TypeError, ValidationError):
                return None, {"ids": "One or more IDs are invalid"}

        action_id = str(uuid4())
        cache.set(f"{ACTION_KEY_PREFIX}{action_id}",
                  {"user_id": str(user.pk), "payload": payload}, ACTION_TTL_SECONDS)
        review_data = dict(payload.get("data", {}))
        if is_create and entity == "promotion":
            review_data["image_count"] = len(payload.get("media_ids", []))
        pending = {
            "action_id": action_id,
            "action": f"{entity}_{action}",
            "details": {
                "target_id": "",
                "data": review_data,
                "ids": ids,
                "bulk_action": action,
            },
            "expires_in_seconds": ACTION_TTL_SECONDS,
            "confirmation_path": f"/api/assistant/admin/marketing/actions/{action_id}/confirm/",
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
        entity, action, ids = payload["entity"], payload["action"], payload["ids"]
        if action == "create" and entity == "promotion":
            image_files = []
            for media in SocialMedia.objects.filter(
                pk__in=payload.get("media_ids", []), media_type=SocialMedia.TYPE_IMAGE,
            ):
                media.file.open("rb")
                try:
                    image_files.append(ContentFile(media.file.read(), name=media.file.name.rsplit("/", 1)[-1]))
                finally:
                    media.file.close()
            if len(image_files) != len(payload.get("media_ids", [])):
                cache.delete(key)
                return None, {"media_ids": "One or more selected images are no longer available"}
            result, errors = PromotionService.create_promotion(payload["data"], image_files, user)
            if result:
                result = {"id": str(result.pk), "name": result.name, "status": result.status}
        elif action == "create" and entity == "discount_code":
            result, errors = PromotionService.create_discount_code(payload["data"], user)
            if result:
                result = {"id": str(result.pk), "code": result.code, "name": result.name,
                          "is_active": result.is_active}
        elif action == "create" and entity == "blog_post":
            result, errors = BlogPostService.create_post(payload["data"], user=user)
            if result:
                result = {"id": str(result.pk), "title": result.title, "slug": result.slug,
                          "status": result.status}
        elif entity == "promotion":
            result, errors = PromotionService.bulk_action_promotions(ids, action, user)
        elif entity == "blog_post":
            result, errors = BlogPostService.bulk_action_posts(ids, action, user)
        elif entity == "review":
            result = AdminReviewService.bulk_moderate_reviews(
                ids, action, user, review_type=payload["review_type"],
            )
            errors = None
        else:
            result = {"success": [], "failed": [], "total": len(ids)}
            errors = None
            for code_id in ids:
                code = DiscountCode.objects.filter(pk=code_id).first()
                if not code:
                    result["failed"].append({"id": code_id, "reason": "Discount code not found"})
                    continue
                updated, error = PromotionService.toggle_discount_code_status(
                    code, action == "activate",
                )
                if error:
                    result["failed"].append({"id": code_id, "reason": error})
                else:
                    result["success"].append({"id": str(updated.pk), "code": updated.code,
                                               "is_active": updated.is_active})
        cache.delete(key)
        return result, errors
