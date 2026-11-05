import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from pgvector.django import CosineDistance

from apps.ai_assistant.models import ProductEmbedding
from apps.ai_assistant.embeddings.provider import (
    embed_query,
    get_embedding_model_name,
    get_embedding_dimensions,
)

logger = logging.getLogger(__name__)


def get_cached_query_embedding(query: str) -> list[float]:
    """
    Return a cached query embedding when available.

    Cache keys include the embedding model and dimensions
    to prevent incompatible vectors from being reused.
    """
    normalized_query = " ".join(query.strip().lower().split())

    if not normalized_query:
        raise ValueError("Search query cannot be empty.")

    model_name = get_embedding_model_name()
    dimensions = get_embedding_dimensions()

    payload = f"{model_name}:{dimensions}:{normalized_query}"

    cache_key = (
        "ai:semantic:query:"
        + hashlib.sha256(payload.encode("utf-8")).hexdigest()
    )

    cached = cache.get(cache_key)

    if cached is not None:
        return cached

    embedding = embed_query(normalized_query)

    cache.set(
        cache_key,
        embedding,
        timeout=getattr(
            settings,
            "AI_EMBEDDING_CACHE_TTL",
            86400,
        ),
    )

    return embedding

def search_product_embeddings(
    query: str,
    limit: int = 100,
    min_similarity: float | None = None,
) -> list[dict]:
    """
    Retrieve semantic candidates using a minimum score
    and a relative score margin.

    Results are candidate IDs, not verified product cards.
    """

    if not query or not query.strip():
        return []

    limit = max(1, min(limit, 200))

    minimum = (
        min_similarity
        if min_similarity is not None
        else settings.AI_SEMANTIC_MIN_SIMILARITY
    )

    margin = settings.AI_SEMANTIC_SCORE_MARGIN

    query_vector = get_cached_query_embedding(query)

    candidates = list(
        ProductEmbedding.objects
        .filter(
            model_name=get_embedding_model_name(),
            product__status="published",
        )
        .annotate(
            distance=CosineDistance(
                "embedding",
                query_vector,
            )
        )
        .filter(
            distance__lte=1.0 - minimum,
        )
        .order_by("distance", "product_id")[:limit]
    )

    if not candidates:
        return []

    best_similarity = 1.0 - float(candidates[0].distance)

    cutoff = max(
        minimum,
        best_similarity - margin,
    )

    results = []

    for candidate in candidates:
        similarity = 1.0 - float(candidate.distance)

        if similarity < cutoff:
            continue

        results.append({
            "product_id": str(candidate.product_id),
            "similarity": round(similarity, 4),
        })

    return results