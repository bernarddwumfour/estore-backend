# apps/orders/services/shipment_service.py
import logging
from typing import Dict,  Optional, Tuple
from decimal import Decimal
from django.db import transaction

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
        estimated_delivery: str = None,
        notes: str = "",
        created_by: User = None,
    ) -> Tuple[Optional[Shipment], Optional[Dict]]:
        """Create a new shipment for an order"""
        try:
            order = get_order_by_id(order_id, include_cancelled=True)
            if not order:
                return None, {"order": "Order not found"}
            
            # Check if order is paid or is POD
            if order.payment_method == Order.PAYMENT_CASH_ON_DELIVERY:
                pass
            elif order.payment_status != Order.PAYMENT_PAID:
                return None, {"payment": "Order must be paid before creating shipment"}
            
            # Check if shipment already exists
            if hasattr(order, 'shipment'):
                return None, {"shipment": "Shipment already exists for this order"}
            
            # Create shipment with default empty strings
            shipment = Shipment.objects.create(
                order=order,
                status=Shipment.STATUS_SHIPPED,
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
                status=Shipment.STATUS_SHIPPED,
                description="Shipment created",
                created_by=created_by,
            )
            
            logger.info(f"Shipment created for order {order.order_number}")
            return shipment, None
            
        except Exception as e:
            logger.error(f"Shipment creation error: {str(e)}")
            return None, {"general": f"Failed to create shipment: {str(e)}"}
    
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
        
        
