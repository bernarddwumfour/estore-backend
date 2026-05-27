"""
Order Schemas - Serialization and validation for orders
"""

from typing import Dict, Any, Tuple, Optional, List
from decimal import Decimal
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from apps.orders.models import Shipment


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
    from apps.orders.schemas.address_schemas import serialize_address
    
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
    
    # ==================== VALIDATE GUEST INFO (for non-authenticated users) ====================
    if not is_authenticated:
        guest_info = data.get('guest_info', {})
        
        if not guest_info:
            errors['guest_info'] = "Guest information is required for checkout"
        else:
            # Validate required guest fields
            if not guest_info.get('email'):
                errors['guest_info.email'] = "Email is required for guest checkout"
            elif not errors.get('guest_info.email'):
                try:
                    validate_email(guest_info['email'])
                except ValidationError:
                    errors['guest_info.email'] = "Invalid email address"
            
            if not guest_info.get('first_name'):
                errors['guest_info.first_name'] = "First name is required for guest checkout"
            
            if not guest_info.get('last_name'):
                errors['guest_info.last_name'] = "Last name is required for guest checkout"
            
            # Optional phone field
            phone = guest_info.get('phone', '')
            if phone:
                cleaned['guest_phone'] = phone
            
            # If no errors, store guest info
            if not any(k.startswith('guest_info') for k in errors.keys()):
                cleaned['guest_info'] = {
                    'email': guest_info['email'],
                    'first_name': guest_info['first_name'],
                    'last_name': guest_info['last_name'],
                    'phone': guest_info.get('phone', ''),
                }
    
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
    
    # ==================== RETURN RESULT ====================
    if errors:
        return None, errors
    
    return cleaned, None


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