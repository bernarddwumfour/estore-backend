"""Send authenticated cache invalidation callbacks without failing writes."""

import logging
from contextlib import contextmanager
from contextvars import ContextVar

import requests
from django.conf import settings

logger = logging.getLogger(__name__)
_callback_results = ContextVar("revalidation_callback_results", default=None)


def storefront_revalidation_url(kind):
    """Build a fixed callback path from this store's frontend origin."""
    base = settings.STOREFRONT_BASE_URL.strip().rstrip("/")
    if not base or not base.startswith(("http://", "https://")):
        return None
    return f"{base}/api/revalidate/{kind}"


@contextmanager
def capture_revalidation():
    """Collect synchronous post-commit callback outcomes for one admin request."""
    results = []
    token = _callback_results.set(results)
    try:
        yield results
    finally:
        _callback_results.reset(token)


def revalidation_status(results, configured):
    if not configured:
        return "unconfigured"
    if not results:
        return "pending"
    return "accepted" if all(results) else "failed"


def notify_storefronts(urls, payload):
    secret = settings.REVALIDATE_SECRET
    if not urls or not secret:
        return False

    success = True
    for url in urls:
        try:
            response = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {secret}"},
                timeout=3,
            )
            response.raise_for_status()
        except requests.RequestException:
            success = False
            logger.exception("Cache revalidation failed for %s", url)

    results = _callback_results.get()
    if results is not None:
        results.append(success)
    return success
