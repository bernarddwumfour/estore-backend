"""Prepare product changes for a separate, authenticated confirmation request."""

import uuid
from decimal import Decimal

from django.core.cache import cache
from django.db import transaction

from apps.products.models import Category, Product, ProductVariant
from apps.products.schemas import (
    validate_product_create, validate_product_update,
    validate_variant_create, validate_variant_update,
    validate_product_bulk_action,
)
from apps.products.services.category_service import CategoryService
from apps.products.services.product_service import AdminProductService, ProductService

ACTION_TTL_SECONDS = 600
PRODUCT_BULK_ACTIONS = {
    "publish", "draft", "archive", "feature", "unfeature",
    "bestseller", "unbestseller", "new", "unnew", "delete",
}
CATEGORY_BULK_ACTIONS = {"activate", "deactivate", "hide", "unhide", "delete"}
VARIANT_BULK_ACTIONS = {"activate", "deactivate", "set_default", "unset_default", "delete"}


def _cache_key(action_id):
    return f"admin_product_action:{action_id}"


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


class AdminProductActionService:
    @staticmethod
    def prepare(user, action, payload):
        if not user.is_active or user.role not in {user.ROLE_ADMIN, user.ROLE_STAFF}:
            return None, {"permission": "Admin access required"}

        data = dict(payload.get("data") or {})
        target_id = str(payload.get("target_id") or "")
        ids = [str(item) for item in payload.get("ids", [])]
        bulk_action = payload.get("bulk_action")

        if action == "create_product":
            data, errors = validate_product_create(data, is_admin=True)
            if not errors and not Category.objects.filter(pk=data["category_id"]).exists():
                errors = {"category_id": "Category not found"}
        elif action == "update_product":
            data, errors = validate_product_update(data, is_admin=True)
            if not errors and (not data or not Product.objects.filter(pk=target_id).exists()):
                errors = {"product": "Product not found or no changes supplied"}
        elif action == "create_variant":
            data, errors = validate_variant_create(data, is_admin=True)
            if not errors and not Product.objects.filter(pk=target_id).exists():
                errors = {"product_id": "Product not found"}
        elif action == "update_variant":
            data, errors = validate_variant_update(data, is_admin=True)
            if not errors and (not data or not ProductVariant.objects.filter(pk=target_id).exists()):
                errors = {"variant": "Variant not found or no changes supplied"}
        elif action == "create_category":
            errors = {"name": "A category name is required"} if not str(data.get("name", "")).strip() else None
            if not errors and data.get("parent_id") and not Category.objects.filter(pk=data["parent_id"]).exists():
                errors = {"parent_id": "Parent category not found"}
        elif action == "update_category":
            errors = None if data and Category.objects.filter(pk=target_id).exists() else {"category": "Category not found or no changes supplied"}
            allowed_fields = {"name", "description", "parent_id", "is_active", "is_hidden",
                              "meta_title", "meta_description"}
            if not errors and (set(data) - allowed_fields):
                errors = {"fields": "Unsupported category field"}
            if not errors and "name" in data and not str(data["name"]).strip():
                errors = {"name": "Category name cannot be empty"}
        elif action in {"bulk_products", "bulk_categories", "bulk_variants"}:
            allowed = {"bulk_products": PRODUCT_BULK_ACTIONS,
                       "bulk_categories": CATEGORY_BULK_ACTIONS,
                       "bulk_variants": VARIANT_BULK_ACTIONS}[action]
            errors = None
            if bulk_action not in allowed:
                errors = {"action": "Unsupported action"}
            elif not ids or len(ids) > 20 or len(ids) != len(set(ids)):
                errors = {"ids": "Supply 1 to 20 distinct IDs"}
            elif action == "bulk_products":
                _, errors = validate_product_bulk_action({"product_ids": ids, "action": bulk_action})
        else:
            return None, {"action": "Unsupported action"}

        if errors:
            return None, errors

        action_id = str(uuid.uuid4())
        record = {"user_id": str(user.pk), "action": action,
                  "payload": _json_safe({"data": data, "target_id": target_id,
                                          "ids": ids, "bulk_action": bulk_action})}
        cache.set(_cache_key(action_id), record, ACTION_TTL_SECONDS)
        return {"action_id": action_id, "action": action, "details": record["payload"],
                "expires_in_seconds": ACTION_TTL_SECONDS,
                "confirmation_path": f"/api/assistant/admin/actions/{action_id}/confirm/"}, None

    @staticmethod
    def confirm(user, action_id):
        if not user.is_active or user.role not in {user.ROLE_ADMIN, user.ROLE_STAFF}:
            return None, {"permission": "Admin access required"}
        key = _cache_key(action_id)
        record = cache.get(key)
        if not record or record["user_id"] != str(user.pk):
            return None, {"action": "Pending action not found or expired"}
        used_key = f"{key}:used"
        if not cache.add(used_key, True, ACTION_TTL_SECONDS):
            return None, {"action": "Action has already been confirmed"}
        with transaction.atomic():
            result, errors = AdminProductActionService._execute(user, record)
        cache.delete(key)
        return result, errors

    @staticmethod
    def _execute(user, record):
        action = record["action"]
        payload = record["payload"]
        data, target_id, ids = payload["data"], payload["target_id"], payload["ids"]
        bulk_action = payload["bulk_action"]

        if action == "create_product":
            data, errors = validate_product_create(data, is_admin=True)
            if errors:
                return None, errors
            obj, errors = AdminProductService.create_product(data, user)
        elif action == "update_product":
            data, errors = validate_product_update(data, is_admin=True)
            if errors:
                return None, errors
            obj, errors = AdminProductService.update_product(target_id, data, user)
        elif action == "create_variant":
            data, errors = validate_variant_create(data, is_admin=True)
            if errors:
                return None, errors
            obj, errors = AdminProductService.create_variant(target_id, data, user)
        elif action == "update_variant":
            data, errors = validate_variant_update(data, is_admin=True)
            if errors:
                return None, errors
            obj, errors = AdminProductService.update_variant(target_id, data, user)
        elif action == "create_category":
            obj, errors = CategoryService.create_category(user=user, **data)
        elif action == "update_category":
            obj, errors = CategoryService.update_category(target_id, data, user=user)
        elif action == "bulk_products":
            result, errors = ProductService.bulk_action_products(ids, bulk_action, user)
            return result, errors
        elif action == "bulk_categories":
            result, errors = CategoryService.bulk_action_categories(ids, bulk_action, user=user)
            return result, errors
        elif action == "bulk_variants":
            return AdminProductActionService._bulk_variants(ids, bulk_action)
        else:
            return None, {"action": "Unsupported action"}
        return ({"id": str(obj.pk), "name": getattr(obj, "title", getattr(obj, "name", getattr(obj, "sku", "")))}
                if obj else None), errors

    @staticmethod
    def _bulk_variants(ids, action):
        result = {"success": [], "failed": [], "total": len(ids)}
        for variant_id in ids:
            variant = ProductVariant.objects.filter(pk=variant_id).first()
            if not variant:
                result["failed"].append({"id": variant_id, "reason": "Variant not found"})
                continue
            if action == "delete":
                variant.delete()
            else:
                if action == "set_default":
                    ProductVariant.objects.filter(product=variant.product, is_default=True).update(is_default=False)
                    variant.is_default = True
                elif action == "unset_default":
                    variant.is_default = False
                else:
                    variant.is_active = action == "activate"
                variant.save()
            result["success"].append({"id": variant_id, "sku": variant.sku})
        return result, None
