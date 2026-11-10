"""Search the verified catalog, with semantic discovery when keywords miss."""
import logging
from apps.ai_assistant.features import enabled
from apps.products.services.product_service import ProductService
from apps.ai_assistant.embeddings.search import search_product_embeddings

logger = logging.getLogger(__name__)


def search_catalog(query: str, page: int = 1, limit: int = 20):
    result = ProductService.get_public_products(search=query, page=page, limit=limit)
    if result[1]:
        return result
    try:
        if not enabled("semantic_search"):
            return result
        candidates = search_product_embeddings(query, limit=200)
        if candidates:
            return ProductService.get_public_products(
                product_ids=[item["product_id"] for item in candidates],
                preserve_order=True, page=page, limit=limit,
            )
    except Exception:
        logger.exception("Semantic discovery unavailable; retaining keyword results")
    return result
