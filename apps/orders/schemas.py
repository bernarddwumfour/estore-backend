# apps/orders/schemas.py
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional, List
from django.core.validators import validate_email
from .models import Shipment

from django.core.exceptions import ValidationError


# ==================== OUTPUT SERIALIZERS ====================

def serialize_address(address, is_admin: bool = False) -> Optional[Dict]:
    """Serialize address model"""
    if not address:
        return None
    
    data = {
        "id": str(address.id),
        "address_type": address.address_type,
        "first_name": address.first_name,
        "last_name": address.last_name,
        "company": address.company,
        "phone": address.phone,
        "email": address.email,
        "address_line1": address.address_line1,
        "address_line2": address.address_line2,
        "city": address.city,
        "state": address.state,
        "postal_code": address.postal_code,
        "country": address.country,
        "instructions": address.instructions,
        "is_default": address.is_default,
    }
    
    if is_admin:
        data.update({
            "is_active": address.is_active,
            "created_at": address.created_at.isoformat(),
            "updated_at": address.updated_at.isoformat(),
        })
    
    return data


def serialize_order_item(item, is_admin: bool = False) -> Dict:
    """Serialize order item"""
    return {
        "id": str(item.id),
        "product_title": item.product_title,
        "product_slug": item.product_slug,
        "sku": item.sku,
        "variant_attributes": item.variant_attributes,
        "quantity": item.quantity,
        "unit_price": float(item.unit_price),
        "discount_amount": float(item.discount_amount),
        "total_price": float(item.total_price),
        "discounted_unit_price": float(item.discounted_unit_price),
        "image": (
            item.variant.images.first().image.url
            if (item.variant and hasattr(item.variant, 'images') and item.variant.images.exists())
            else ""
        ) if is_admin else None,
    }



def serialize_order(order, is_admin: bool = False, detailed: bool = True) -> Dict:
    """Serialize order model"""
    data = {
        "id": str(order.id),
        "order_number": order.order_number,
        "status": order.status,
        "status_display": order.get_status_display(),
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "payment_type": getattr(order, 'payment_type', 'online'),
        "customer_name": order.customer_name,
        "customer_email": order.customer_email,
        "subtotal": float(order.subtotal),
        "shipping_cost": float(order.shipping_cost),
        "tax_amount": float(order.tax_amount),
        "discount_amount": float(order.discount_amount),
        "total": float(order.total),
        "currency": order.currency,
        "item_count": order.item_count,
        "shipping_method": order.shipping_method,
        "customer_note": order.customer_note,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }
    
    # Add carrier and tracking from shipment if exists
    if hasattr(order, 'shipment') and order.shipment:
        data["carrier"] = order.shipment.carrier
        data["tracking_number"] = order.shipment.tracking_number
    else:
        data["carrier"] = None
        data["tracking_number"] = None
    
    if is_admin:
        data.update({
            "guest_email": order.guest_email,
            "guest_first_name": order.guest_first_name,
            "guest_last_name": order.guest_last_name,
            "guest_phone": order.guest_phone,
            "payment_intent_id": order.payment_intent_id,
            "payment_receipt_url": order.payment_receipt_url,
            "admin_note": order.admin_note,
            "email_sent": order.email_sent,
            "pod_eligible": getattr(order, 'pod_eligible', False),
            "pod_reason": getattr(order, 'pod_reason', ''),
            "paid_at": order.paid_at.isoformat() if order.paid_at else None,
            "confirmed_at": order.confirmed_at.isoformat() if order.confirmed_at else None,
            "shipped_at": order.shipped_at.isoformat() if order.shipped_at else None,
            "delivered_at": order.delivered_at.isoformat() if order.delivered_at else None,
            "cancelled_at": order.cancelled_at.isoformat() if order.cancelled_at else None,
        })
    
    # Addresses
    if is_admin or detailed:
        data["shipping_address"] = serialize_address(order.shipping_address, is_admin)
        data["billing_address"] = serialize_address(order.billing_address, is_admin)
    else:
        if order.shipping_address:
            data["shipping_address"] = {
                "city": order.shipping_address.city,
                "country": order.shipping_address.country,
                "address_line1": order.shipping_address.address_line1,
            }
    
    if detailed:
        data["items"] = [serialize_order_item(item, is_admin) for item in order.items.all()]
    
    return data




