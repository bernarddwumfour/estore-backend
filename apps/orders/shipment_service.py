# apps/orders/services/shipment_service.py
import logging
from typing import Dict,  Optional, Tuple
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.orders.models import Order, Shipment, ShipmentTracking
from apps.orders.selectors import get_order_by_id
from apps.users.models import User

logger = logging.getLogger(__name__)




logger = logging.getLogger(__name__)


class ShipmentService:
    """Shipment business logic"""
    
        
    # apps/orders/services/shipment_service.py - Update create_shipment

    @staticmethod
    @transaction.atomic
    def create_shipment(
        order_id: str,
        carrier: str = "",
        tracking_number: str = "",
        tracking_url: str = "",
        weight: Decimal = None,
        dimensions: str = "",
        estimated_delivery: str = None,
        notes: str = "",
        shipping_cost: Decimal = None,
        created_by: User = None,
    ) -> Tuple[Optional[Shipment], Optional[Dict]]:
        """Create a new shipment for an order.

        The shipment starts as `pending` — it becomes `shipped` (and syncs the
        order) via update_shipment_status once it is dispatched. Orders not yet
        ready_for_shipping are advanced to it so both stay consistent.
        `dimensions` is accepted for API compatibility but folded into notes;
        `shipping_cost`, when given, overrides the order's shipping cost and
        recomputes its total.
        """
        try:
            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}

            # Check if shipment already exists
            if hasattr(order, 'shipment'):
                return None, {"shipment": "Shipment already exists for this order"}

            if order.is_pickup:
                return None, {"order": "In-store pickup orders cannot be shipped"}

            if order.status not in (
                Order.STATUS_CONFIRMED,
                Order.STATUS_PROCESSING,
                Order.STATUS_READY_FOR_SHIPPING,
            ):
                return None, {
                    "order": (
                        "Only confirmed, processing or ready-for-shipping orders "
                        f"can be shipped (current status: {order.status})"
                    )
                }

            if shipping_cost is not None:
                old_shipping_cost = order.shipping_cost
                order.shipping_cost = shipping_cost
                order.total = order.total - old_shipping_cost + shipping_cost
                order.save(update_fields=["shipping_cost", "total", "updated_at"])

            if dimensions:
                notes = f"{notes}\nDimensions: {dimensions}" if notes else f"Dimensions: {dimensions}"

            if order.status != Order.STATUS_READY_FOR_SHIPPING:
                order.status = Order.STATUS_READY_FOR_SHIPPING
                if not order.ready_for_shipping_at:
                    order.ready_for_shipping_at = timezone.now()
                order.save(update_fields=["status", "ready_for_shipping_at", "updated_at"])

            # Create shipment with default empty strings
            shipment = Shipment.objects.create(
                order=order,
                status=Shipment.STATUS_PENDING,
                carrier=carrier or '',
                tracking_number=tracking_number or '',
                tracking_url=tracking_url or '',
                weight=weight,
                estimated_delivery=estimated_delivery,
                notes=notes,
                created_by=created_by,
            )

            # Create initial tracking record
            ShipmentTracking.objects.create(
                shipment=shipment,
                status=Shipment.STATUS_PENDING,
                description="Shipment created — awaiting dispatch",
                created_by=created_by,
            )
            
            logger.info(f"Shipment created for order {order.order_number}")
            return shipment, None
            
        except Exception as e:
            logger.error(f"Shipment creation error: {str(e)}")
            return None, {"general": f"Failed to create shipment: {str(e)}"}
    
    @staticmethod
    @transaction.atomic
    def update_shipment_status(
        shipment_id: str,
        status: str = None,
        location: str = "",
        description: str = "",
        tracking_number: str = None,
        carrier: str = None,
        created_by: User = None,
    ) -> Tuple[Optional[Shipment], Optional[Dict]]:
        """
        Update a shipment's status and/or tracking details.

        status=None (or unchanged) allows a pure carrier/tracking update.
        Shipment.save() syncs the order status (shipped/delivered/cancelled/
        refunded) and dispatches the customer notification emails.
        """
        try:
            shipment = Shipment.objects.select_related("order").get(id=shipment_id)
        except (Shipment.DoesNotExist, ValueError, ValidationError):
            return None, {"shipment": "Shipment not found"}

        try:
            status_changed = False
            if status is not None and status != shipment.status:
                valid_statuses = dict(Shipment.STATUS_CHOICES).keys()
                if status not in valid_statuses:
                    return None, {
                        "status": f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
                    }

                if status == Shipment.STATUS_PENDING:
                    return None, {"status": "Shipments cannot go back to pending"}
                if status == Shipment.STATUS_DELIVERED and shipment.status != Shipment.STATUS_SHIPPED:
                    return None, {"status": "Only shipped shipments can be marked delivered"}
                if status == Shipment.STATUS_REFUNDED and shipment.status not in (
                    Shipment.STATUS_SHIPPED,
                    Shipment.STATUS_DELIVERED,
                ):
                    return None, {"status": "Only shipped or delivered shipments can be refunded"}
                if status == Shipment.STATUS_SHIPPED:
                    if shipment.status != Shipment.STATUS_PENDING:
                        return None, {
                            "status": f"A {shipment.status} shipment cannot go back to shipped"
                        }
                    order = shipment.order
                    if (
                        order.payment_method != Order.PAYMENT_CASH_ON_DELIVERY
                        and order.payment_status != Order.PAYMENT_PAID
                    ):
                        return None, {
                            "payment": "Order must be paid before the shipment can be marked shipped"
                        }

                status_changed = True
                shipment.status = status

            if tracking_number:
                shipment.tracking_number = tracking_number
            if carrier:
                shipment.carrier = carrier
            if shipment.status == Shipment.STATUS_DELIVERED and not shipment.delivered_at:
                shipment.delivered_at = timezone.now()
            shipment.updated_by = created_by
            shipment.save()

            if status_changed:
                ShipmentTracking.objects.create(
                    shipment=shipment,
                    status=shipment.status,
                    location=location or "",
                    description=description or f"Status updated to {shipment.status}",
                    created_by=created_by,
                )

            logger.info(
                f"Shipment {shipment.id} for order {shipment.order.order_number} "
                f"updated to {shipment.status}"
            )
            return shipment, None
        except Exception:
            logger.exception("Shipment status update error")
            return None, {"general": "Failed to update shipment status"}

    @staticmethod
    def get_shipment_by_order_id(order_id: str) -> Optional[Shipment]:
        """Get shipment by order ID"""
        try:
            return Shipment.objects.select_related('order').get(order_id=order_id)
        except Shipment.DoesNotExist:
            return None
    
    @staticmethod
    def get_shipment_tracking(shipment_id: str) -> list:
        """Get shipment tracking history"""
        try:
            shipment = Shipment.objects.get(id=shipment_id)
            return list(shipment.tracking_history.all().order_by('-created_at'))
        except Shipment.DoesNotExist:
            return []
        
        
