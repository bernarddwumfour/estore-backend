"""Read-only order tracking for the authenticated shopper."""

import json
import logging

from django.contrib.auth import get_user_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.orders.models import Order


logger = logging.getLogger(__name__)
User = get_user_model()


class TrackOrdersInput(BaseModel):
    order_number: str | None = Field(
        default=None,
        max_length=20,
        description=(
            "Exact order number to look up, if the customer provided one. "
            "Leave empty to show their five most recent orders."
        ),
    )


def _serialize_order(order: Order) -> dict:
    shipment = getattr(order, "shipment", None)
    items = list(order.items.all())
    result = {
        "order_number": order.order_number,
        "status": order.status,
        "status_display": order.get_status_display(),
        "payment_status": order.payment_status,
        "created_at": order.created_at.isoformat(),
        "total": float(order.total),
        "currency": order.currency,
        "items": [],
        "items_count": len(items),
        "shipment": None,
    }

    for item in items[:12]:
        image_url = None
        if item.variant_id:
            image = next(
                (
                    variant_image
                    for variant_image in item.variant.images.all()
                    if variant_image.is_active and variant_image.image
                ),
                None,
            )
            if image and image.image:
                try:
                    image_url = image.image.url
                except ValueError:
                    pass
        result["items"].append({
            "product": item.product_title,
            "variant": item.variant_attributes or {},
            "quantity": item.quantity,
            "image": image_url,
        })

    if shipment:
        events = list(shipment.tracking_history.order_by("-created_at")[:10])
        events.reverse()
        result["shipment"] = {
            "status": shipment.status,
            "status_display": shipment.get_status_display(),
            "carrier": shipment.carrier or None,
            "tracking_number": shipment.tracking_number or None,
            "tracking_url": shipment.tracking_url or None,
            "estimated_delivery": (
                shipment.estimated_delivery.isoformat()
                if shipment.estimated_delivery
                else None
            ),
            "shipped_at": shipment.shipped_at.isoformat() if shipment.shipped_at else None,
            "delivered_at": (
                shipment.delivered_at.isoformat()
                if shipment.delivered_at
                else None
            ),
            "tracking_history": [
                {
                    "status": event.status,
                    "status_display": event.get_status_display(),
                    "location": event.location or None,
                    "description": event.description or None,
                    "created_at": event.created_at.isoformat(),
                }
                for event in events
            ],
        }

    return result


@tool(args_schema=TrackOrdersInput)
def track_customer_orders(
    config: RunnableConfig,
    order_number: str | None = None,
) -> str:
    """Look up the authenticated customer's order and shipment status."""
    user_id = config.get("configurable", {}).get("authenticated_user_id")
    if not user_id:
        return json.dumps({
            "success": False,
            "requires_authentication": True,
            "error": "Sign in to view your order status and tracking details.",
        })

    try:
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if user is None:
            return json.dumps({
                "success": False,
                "requires_authentication": True,
                "error": "Sign in to view your order status and tracking details.",
            })

        orders = (
            Order.objects.filter(user=user)
            .select_related("shipment")
            .prefetch_related(
                "items__variant__images",
                "shipment__tracking_history",
            )
            .order_by("-created_at")
        )

        normalized_number = (order_number or "").strip().lstrip("#").strip()
        if normalized_number:
            order = orders.filter(order_number__iexact=normalized_number).first()
            if order is None:
                return json.dumps({
                    "success": False,
                    "not_found": True,
                    "error": "I couldn't find that order in your account. Check the order number and try again.",
                })

            return json.dumps({
                "success": True,
                "view": "detail",
                "orders": [_serialize_order(order)],
            }, ensure_ascii=False)

        recent_orders = list(orders[:5])
        return json.dumps({
            "success": True,
            "view": "list",
            "orders": [_serialize_order(order) for order in recent_orders],
            "message": (
                "Here are your five most recent orders."
                if recent_orders
                else "There are no orders associated with your account yet."
            ),
        }, ensure_ascii=False)
    except Exception:
        logger.exception("Shopper order tracking lookup failed")
        return json.dumps({
            "success": False,
            "error": "Order tracking is temporarily unavailable. Please try again shortly.",
        })
