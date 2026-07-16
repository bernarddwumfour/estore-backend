"""
Shared caching wrapper for analytics selector calls.

Analytics aggregates are expensive to compute and don't need to be
real-time — this wraps a selector call in cache.get_or_set, keyed by
endpoint action + sorted query params, backed by the same Redis cache
already used for rate-limiting (django-redis, settings.CACHES['default']).
"""

from typing import Any, Callable
from django.core.cache import cache

DEFAULT_TIMEOUT = 60 * 10  # 10 minutes — long enough to matter, short enough to stay fresh


def analytics_cache_key(app_name: str, action: str, **params: Any) -> str:
    """Build a stable cache key from endpoint action + sorted query params."""
    parts = [f"analytics:{app_name}:{action}"]
    for key in sorted(params):
        value = params[key]
        if value is not None and value != "":
            parts.append(f"{key}={value}")
    return ":".join(parts)


def cached_analytics(
    app_name: str,
    action: str,
    compute_fn: Callable[[], Any],
    timeout: int = DEFAULT_TIMEOUT,
    **key_params: Any,
) -> Any:
    """Get-or-compute-and-cache an analytics aggregate.

    `key_params` should be the raw query-string values (not parsed
    datetimes/objects) so the cache key stays stable and human-readable —
    pass e.g. start_date_str/end_date_str, not the parsed datetime.
    """
    key = analytics_cache_key(app_name, action, **key_params)
    return cache.get_or_set(key, compute_fn, timeout=timeout)
