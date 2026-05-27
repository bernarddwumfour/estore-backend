"""
Address Schemas - Serialization and validation for addresses
"""

from typing import Dict, Any, Tuple, Optional
from django.core.validators import validate_email


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