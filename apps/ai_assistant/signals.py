"""Refresh search embeddings after catalog changes are committed."""

import logging

from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.products.models import Product, ProductVariant

from .tasks import refresh_product_embedding

logger = logging.getLogger(__name__)


def schedule_refresh(product_id, using):
    def enqueue():
        try:
            refresh_product_embedding.delay(str(product_id))
        except Exception:
            # A broker/provider outage must not make a committed catalog edit fail.
            # The periodic reconciliation will pick it up later.
            logger.exception("Could not enqueue embedding refresh for product %s", product_id)

    transaction.on_commit(enqueue, using=using)


@receiver(post_save, sender=Product, dispatch_uid="embedding_product_saved")
def product_saved(sender, instance, using, **kwargs):
    schedule_refresh(instance.pk, using)


@receiver(post_save, sender=ProductVariant, dispatch_uid="embedding_variant_saved")
def variant_saved(sender, instance, using, **kwargs):
    schedule_refresh(instance.product_id, using)


@receiver(post_delete, sender=ProductVariant, dispatch_uid="embedding_variant_deleted")
def variant_deleted(sender, instance, using, **kwargs):
    schedule_refresh(instance.product_id, using)
