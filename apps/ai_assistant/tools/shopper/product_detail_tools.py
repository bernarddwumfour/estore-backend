import json
import logging

from typing import Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.products.services.product_service import ProductService


logger = logging.getLogger(__name__)


class ProductDetailInput(BaseModel):
    """Input schema for retrieving a product's details."""

    slug: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description=(
            "Exact product slug obtained from search_products "
            "or a product URL. Do not invent slugs."
        ),
    )

def serialize_assistant_product_details(product: dict) -> dict:
    """
    Serialize customer-facing product details.

    Only expose public product and variant information.
    Never include raw stock quantities, cost prices,
    profit margins, or administrative fields.
    """

    variants = []

    for variant in product.get("variants") or []:
        if not isinstance(variant, dict):
            continue

        variants.append({
    "id": variant.get("id"),
    "sku": variant.get("sku"),
    "attributes": variant.get("attributes") or {},
    "price": variant.get("price"),
    "discounted_price": variant.get("discounted_price"),
    "discount_percentage": variant.get("discount_percentage"),
    "discount_amount": variant.get("discount_amount"),
    "is_in_stock": variant.get("is_in_stock"),
    "stock_status": variant.get("stock_status"),
    "is_default": variant.get("is_default"),
    "images": [
        {
            "url": image.get("url"),
            "alt_text": image.get("alt_text"),
        }
        for image in variant.get("images") or []
        if isinstance(image, dict)
    ],
})
    related_products = []

    for related in product.get("related_products") or []:
        if not isinstance(related, dict):
            continue

        related_products.append({
            "id": related.get("id"),
            "title": related.get("title"),
            "slug": related.get("slug"),
            "min_price": related.get("min_price"),
            "max_price": related.get("max_price"),
            "has_stock": related.get("has_stock"),
        })

    return {
        "id": product.get("id"),
        "title": product.get("title"),
        "slug": product.get("slug"),
        "description": product.get("description"),
        "category": product.get("category"),
        "features": product.get("features"),
        "options": product.get("options"),
        "average_rating": product.get("average_rating"),
        "total_reviews": product.get("total_reviews"),
        "min_price": product.get("min_price"),
        "max_price": product.get("max_price"),
        "has_stock": product.get("has_stock"),
        "variants": variants,
        "related_products": related_products[:5],
    }
    

@tool(args_schema=ProductDetailInput)
def get_product_details(slug: str) -> str:
    """
    Retrieve detailed public information about a store product.

    Use this tool when a customer asks about a specific product,
    its features, specifications, price, available variants,
    or related products.

    The slug must come from a verified product search result
    or product URL.
    """

    try:
        product = ProductService.get_product_detail(
            slug=slug,
            is_admin=False,
        )

        if not product:
            return json.dumps({
                "success": False,
                "error": "Product not found or unavailable.",
            })

        return json.dumps(
            {
                "success": True,
                "product": serialize_assistant_product_details(
                    product
                ),
            },
            default=str,
        )

    except Exception:
        logger.exception(
            "AI product detail retrieval failed"
        )

        return json.dumps({
            "success": False,
            "error": (
                "Product details are temporarily unavailable."
            ),
        })