def serialize_order_list(orders, is_admin: bool = False) -> List[Dict]:
    """Serialize list of orders (summary)"""
    return [serialize_order(order, is_admin, detailed=False) for order in orders]


def validate_order_create(data: Dict[str, Any], is_authenticated: bool = False) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate order creation data"""
    errors = {}
    cleaned = {}
    
    # ==================== VALIDATE ITEMS ====================
    items = data.get('items', [])
    if not items:
        errors['items'] = "At least one item is required"
    elif not isinstance(items, list):
        errors['items'] = "Items must be a list"
    else:
        cleaned_items = []
        for i, item in enumerate(items):
            item_errors = {}
            
            variant_id = item.get('variant_id')
            if not variant_id:
                item_errors['variant_id'] = "Variant ID is required"
            
            quantity = item.get('quantity', 1)
            if not isinstance(quantity, int) or quantity < 1:
                item_errors['quantity'] = "Quantity must be a positive integer"
            
            if item_errors:
                errors[f'items[{i}]'] = item_errors
            else:
                cleaned_items.append({
                    'variant_id': variant_id,
                    'quantity': quantity,
                })
        
        if not errors:
            cleaned['items'] = cleaned_items
    
    # ==================== VALIDATE SHIPPING ADDRESS ====================
    shipping_address = data.get('shipping_address', {})
    required_address_fields = [
        'first_name', 'last_name', 'phone', 'email', 
        'address_line1', 'city', 'state', 'postal_code', 'country'
    ]
    
    for field in required_address_fields:
        if not shipping_address.get(field):
            errors[f'shipping_address.{field}'] = f"{field.replace('_', ' ').title()} is required"
    
    # Validate email format in shipping address
    if shipping_address.get('email') and not errors.get(f'shipping_address.email'):
        try:
            validate_email(shipping_address['email'])
        except ValidationError:
            errors['shipping_address.email'] = "Invalid email address"
    
    if not errors.get('shipping_address') and 'shipping_address' not in errors:
        cleaned['shipping_address'] = shipping_address
    
    # ==================== VALIDATE BILLING ADDRESS (optional) ====================
    use_separate_billing = data.get('use_separate_billing', False)
    
    if use_separate_billing:
        billing_address = data.get('billing_address', {})
        if not billing_address:
            errors['billing_address'] = "Billing address is required when separate billing is enabled"
        else:
            for field in required_address_fields:
                if not billing_address.get(field):
                    errors[f'billing_address.{field}'] = f"{field.replace('_', ' ').title()} is required"
            
            # Validate email format in billing address
            if billing_address.get('email') and not errors.get(f'billing_address.email'):
                try:
                    validate_email(billing_address['email'])
                except ValidationError:
                    errors['billing_address.email'] = "Invalid email address"
            
            if not any(k.startswith('billing_address') for k in errors.keys()):
                cleaned['billing_address'] = billing_address
    
    # ==================== VALIDATE PAYMENT METHOD ====================
    payment_method = data.get('payment_method')
    valid_payment_methods = ['paystack', 'pod', 'cash_on_delivery']
    
    if not payment_method:
        errors['payment_method'] = "Payment method is required"
    elif payment_method not in valid_payment_methods:
        errors['payment_method'] = f"Invalid payment method. Must be one of: {', '.join(valid_payment_methods)}"
    else:
        cleaned['payment_method'] = payment_method
    
    # ==================== VALIDATE OPTIONAL FIELDS ====================
    optional_fields = ['customer_note', 'currency']
    for field in optional_fields:
        if field in data:
            cleaned[field] = data[field]
    
    # Set default currency if not provided
    if 'currency' not in cleaned and 'currency' not in errors:
        cleaned['currency'] = 'GHS'
    
    # ==================== VALIDATE FOR NON-AUTHENTICATED USERS ====================
    # Note: Guest user info is now taken from shipping address, not separate guest fields
    if not is_authenticated:
        # Ensure shipping address has all required guest info
        if 'shipping_address' in cleaned:
            shipping = cleaned['shipping_address']
            if not shipping.get('first_name'):
                errors['shipping_address.first_name'] = "First name is required for guest checkout"
            if not shipping.get('last_name'):
                errors['shipping_address.last_name'] = "Last name is required for guest checkout"
            if not shipping.get('email'):
                errors['shipping_address.email'] = "Email is required for guest checkout"
            if not shipping.get('phone'):
                errors['shipping_address.phone'] = "Phone number is required for guest checkout"
    
    # ==================== RETURN RESULT ====================
    if errors:
        return None, errors
    
    return cleaned, None


# apps/orders/schemas.py - Update validate_order_status_update

def validate_order_status_update(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate order status update"""
    errors = {}
    cleaned = {}
    
    status = data.get('status')
    valid_statuses = ['pending', 'confirmed', 'processing', 'shipped', 'delivered', 'cancelled', 'refunded']
    
    if not status:
        errors['status'] = "Status is required"
    elif status not in valid_statuses:
        errors['status'] = f"Invalid status. Must be one of: {', '.join(valid_statuses)}"
    else:
        cleaned['status'] = status
    
    if 'admin_note' in data:
        cleaned['admin_note'] = data['admin_note']
    
    # NEW: Allow tracking info when status is shipped
    if 'carrier' in data:
        cleaned['carrier'] = data['carrier']
    
    if 'tracking_number' in data:
        cleaned['tracking_number'] = data['tracking_number']
    
    if errors:
        return None, errors
    
    return cleaned, None




