"""Invalidate cached storefront product listings after catalog writes."""

from django.conf import settings
from django.db import transaction

from apps.common.revalidation import notify_storefronts, storefront_revalidation_url


def notify_product_change(categories_changed=False):
    url = storefront_revalidation_url("products")
    notify_storefronts([url] if url else [], {"categories_changed": categories_changed})


def schedule_product_revalidation(categories_changed=False, using=None):
    if not storefront_revalidation_url("products") or not settings.REVALIDATE_SECRET:
        return
    transaction.on_commit(
        lambda: notify_product_change(categories_changed),
        using=using,
        robust=True,
    )
