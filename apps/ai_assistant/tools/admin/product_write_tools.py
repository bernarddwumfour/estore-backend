"""Prepare product changes; only the separate confirmation endpoint writes data."""

import json
from typing import Any, Literal
from uuid import UUID

from django.contrib.auth import get_user_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.ai_assistant.services.admin_product_action_service import AdminProductActionService

User = get_user_model()


def _prepare(config, action, payload):
    user_id = (config.get("configurable") or {}).get("authenticated_user_id")
    user = User.objects.filter(pk=user_id, is_active=True,
                               role__in=[User.ROLE_ADMIN, User.ROLE_STAFF]).first() if user_id else None
    if not user:
        return json.dumps({"success": False, "error": "Admin access required"})
    result, errors = AdminProductActionService.prepare(user, action, payload)
    return json.dumps({"success": errors is None, "pending_action": result, "errors": errors}, default=str)


class ProductCreateInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    category_id: UUID
    features: list[Any] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "published", "archived"] = "draft"
    is_featured: bool = False
    is_bestseller: bool = False
    is_new: bool = False


@tool(args_schema=ProductCreateInput)
def create_admin_product(title: str, description: str, category_id: UUID,
                         features: list[Any] = None, options: dict[str, Any] = None,
                         status: str = "draft", is_featured: bool = False,
                         is_bestseller: bool = False, is_new: bool = False,
                         config: RunnableConfig = None) -> str:
    """Prepare a new product. A human must confirm the returned action ID."""
    return _prepare(config or {}, "create_product", {"data": {
        "title": title, "description": description, "category_id": str(category_id),
        "features": features or [], "options": options or {}, "status": status,
        "is_featured": is_featured, "is_bestseller": is_bestseller, "is_new": is_new,
    }})


class ProductUpdateInput(BaseModel):
    product_id: UUID
    changes: dict[str, Any] = Field(description="Product fields to change: title, description, category_id, features, options, status, flags, or SEO fields")


@tool(args_schema=ProductUpdateInput)
def update_admin_product(product_id: UUID, changes: dict[str, Any],
                         config: RunnableConfig) -> str:
    """Prepare product edits, including publication status and feature flags."""
    return _prepare(config, "update_product", {"target_id": str(product_id), "data": changes})


class VariantCreateInput(BaseModel):
    product_id: UUID
    sku: str = Field(min_length=1, max_length=100)
    price: float = Field(gt=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    stock: int = Field(default=0, ge=0)
    discount_amount: float = Field(default=0, ge=0)
    cost_price: float | None = Field(default=None, ge=0)
    is_default: bool = False
    is_active: bool = True
    low_stock_threshold: int = Field(default=5, ge=0)


@tool(args_schema=VariantCreateInput)
def create_admin_variant(product_id: UUID, sku: str, price: float,
                         attributes: dict[str, Any] = None, stock: int = 0,
                         discount_amount: float = 0, cost_price: float | None = None,
                         is_default: bool = False, is_active: bool = True,
                         low_stock_threshold: int = 5,
                         config: RunnableConfig = None) -> str:
    """Prepare a product variant with price, stock, and SKU."""
    data = {"sku": sku, "price": price, "attributes": attributes or {},
            "stock": stock, "discount_amount": discount_amount,
            "is_default": is_default, "is_active": is_active,
            "low_stock_threshold": low_stock_threshold}
    if cost_price is not None:
        data["cost_price"] = cost_price
    return _prepare(config or {}, "create_variant", {"target_id": str(product_id), "data": data})


class VariantUpdateInput(BaseModel):
    variant_id: UUID
    changes: dict[str, Any] = Field(description="Variant fields to change: SKU, price, discount, cost, stock, attributes, activation, default, or dimensions")


@tool(args_schema=VariantUpdateInput)
def update_admin_variant(variant_id: UUID, changes: dict[str, Any],
                         config: RunnableConfig) -> str:
    """Prepare a variant price, stock, SKU, or attribute update."""
    return _prepare(config, "update_variant", {"target_id": str(variant_id), "data": changes})


class CategoryCreateInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    parent_id: UUID | None = None
    is_active: bool = True
    is_hidden: bool = False


@tool(args_schema=CategoryCreateInput)
def create_admin_category(name: str, description: str = "", parent_id: UUID | None = None,
                          is_active: bool = True, is_hidden: bool = False,
                          config: RunnableConfig = None) -> str:
    """Prepare a category, optionally nested under an existing category."""
    return _prepare(config or {}, "create_category", {"data": {
        "name": name, "description": description,
        "parent_id": str(parent_id) if parent_id else None,
        "is_active": is_active, "is_hidden": is_hidden,
    }})


class CategoryUpdateInput(BaseModel):
    category_id: UUID
    changes: dict[str, Any] = Field(description="Category fields to change: name, description, parent_id, active or hidden flags, or SEO fields")


@tool(args_schema=CategoryUpdateInput)
def update_admin_category(category_id: UUID, changes: dict[str, Any],
                          config: RunnableConfig) -> str:
    """Prepare a category name, parent, visibility, or metadata update."""
    return _prepare(config, "update_category", {"target_id": str(category_id), "data": changes})


class BulkInput(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=20)
    action: str


@tool(args_schema=BulkInput)
def bulk_admin_products(ids: list[UUID], action: str, config: RunnableConfig) -> str:
    """Prepare up to 20 product status, flag, or delete changes."""
    return _prepare(config, "bulk_products", {"ids": [str(i) for i in ids], "bulk_action": action})


@tool(args_schema=BulkInput)
def bulk_admin_variants(ids: list[UUID], action: str, config: RunnableConfig) -> str:
    """Prepare up to 20 variant activation, default, or delete changes."""
    return _prepare(config, "bulk_variants", {"ids": [str(i) for i in ids], "bulk_action": action})


@tool(args_schema=BulkInput)
def bulk_admin_categories(ids: list[UUID], action: str, config: RunnableConfig) -> str:
    """Prepare up to 20 category activation, visibility, or delete changes."""
    return _prepare(config, "bulk_categories", {"ids": [str(i) for i in ids], "bulk_action": action})
