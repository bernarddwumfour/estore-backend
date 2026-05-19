# apps/orders/schemas.py
from decimal import Decimal
from typing import Dict, Any, Tuple, Optional, List
from django.core.validators import validate_email
from decimal import  DecimalException


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
        "carrier": order.carrier,
        "customer_note": order.customer_note,
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }
    
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
    
    # Addresses (always include for admin, limited for users)
    if is_admin or detailed:
        data["shipping_address"] = serialize_address(order.shipping_address, is_admin)
        data["billing_address"] = serialize_address(order.billing_address, is_admin)
    else:
        # Limited address info for users
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


# ==================== INPUT VALIDATORS ====================

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
    
    if not errors:
        cleaned['shipping_address'] = shipping_address
    
    # ==================== VALIDATE BILLING ADDRESS (optional) ====================
    if 'billing_address' in data and data['billing_address']:
        billing_address = data['billing_address']
        for field in required_address_fields:
            if not billing_address.get(field):
                errors[f'billing_address.{field}'] = f"{field.replace('_', ' ').title()} is required"
        
        if not errors and 'billing_address' not in errors:
            cleaned['billing_address'] = billing_address
    
    # ==================== VALIDATE PAYMENT METHOD ====================
    payment_method = data.get('payment_method')
    valid_payment_methods = ['paystack', 'pod']
    
    if not payment_method:
        errors['payment_method'] = "Payment method is required"
    elif payment_method not in valid_payment_methods:
        errors['payment_method'] = f"Invalid payment method. Must be one of: {', '.join(valid_payment_methods)}"
    else:
        cleaned['payment_method'] = payment_method
    
    # ==================== VALIDATE GUEST CHECKOUT FIELDS ====================
    if not is_authenticated:
        guest_email = data.get('guest_email')
        if not guest_email:
            errors['guest_email'] = "Email is required for guest checkout"
        else:
            try:
                validate_email(guest_email)
                cleaned['guest_email'] = guest_email
            except:
                errors['guest_email'] = "Invalid email address"
        
        if not data.get('guest_first_name'):
            errors['guest_first_name'] = "First name is required for guest checkout"
        else:
            cleaned['guest_first_name'] = data['guest_first_name']
        
        if not data.get('guest_last_name'):
            errors['guest_last_name'] = "Last name is required for guest checkout"
        else:
            cleaned['guest_last_name'] = data['guest_last_name']
        
        if not data.get('guest_phone'):
            errors['guest_phone'] = "Phone number is required for guest checkout"
        else:
            cleaned['guest_phone'] = data['guest_phone']
    
    # ==================== VALIDATE OPTIONAL FIELDS ====================
    optional_fields = ['shipping_cost', 'tax_rate', 'discount_amount', 'customer_note', 'shipping_method', 'currency']
    for field in optional_fields:
        if field in data:
            try:
                if field in ['shipping_cost', 'tax_rate', 'discount_amount']:
                    value = Decimal(str(data[field]))
                    if value < 0:
                        errors[field] = f"{field} cannot be negative"
                    else:
                        cleaned[field] = value
                else:
                    cleaned[field] = data[field]
            except (ValueError, TypeError, DecimalException):
                errors[field] = f"Invalid value for {field}"
    
    # Set default currency if not provided
    if 'currency' not in cleaned and 'currency' not in errors:
        cleaned['currency'] = 'USD'
    
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
    
    if 'carrier' in data:
        cleaned['carrier'] = data['carrier']
    
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