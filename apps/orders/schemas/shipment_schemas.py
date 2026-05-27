"""
Shipment Schemas - Serialization and validation for shipments
"""

from typing import Dict, Any, Tuple, Optional, List
from decimal import Decimal

from apps.orders.models import Shipment


def serialize_shipment_info(order, include_tracking: bool = True) -> Dict:
    """Serialize shipment information for an order"""
    from apps.orders.selectors.shipment_selectors import get_shipment_tracking
    
    data = {
        "has_shipment": hasattr(order, 'shipment'),
        "shipment_status": None,
        "shipment_status_display": None,
        "tracking_number": None,
        "carrier": None,
        "estimated_delivery": None,
        "shipping_method": order.shipping_method,
        "shipping_cost": float(order.shipping_cost),
        "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
        "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
    }
    
    if hasattr(order, 'shipment'):
        shipment = order.shipment
        data.update({
            "shipment_status": shipment.status,
            "shipment_status_display": shipment.get_status_display(),
            "tracking_number": shipment.tracking_number,
            "carrier": shipment.carrier,
            "estimated_delivery": shipment.estimated_delivery.isoformat() if shipment.estimated_delivery else None,
        })
        
        if include_tracking:
            tracking = get_shipment_tracking(str(shipment.id))
            data["tracking_history"] = [
                {
                    "status": t.status,
                    "status_display": dict(Shipment.STATUS_CHOICES).get(t.status, t.status),
                    "location": t.location,
                    "description": t.description,
                    "created_at": t.created_at.isoformat(),
                }
                for t in tracking
            ]
    
    return data


def serialize_shipment_list(shipments: List, is_admin: bool = False) -> List[Dict]:
    """Serialize list of shipments for list view"""
    return [
        {
            "id": str(s.id),
            "order_number": s.order.order_number,
            "order_id": str(s.order.id),
            "customer_name": s.order.customer_name,
            "customer_email": s.order.customer_email,
            "status": s.status,
            "status_display": s.get_status_display(),
            "tracking_number": s.tracking_number,
            "carrier": s.carrier,
            "created_at": s.created_at.isoformat(),
            "shipped_at": s.shipped_at.isoformat() if s.shipped_at else None,
            "delivered_at": s.delivered_at.isoformat() if s.delivered_at else None,
            "estimated_delivery": s.estimated_delivery.isoformat() if s.estimated_delivery else None,
        }
        for s in shipments
    ]


def validate_shipment_update(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate shipment status update"""
    errors = {}
    cleaned = {}
    
    shipment_status = data.get('shipment_status')
    if shipment_status:
        valid_statuses = ['pending', 'processing', 'ready', 'shipped', 'in_transit', 'out_for_delivery', 'delivered', 'failed', 'returned']
        if shipment_status not in valid_statuses:
            errors['shipment_status'] = f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
        else:
            cleaned['shipment_status'] = shipment_status
    
    if 'tracking_number' in data:
        cleaned['tracking_number'] = data['tracking_number']
    
    if 'carrier' in data:
        cleaned['carrier'] = data['carrier']
    
    if 'location' in data:
        cleaned['location'] = data['location']
    
    if 'description' in data:
        cleaned['description'] = data['description']
    
    if errors:
        return None, errors
    
    return cleaned, None
