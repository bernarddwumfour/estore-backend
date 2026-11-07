"""Read-only product management tools. Every invocation checks the caller's role."""

import json
from uuid import UUID

from django.contrib.auth import get_user_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.products.models import Category, Product, ProductVariant
from apps.products.schemas import serialize_product, serialize_category, serialize_variant
from apps.products.selectors.category_selectors import get_all_categories
from apps.products.services.product_service import ProductService

User = get_user_model()


def _authorized(config: RunnableConfig) -> bool:
    user_id = (config.get("configurable") or {}).get("authenticated_user_id")
    return bool(user_id and User.objects.filter(
        pk=user_id, is_active=True, role__in=[User.ROLE_ADMIN, User.ROLE_STAFF]
    ).exists())


def _result(config: RunnableConfig, data=None, error=None) -> str:
    if not _authorized(config):
        return json.dumps({"success": False, "error": "Admin access required."})
    return json.dumps({"success": error is None, "data": data, "error": error}, default=str)


class ProductSearchInput(BaseModel):
    search: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, description="draft, published, or archived")
    category_id: UUID | None = None
    has_stock: bool | None = None
    is_featured: bool | None = None
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=20)


@tool(args_schema=ProductSearchInput)
def search_admin_products(search: str | None = None, status: str | None = None,
                          category_id: UUID | None = None, has_stock: bool | None = None,
                          is_featured: bool | None = None, min_price: float | None = None,
                          max_price: float | None = None, page: int = 1, limit: int = 10,
                          config: RunnableConfig = None) -> str:
    """Search the full admin catalog, including unpublished products."""
    if not _authorized(config or {}):
        return _result(config or {})
    if status and status not in {"draft", "published", "archived"}:
        return _result(config, error="Invalid product status.")
    if min_price is not None and max_price is not None and min_price > max_price:
        return _result(config, error="Minimum price exceeds maximum price.")
    products, total, pagination = ProductService.get_admin_products(
        page=page, limit=limit, search=search, status=status,
        category_id=str(category_id) if category_id else None,
        has_stock=has_stock, is_featured=is_featured,
        min_price=min_price, max_price=max_price,
    )
    return _result(config, {"products": products, "total": total, "pagination": pagination})


class ProductDetailInput(BaseModel):
    product_id: UUID


@tool(args_schema=ProductDetailInput)
def get_admin_product(product_id: UUID, config: RunnableConfig) -> str:
    """Get an admin product by ID with its variants and private catalog fields."""
    if not _authorized(config):
        return _result(config)
    product = Product.objects.prefetch_related("variants__images").filter(pk=product_id).first()
    if not product:
        return _result(config, error="Product not found.")
    return _result(config, serialize_product(product, is_admin=True))


class VariantDetailInput(BaseModel):
    variant_id: UUID


@tool(args_schema=VariantDetailInput)
def get_admin_variant(variant_id: UUID, config: RunnableConfig) -> str:
    """Get full variant pricing, stock, cost, attributes, and image metadata."""
    if not _authorized(config):
        return _result(config)
    variant = ProductVariant.objects.select_related("product").filter(pk=variant_id).first()
    if not variant:
        return _result(config, error="Variant not found.")
    return _result(config, serialize_variant(variant, is_admin=True))


class VariantListInput(BaseModel):
    search: str | None = Field(default=None, max_length=100, description="SKU or variant search")
    product_id: UUID | None = None
    in_stock: bool | None = None
    is_active: bool | None = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=10, ge=1, le=20)


@tool(args_schema=VariantListInput)
def list_admin_variants(search: str | None = None, product_id: UUID | None = None,
                        in_stock: bool | None = None, is_active: bool | None = None,
                        page: int = 1, limit: int = 10,
                        config: RunnableConfig = None) -> str:
    """List variants across the admin catalog, including inactive variants."""
    if not _authorized(config or {}):
        return _result(config or {})
    variants, total, pagination = ProductService.get_all_variants(
        page=page, limit=limit, search=search,
        product_id=str(product_id) if product_id else None,
        in_stock=in_stock, is_active=is_active, is_admin=True,
    )
    return _result(config, {"variants": variants, "total": total, "pagination": pagination})


class CategoryListInput(BaseModel):
    search: str | None = Field(default=None, max_length=100)
    limit: int = Field(default=20, ge=1, le=50)


@tool(args_schema=CategoryListInput)
def list_admin_categories(search: str | None = None, limit: int = 20,
                           config: RunnableConfig = None) -> str:
    """List active, inactive, visible, and hidden product categories."""
    if not _authorized(config or {}):
        return _result(config or {})
    categories, total, pagination = get_all_categories(
        only_active=False, is_admin=True, search=search, limit=limit,
    )
    return _result(config, {"categories": [serialize_category(c, is_admin=True) for c in categories],
                            "total": total, "pagination": pagination})


class CategoryDetailInput(BaseModel):
    category_id: UUID


@tool(args_schema=CategoryDetailInput)
def get_admin_category(category_id: UUID, config: RunnableConfig) -> str:
    """Get a category including hidden and inactive settings."""
    if not _authorized(config):
        return _result(config)
    category = Category.objects.select_related("parent").filter(pk=category_id).first()
    if not category:
        return _result(config, error="Category not found.")
    return _result(config, serialize_category(category, is_admin=True))


class InventoryInput(BaseModel):
    limit: int = Field(default=20, ge=1, le=50)


@tool(args_schema=InventoryInput)
def get_inventory_health(limit: int = 20, config: RunnableConfig = None) -> str:
    """Find out-of-stock and low-stock active variants across the full catalog."""
    if not _authorized(config or {}):
        return _result(config or {})
    variants = ProductVariant.objects.filter(is_active=True).select_related("product")
    from django.db.models import F, Q
    at_risk = variants.filter(Q(stock=0) | Q(stock__lte=F("low_stock_threshold")))
    total = at_risk.count()
    items = [{"variant_id": str(v.id), "product_id": str(v.product_id),
              "product": v.product.title, "sku": v.sku, "stock": v.stock,
              "threshold": v.low_stock_threshold, "status": "out_of_stock" if v.stock == 0 else "low_stock"}
             for v in at_risk.order_by("stock", "sku")[:limit]]
    return _result(config, {"items": items, "total_at_risk": total,
                            "total_active_variants": variants.count()})
