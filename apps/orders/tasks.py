"""
Order background tasks.

Celery runs eagerly (inline) when no broker is configured, so these tasks are
safe to call anywhere; with Redis provisioned they run on a worker. The
`cancel_unpaid_orders` management command is the cron-friendly entry point.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def cancel_unpaid_orders_task(self):
    """Cancel stale unpaid orders per GeneralConfig.auto_cancel_unpaid_hours."""
    from apps.orders.order_service import OrderService

    cancelled, failed = OrderService.cancel_stale_unpaid_orders()
    logger.info(f"cancel_unpaid_orders_task: {cancelled} cancelled, {failed} failed")
    return {"cancelled": cancelled, "failed": failed}
