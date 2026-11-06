
import json
import logging
import re
from typing import Any, Optional

from langchain_core.tools import tool
from pydantic import BaseModel, Field, model_validator

from apps.products.services.product_service import ProductService
from apps.ai_assistant.embeddings.search import search_product_embeddings


logger = logging.getLogger(__name__)


class ProductSearchInput(BaseModel):
    """Validated arguments for searching public store products."""

    search: Optional[str] = Field(
        default=None,
        description="Product name, description, or keyword to search for.",
        max_length=200,
    )

    category_slug: Optional[str] = Field(
        default=None,
        description="Category slug to filter products by.",
        max_length=150,
    )

    brand: Optional[str] = Field(
        default=None,
        description="Brand name to filter products by.",
        max_length=100,
    )

    min_price: Optional[float] = Field(
        default=None,
        description="Minimum product price.",
        ge=0,
    )

    max_price: Optional[float] = Field(
        default=None,
        description="Maximum product price.",
        ge=0,
    )

    in_stock: Optional[bool] = Field(
        default=None,
        description="Whether to return only products currently in stock.",
    )

    featured: Optional[bool] = Field(default=None)
    bestseller: Optional[bool] = Field(default=None)
    new: Optional[bool] = Field(default=None)

    sort_by: str = Field(
        default="newest",
        description=(
            "Sorting option: price_asc, price_desc, rating, newest, "
            "oldest, name_asc, or name_desc."
        ),
    )

    page: int = Field(default=1, ge=1)

    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="Maximum number of products to return.",
    )

    @model_validator(mode="after")
    def validate_price_range(self):
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError(
                "Minimum price cannot exceed maximum price."
            )

        return self


ALLOWED_SORT_OPTIONS = {
    "price_asc",
    "price_desc",
    "rating",
    "newest",
    "oldest",
    "name_asc",
    "name_desc",
}


def get_product_image(product: dict[str, Any]) -> str | None:
    """
    Extract the first available image URL from the
    product's public variant data.

    Prefer the default variant, then fall back to
    another variant with images.
    """

    def first_image_url(variant):
        if not isinstance(variant, dict):
            return None

        images = variant.get("images") or []

        for image in images:
            if not isinstance(image, dict):
                continue

            url = image.get("url")

            if isinstance(url, str) and url:
                return url

        return None

    default_variant = product.get("default_variant")

    url = first_image_url(default_variant)

    if url:
        return url

    for variant in product.get("variants") or []:
        url = first_image_url(variant)

        if url:
            return url

    return None



