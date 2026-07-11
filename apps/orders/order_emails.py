"""
apps/orders/order_emails.py

Transactional order emails. Every sender swallows its own errors:
an email failure must never alter the payment or order flow.
Each event can be switched off in Settings → General (notifications).
"""

import logging

from django.conf import settings

from estore.utils.email_util import send_templated_email

logger = logging.getLogger(__name__)


def _email_enabled(event: str) -> bool:
    """Config gate — fails open so a config problem never blocks a receipt."""
    try:
        from apps.common.models import GeneralConfig
        return GeneralConfig.get_cached().notification_enabled(event, "email")
    except Exception:
        return True


def _store_name() -> str:
    try:
        from apps.common.models import GeneralConfig
        name = GeneralConfig.get_cached().store_name
        if name:
            return name
    except Exception:
        pass
    return getattr(settings, 'SITE_NAME', 'API')


def send_order_confirmation_email(order, transaction_record=None) -> bool:
    """Send combined order confirmation + payment receipt after payment succeeds."""
    try:
        if not _email_enabled("order_confirmation"):
            return False
        if order.email_sent:
            return False

        recipient = order.customer_email
        if not recipient:
            logger.warning(f"No customer email for order {order.order_number}; skipping confirmation email")
            return False

        receipt_url = getattr(transaction_record, "receipt_url", "") or order.payment_receipt_url

        send_templated_email(
            recipient_email=recipient,
            subject=f"Order Confirmed - {order.order_number} - {_store_name()}",
            template="order_confirmation.html",
            context={
                "order": order,
                "items": list(order.items.all()),
                "receipt_url": receipt_url,
                "payment_method": order.payment_method or "Paystack",
            },
            recipient_name=order.customer_name,
        )

        order.email_sent = True
        order.save(update_fields=["email_sent"])
        return True
    except Exception as e:
        logger.error(f"Failed to send order confirmation email for {getattr(order, 'order_number', '?')}: {str(e)}")
        return False


def send_shipping_update_email(order, shipment=None) -> bool:
    """Notify the customer that their order has shipped."""
    try:
        if not _email_enabled("order_shipped"):
            return False

        recipient = order.customer_email
        if not recipient:
            return False

        send_templated_email(
            recipient_email=recipient,
            subject=f"Your Order Has Shipped - {order.order_number}",
            template="shipping_update.html",
            context={"order": order, "shipment": shipment},
            recipient_name=order.customer_name,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send shipping email for {getattr(order, 'order_number', '?')}: {str(e)}")
        return False


def send_order_delivered_email(order) -> bool:
    """Notify the customer that their order was delivered."""
    try:
        if not _email_enabled("order_delivered"):
            return False

        recipient = order.customer_email
        if not recipient:
            return False

        send_templated_email(
            recipient_email=recipient,
            subject=f"Your Order Has Been Delivered - {order.order_number}",
            template="order_delivered.html",
            context={"order": order},
            recipient_name=order.customer_name,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to send delivered email for {getattr(order, 'order_number', '?')}: {str(e)}")
        return False
