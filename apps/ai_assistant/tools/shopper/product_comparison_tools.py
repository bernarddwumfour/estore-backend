import json
import logging
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field, field_validator

from apps.products.services.product_service import ProductService


logger = logging.getLogger(__name__)

MAX_COMPARISON_PRODUCTS = 4


class ProductComparisonInput(BaseModel):
    """Input schema for comparing store products."""

    product_slugs: list[str] = Field(
        ...,
        min_length=2,
        max_length=MAX_COMPARISON_PRODUCTS,
        description=(
            "List of 2 to 4 exact product slugs. "
            "Obtain slugs from search_products or verified "
            "product details. Never invent product slugs."
        ),
    )

    @field_validator("product_slugs")
    @classmethod
    def validate_slugs(cls, slugs: list[str]) -> list[str]:
        cleaned = [slug.strip() for slug in slugs]

        if any(not slug for slug in cleaned):
            raise ValueError("Product slugs cannot be empty.")

        if len(set(cleaned)) != len(cleaned):
            raise ValueError("Duplicate products are not allowed.")

        return cleaned


def normalize_specifications(value: Any) -> dict:
    """
    Normalize product features or options into a dictionary.

    Supports dictionaries and lists without assuming a
    specific product niche or specification structure.
    """

    if isinstance(value, dict):
        return value

    if isinstance(value, list):
        result = {}

        for index, item in enumerate(value):
            if isinstance(item, dict):
                name = (
                    item.get("name")
                    or item.get("key")
                    or item.get("label")
                )

                if name:
                    result[str(name)] = (
                        item.get("value")
                        if "value" in item
                        else item
                    )
                else:
                    result[f"item_{index + 1}"] = item

            elif isinstance(item, str):
                result[f"item_{index + 1}"] = item

        return result

    return {}


def normalize_variant(variant: dict) -> dict:
    """
    Return only customer-facing variant information.

    Never expose raw stock quantities, internal cost
    prices, profit margins, or inventory valuations.
    """

    return {
        "id": variant.get("id"),
        "sku": variant.get("sku"),
        "attributes": variant.get("attributes") or {},
        "price": variant.get("price"),
        "discounted_price": variant.get("discounted_price"),
        "discount_percentage": variant.get("discount_percentage"),
        "is_in_stock": variant.get("is_in_stock"),
        "stock_status": variant.get("stock_status"),
        "is_default": variant.get("is_default"),
    }

def normalize_product(product: dict) -> dict:
    """Normalize public product information for comparison."""

    variants = [
        normalize_variant(variant)
        for variant in product.get("variants") or []
        if isinstance(variant, dict)
    ]

    return {
        "id": product.get("id"),
        "title": product.get("title"),
        "slug": product.get("slug"),
        "description": product.get("description"),
        "category": product.get("category"),
        "features": normalize_specifications(
            product.get("features")
        ),
        "options": normalize_specifications(
            product.get("options")
        ),
        "min_price": product.get("min_price"),
        "max_price": product.get("max_price"),
        "average_rating": product.get("average_rating"),
        "total_reviews": product.get("total_reviews"),
        "has_stock": product.get("has_stock"),
        "variants": variants,
    }


def build_specification_matrix(products: list[dict]) -> list[dict]:
    """
    Build a cross-product specification matrix.

    Missing values remain null instead of being invented.
    """

    specification_keys = set()

    for product in products:
        specification_keys.update(product["features"].keys())
        specification_keys.update(product["options"].keys())

    matrix = []

    for key in sorted(specification_keys):
        values = {}

        for product in products:
            value = product["features"].get(key)

            if value is None:
                value = product["options"].get(key)

            values[product["slug"]] = value

        matrix.append({
            "specification": key,
            "values": values,
        })

    return matrix


@tool(args_schema=ProductComparisonInput)
def compare_products(product_slugs: list[str]) -> str:
    """
    Compare 2 to 4 verified products from the store.

    Use when a customer asks to compare products,
    understand their differences, or decide which
    product better suits their preferences.

    Product slugs must be obtained from verified
    product search results.
    """

    try:
        products = []
        unavailable = []

        for slug in product_slugs:
            product = ProductService.get_product_detail(
                slug=slug,
                is_admin=False,
            )

            if not product:
                unavailable.append(slug)
                continue

            products.append(normalize_product(product))

        if unavailable:
            return json.dumps({
                "success": False,
                "error": (
                    "One or more requested products "
                    "could not be found."
                ),
                "unavailable_products": unavailable,
                "found_products": [
                    {
                        "title": product["title"],
                        "slug": product["slug"],
                    }
                    for product in products
                ],
            })

        comparison = {
            "success": True,
            "total": len(products),
            "products": products,
            "specification_matrix": (
                build_specification_matrix(products)
            ),
        }

        return json.dumps(comparison, default=str)

    except Exception:
        logger.exception("AI product comparison failed")

        return json.dumps({
            "success": False,
            "error": (
                "Product comparison is temporarily unavailable."
            ),
        })