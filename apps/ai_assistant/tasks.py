"""Background maintenance for the product semantic search index."""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True,
             retry_backoff_max=600, retry_jitter=True, max_retries=5)
def refresh_product_embedding(self, product_id):
    from .embeddings.indexer import index_product

    return index_product(product_id)


@shared_task
def reconcile_product_embeddings():
    """Repair missed updates, including products that are no longer published."""
    from apps.products.models import Product
    from .models import ProductEmbedding

    ProductEmbedding.objects.exclude(product__status=Product.STATUS_PUBLISHED).delete()
    product_ids = Product.objects.filter(status=Product.STATUS_PUBLISHED).values_list("pk", flat=True)
    queued = 0
    for product_id in product_ids.iterator():
        try:
            refresh_product_embedding.delay(str(product_id))
            queued += 1
        except Exception:
            logger.exception("Could not refresh embedding for product %s", product_id)
    return {"queued": queued}