def validate_payment_status_update(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate payment status update"""
    errors = {}
    cleaned = {}
    
    payment_status = data.get('payment_status')
    valid_statuses = ['pending', 'paid', 'failed', 'refunded']
    
    if not payment_status:
        errors['payment_status'] = "Payment status is required"
    elif payment_status not in valid_statuses:
        errors['payment_status'] = f"Invalid payment status. Must be one of: {', '.join(valid_statuses)}"
    else:
        cleaned['payment_status'] = payment_status
    
    if 'payment_intent_id' in data:
        cleaned['payment_intent_id'] = data['payment_intent_id']
    
    if 'payment_receipt_url' in data:
        cleaned['payment_receipt_url'] = data['payment_receipt_url']
    
    if errors:
        return None, errors
    
    return cleaned, None


def validate_address_create(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate address creation data"""
    errors = {}
    cleaned = {}
    
    required_fields = [
        'address_type', 'first_name', 'last_name', 'phone', 'email',
        'address_line1', 'city', 'state', 'postal_code', 'country'
    ]
    
    for field in required_fields:
        if not data.get(field):
            errors[field] = f"{field.replace('_', ' ').title()} is required"
    
    if data.get('address_type') not in ['shipping', 'billing']:
        errors['address_type'] = "Address type must be 'shipping' or 'billing'"
    
    if data.get('email'):
        try:
            validate_email(data['email'])
        except:
            errors['email'] = "Invalid email address"
    
    if errors:
        return None, errors
    
    cleaned = {field: data.get(field, '') for field in required_fields}
    cleaned['company'] = data.get('company', '')
    cleaned['address_line2'] = data.get('address_line2', '')
    cleaned['instructions'] = data.get('instructions', '')
    cleaned['is_default'] = data.get('is_default', False)
    
    return cleaned, None


def validate_address_update(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate address update data"""
    errors = {}
    cleaned = {}
    
    updatable_fields = [
        'first_name', 'last_name', 'company', 'phone', 'email',
        'address_line1', 'address_line2', 'city', 'state', 
        'postal_code', 'country', 'instructions', 'is_default'
    ]
    
    for field in updatable_fields:
        if field in data:
            cleaned[field] = data[field]
    
    if 'email' in cleaned:
        try:
            validate_email(cleaned['email'])
        except:
            errors['email'] = "Invalid email address"
    
    if errors:
        return None, errors
    
    return cleaned, None


def validate_bulk_order_action(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate bulk order action request"""
    errors = {}
    cleaned = {}
    
    # Validate action
    action = data.get('action')
    valid_actions = ['cancel', 'confirm', 'process', 'ship', 'deliver']
    
    if not action:
        errors['action'] = "Action is required"
    elif action not in valid_actions:
        errors['action'] = f"Invalid action. Must be one of: {', '.join(valid_actions)}"
    else:
        cleaned['action'] = action
    
    # Validate order_ids
    order_ids = data.get('order_ids', [])
    if not order_ids:
        errors['order_ids'] = "At least one order ID is required"
    elif not isinstance(order_ids, list):
        errors['order_ids'] = "order_ids must be a list"
    else:
        cleaned['order_ids'] = order_ids
    
    if errors:
        return None, errors
    
    return cleaned, None


def validate_payment_initiation(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate payment initiation request"""
    errors = {}
    cleaned = {}
    
    # No additional validation needed for now
    # Can add payment method override in the future
    
    if errors:
        return None, errors
    
    return cleaned, None


# apps/orders/schemas.py - Add these functions

def serialize_transaction(transaction, is_admin: bool = False) -> Dict:
    """Serialize transaction for API response"""
    data = {
        "id": str(transaction.id),
        "transaction_type": transaction.transaction_type,
        "transaction_type_display": transaction.get_transaction_type_display(),
        "transaction_id": transaction.transaction_id,
        "reference": transaction.reference,
        "amount": float(transaction.amount),
        "currency": transaction.currency,
        "status": transaction.status,
        "status_display": transaction.get_status_display(),
        "payment_method": transaction.payment_method,
        "created_at": transaction.created_at.isoformat(),
        "completed_at": transaction.completed_at.isoformat() if transaction.completed_at else None,
    }
    
    if is_admin:
        data.update({
            "card_last4": transaction.card_last4,
            "card_brand": transaction.card_brand,
            "metadata": transaction.metadata,
            "notes": transaction.notes,
            "receipt_url": transaction.receipt_url,
            "refund_reason": transaction.refund_reason,
            "parent_transaction_id": str(transaction.parent_transaction_id) if transaction.parent_transaction_id else None,
        })
    
    return data


def serialize_shipment_info(order, include_tracking: bool = True) -> Dict:
    """Serialize shipment information for an order"""
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
            from apps.orders.selectors import get_shipment_tracking
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


def validate_refund_request(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate refund request"""
    errors = {}
    cleaned = {}
    
    amount = data.get('amount')
    if not amount:
        errors['amount'] = "Amount is required"
    else:
        try:
            cleaned['amount'] = Decimal(str(amount))
            if cleaned['amount'] <= 0:
                errors['amount'] = "Amount must be greater than 0"
        except:
            errors['amount'] = "Invalid amount"
    
    if 'refund_reason' in data:
        cleaned['refund_reason'] = data['refund_reason']
    
    if 'admin_note' in data:
        cleaned['admin_note'] = data['admin_note']
    
    if errors:
        return None, errors
    
    return cleaned, None


def serialize_pagination_metadata(pagination_meta: Dict) -> Dict:
    """Serialize pagination metadata for API response"""
    return {
        "current_page": pagination_meta["current_page"],
        "per_page": pagination_meta["per_page"],
        "total": pagination_meta["total"],
        "total_pages": pagination_meta["total_pages"],
        "has_next": pagination_meta["has_next"],
        "has_previous": pagination_meta["has_previous"],
        "next_page": pagination_meta["next_page"],
        "previous_page": pagination_meta["previous_page"],
        "start_index": pagination_meta["start_index"],
        "end_index": pagination_meta["end_index"],
    }


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


def serialize_transaction_list(transactions: List, is_admin: bool = False) -> List[Dict]:
    """Serialize list of transactions for list view"""
    return [serialize_transaction(t, is_admin=is_admin) for t in transactions]