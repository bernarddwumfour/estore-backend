"""
Shared analytics query-param validators (date range, limit, interval).

Previously duplicated byte-for-byte across apps/products, apps/orders, and
apps/users' analytics_schemas.py — consolidated here so all three import the
same implementation.
"""

from datetime import datetime
from typing import Dict, Optional, Tuple

from django.conf import settings
from django.utils import timezone


def validate_date_range(
    start_date_str: Optional[str] = None,
    end_date_str: Optional[str] = None
) -> Tuple[Optional[datetime], Optional[datetime], Optional[Dict]]:
    """Validate date range parameters.

    Returns timezone-aware datetimes when USE_TZ is enabled — comparing a
    naive datetime against a timezone-aware DateTimeField (e.g. created_at)
    makes Django silently assume the current timezone and emit a
    RuntimeWarning, which was previously mis-filtering date-range queries.
    """
    start_date = None
    end_date = None

    if start_date_str:
        try:
            start_date = datetime.fromisoformat(start_date_str)
        except ValueError:
            return None, None, {"error": "Invalid start_date format. Use YYYY-MM-DD"}

    if end_date_str:
        try:
            end_date = datetime.fromisoformat(end_date_str)
        except ValueError:
            return None, None, {"error": "Invalid end_date format. Use YYYY-MM-DD"}

    if settings.USE_TZ:
        if start_date and timezone.is_naive(start_date):
            start_date = timezone.make_aware(start_date)
        if end_date and timezone.is_naive(end_date):
            end_date = timezone.make_aware(end_date)

    if start_date and end_date and start_date > end_date:
        return None, None, {"error": "Start date must be before end date"}

    return start_date, end_date, None


def validate_limit(limit_str: Optional[str] = None, default: int = 10) -> Tuple[int, Optional[Dict]]:
    """Validate limit parameter"""
    if not limit_str:
        return default, None

    try:
        limit = int(limit_str)
        if limit < 1:
            return default, {"error": "Limit must be greater than 0"}
        if limit > 100:
            return 100, None
        return limit, None
    except ValueError:
        return default, {"error": "Limit must be a valid integer"}


def validate_interval(interval_str: Optional[str] = None) -> Tuple[str, Optional[Dict]]:
    """Validate interval parameter"""
    valid_intervals = ['day', 'week', 'month']
    if not interval_str or interval_str not in valid_intervals:
        return 'day', None
    return interval_str, None
