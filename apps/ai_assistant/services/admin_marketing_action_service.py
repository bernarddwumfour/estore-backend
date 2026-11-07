"""Prepare and confirm administrator-initiated marketing actions."""

from uuid import uuid4

from django.core.cache import cache
from django.contrib.auth import get_user_model

from apps.blog.models import BlogPost
from apps.blog.services.blog_post_service import BlogPostService
from apps.products.models import OrderReview, ProductReview
from apps.products.services.review_service import AdminReviewService
from apps.promotions.models import DiscountCode, Promotion
from apps.promotions.services import PromotionService

User = get_user_model()
ACTION_TTL_SECONDS = 600
ACTION_KEY_PREFIX = "admin_marketing_action:"
ALLOWED_ACTIONS = {
    "promotion": {"activate", "pause", "delete"},
    "discount_code": {"activate", "deactivate"},
    "blog_post": {"publish", "archive", "delete"},
    "review": {"approve", "reject"},
}


class AdminMarketingActionService:
    @staticmethod
    def prepare(user, *, entity, action, ids, review_type=None):
        if not user.is_active or user.role not in {User.ROLE_ADMIN, User.ROLE_STAFF}:
            return None, {"permission": "Admin access required"}
        if entity not in ALLOWED_ACTIONS or action not in ALLOWED_ACTIONS.get(entity, set()):
            return None, {"action": "Unsupported marketing action"}
        if not isinstance(ids, list) or not 1 <= len(ids) <= 20:
            return None, {"ids": "Supply 1 to 20 IDs"}
        if any(not isinstance(value, str) or not value for value in ids) or len(set(ids)) != len(ids):
            return None, {"ids": "IDs must be distinct non-empty strings"}

        payload = {"entity": entity, "action": action, "ids": ids}
        if entity == "promotion":
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

        try:
            if model.objects.filter(pk__in=ids).count() != len(ids):
                return None, {"ids": "One or more selected records were not found"}
        except (ValueError, TypeError):
            return None, {"ids": "One or more IDs are invalid"}

        action_id = str(uuid4())
        cache.set(f"{ACTION_KEY_PREFIX}{action_id}",
                  {"user_id": str(user.pk), "payload": payload}, ACTION_TTL_SECONDS)
        pending = {
            "action_id": action_id,
            "action": f"{entity}_{action}",
            "details": {
                "target_id": "",
                "data": {},
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
        if entity == "promotion":
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
