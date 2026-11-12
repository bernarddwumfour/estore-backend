"""Notify storefronts to refresh cached public blog data after commit."""

from django.conf import settings
from django.db import transaction

from apps.common.revalidation import notify_storefronts, storefront_revalidation_url


def notify_blog_change(slugs):
    url = storefront_revalidation_url("blog")
    notify_storefronts([url] if url else [], {"slugs": sorted(set(slugs))})


def schedule_blog_revalidation(slugs, using=None):
    if not storefront_revalidation_url("blog") or not settings.REVALIDATE_SECRET:
        return
    slugs = tuple(sorted(set(slugs)))
    transaction.on_commit(lambda: notify_blog_change(slugs), using=using, robust=True)