def serialize_assistant_variant(
    variant: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Serialize only the variant fields needed by
    the chatbot's cart and wishlist actions.
    """

    if not isinstance(variant, dict):
        return None

    variant_id = variant.get("id")
    sku = variant.get("sku")

    if not variant_id or not sku:
        return None

    images = variant.get("images") or []

    image_url = next(
        (
            image.get("url")
            for image in images
            if isinstance(image, dict)
            and isinstance(image.get("url"), str)
            and image.get("url")
        ),
        None,
    )

    return {
        "id": str(variant_id),
        "sku": str(sku),
        "attributes": variant.get("attributes") or {},
        "price": variant.get("price"),
        "discounted_price": variant.get(
            "discounted_price"
        ),
        "is_in_stock": bool(
            variant.get("is_in_stock", False)
        ),
        "image": image_url,
    }



def serialize_assistant_product(
    product: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert a public product into a lightweight
    assistant product card with selectable variants.
    """

    variants = []

    seen_variant_ids = set()

    # Include the default variant first.
    raw_variants = [
        product.get("default_variant"),
        *(product.get("variants") or []),
    ]

    for variant in raw_variants:
        serialized = serialize_assistant_variant(variant)

        if serialized is None:
            continue

        variant_id = serialized["id"]

        if variant_id in seen_variant_ids:
            continue

        seen_variant_ids.add(variant_id)
        variants.append(serialized)

    return {
        "id": str(product["id"]),
        "title": product["title"],
        "slug": product["slug"],
        "min_price": product.get("min_price"),
        "max_price": product.get("max_price"),
        "has_stock": bool(
            product.get("has_stock", False)
        ),
        "image": get_product_image(product),
        # Resolved only when the requested model/configuration matches an
        # actual catalog variant, otherwise the UI asks the customer to choose.
        "selected_variant_id": product.get("selected_variant_id"),
        "variants": variants,
    }


def select_exact_variant_cards(products: list[dict], search: Optional[str]) -> list[dict]:
    """Narrow explicit colour/model searches to the matching card and variant.

    Product search intentionally has broad recall. The assistant UI should not,
    however, show a customer asking for "pink iPhone 13" an unrelated iPhone
    or silently select the parent product's default configuration.
    """
    if not search:
        return products

    tokens = set(re.findall(r"[a-z0-9]+", search.lower()))
    if not tokens:
        return products

    exact_cards = []
    for product in products:
        product_tokens = set(re.findall(r"[a-z0-9]+", product.get("title", "").lower()))
        query_mentions_product = bool(product_tokens & tokens)
        matching_variants = []
        for variant in product.get("variants", []):
            attribute_tokens = set()
            for value in (variant.get("attributes") or {}).values():
                attribute_tokens.update(re.findall(r"[a-z0-9]+", str(value).lower()))
            requested_attributes = tokens & attribute_tokens
            # Do not treat model words/numbers as variant choices. A color or
            # storage token that appears in variant data is a strong selector.
            if query_mentions_product and requested_attributes:
                matching_variants.append(variant)

        if matching_variants:
            product["selected_variant_id"] = matching_variants[0]["id"]
            exact_cards.append(product)

    return exact_cards or products



@tool(args_schema=ProductSearchInput)
def search_products(
    search: Optional[str] = None,
    category_slug: Optional[str] = None,
    brand: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    in_stock: Optional[bool] = None,
    featured: Optional[bool] = None,
    bestseller: Optional[bool] = None,
    new: Optional[bool] = None,
    sort_by: str = "newest",
    page: int = 1,
    limit: int = 5,
) -> str:
    """
    Search published products using keyword search first,
    followed by semantic search when no matches are found.
    """
    
    logger.info(
    "AI PRODUCT SEARCH CALLED | search=%r | category=%r | "
    "brand=%r | in_stock=%r | page=%s | limit=%s",
    search,
    category_slug,
    brand,
    in_stock,
    page,
    limit,
)

    if (
        min_price is not None
        and max_price is not None
        and min_price > max_price
    ):
        return json.dumps({
            "success": False,
            "error": "Minimum price cannot exceed maximum price.",
        })

    if sort_by not in ALLOWED_SORT_OPTIONS:
        return json.dumps({
            "success": False,
            "error": "Unsupported sorting option.",
        })

    try:
        filters = {
            "page": page,
            "limit": limit,
            "category_slug": category_slug,
            "brand": brand,
            "min_price": min_price,
            "max_price": max_price,
            "in_stock": in_stock,
            "featured": featured,
            "bestseller": bestseller,
            "new": new,
            "sort_by": sort_by,
            "is_admin": False,
        }

        # 1. Existing keyword search.
        products, total, pagination = (
            ProductService.get_public_products(
                **filters,
                search=search,
            )
        )

        # 2. Semantic fallback.
        if total == 0 and search and search.strip():
            try:
                from django.conf import settings

                candidates = search_product_embeddings(
                    query=search,
                    limit=getattr(
                        settings,
                        "AI_SEMANTIC_CANDIDATE_LIMIT",
                        100,
                    ),
                )

                product_ids = [
                    candidate["product_id"]
                    for candidate in candidates
                ]

                if product_ids:
                    products, total, pagination = (
                        ProductService.get_public_products(
                            **filters,
                            search=None,
                            product_ids=product_ids,
                            preserve_order=(sort_by == "newest"),
                        )
                    )

            except Exception:
                logger.exception(
                    "Semantic search failed; "
                    "using keyword search results"
                )

        # 3. Preserve the existing product-card format.
        product_cards = [
            serialize_assistant_product(product)
            for product in products
        ]
        product_cards = select_exact_variant_cards(product_cards, search)
        
        logger.info(
    "AI PRODUCT SEARCH RESULT | search=%r | total=%s | products=%s",
    search,
    total,
    [product["title"] for product in product_cards],
)

        return json.dumps(
            {
                "success": True,
                "total": total,
                "pagination": pagination,
                "products": product_cards,
            },
            default=str,
        )

    except Exception:
        logger.exception("AI product search failed")
        
        return json.dumps({
            "success": False,
            "error": "Product search is temporarily unavailable.",
        })
