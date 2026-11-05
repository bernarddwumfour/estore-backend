import hashlib
import json
import logging

from django.db import transaction

from apps.products.models import Product
from apps.ai_assistant.models import ProductEmbedding

from .provider import (
    embed_document,
    get_embedding_model_name,
)

logger = logging.getLogger(__name__)


def build_product_search_text(product: Product) -> str:
    """
    Build searchable text for any product niche.

    Only include product information useful for
    semantic discovery.
    """

    parts = [
        f"Product: {product.title}",
    ]

    category = product.category

    if category:
        parts.append(
            f"Category: {category.full_path}"
        )

    if product.description:
        parts.append(
            f"Description: {product.description[:1000]}"
        )

    if product.features:
        parts.append(
            "Features: "
            + json.dumps(
                product.features,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )[:1000]
        )

    if product.options:
        parts.append(
            "Options: "
            + json.dumps(
                product.options,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )[:500]
        )

    variants = product.variants.filter(
        is_active=True
    ).order_by("id")

    attributes = []

    for variant in variants:
        if variant.attributes:
            attributes.append(variant.attributes)

    if attributes:
        # Deduplicate identical variant attribute objects.
        unique_attributes = sorted({
            json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )
            for item in attributes
        })

        parts.append(
            "Variant attributes: "
            + " | ".join(unique_attributes)[:1000]
        )

    return "\n".join(parts)


def calculate_content_hash(
    text: str,
    model_name: str,
) -> str:
    payload = json.dumps(
        {
            "text": text,
            "model": model_name,
        },
        sort_keys=True,
        ensure_ascii=False,
    )

    return hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()


def index_product(product_id: str) -> dict:
    """
    Generate or update one product embedding.

    Returns a status dictionary.
    """

    product = (
        Product.objects
        .select_related("category")
        .filter(id=product_id)
        .first()
    )

    if not product:
        return {
            "status": "not_found",
            "product_id": str(product_id),
        }

    # Unpublished products should not remain in
    # the customer-facing semantic index.
    if product.status != Product.STATUS_PUBLISHED:
        ProductEmbedding.objects.filter(
            product_id=product.id
        ).delete()

        return {
            "status": "removed",
            "product_id": str(product.id),
        }

    text = build_product_search_text(product)

    model_name = get_embedding_model_name()

    content_hash = calculate_content_hash(
        text,
        model_name,
    )

    existing = ProductEmbedding.objects.filter(
        product_id=product.id
    ).first()

    if (
        existing
        and existing.content_hash == content_hash
        and existing.model_name == model_name
    ):
        return {
            "status": "unchanged",
            "product_id": str(product.id),
        }

    # External API call happens outside a database
    # transaction to avoid holding database locks.
    embedding = embed_document(text)

    with transaction.atomic():
        ProductEmbedding.objects.update_or_create(
            product_id=product.id,
            defaults={
                "embedding": embedding,
                "content_hash": content_hash,
                "model_name": model_name,
            },
        )

    logger.info(
        "Product embedding indexed: %s",
        product.id,
    )

    return {
        "status": "indexed",
        "product_id": str(product.id),
    }