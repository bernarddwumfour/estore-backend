"""
Address Schemas - Serialization and validation for addresses
"""

from typing import Dict, Any, List, Optional
from apps.users.models.address import Address


def serialize_address(address: Address, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize an address"""
    if not address:
        return None
    
    try:
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
            "full_address": address.full_address,
        }

        if is_admin:
            data.update({
                "user_id": str(address.user.id) if address.user else None,
                "is_active": address.is_active,
                "created_at": address.created_at.isoformat() if address.created_at else None,
                "updated_at": address.updated_at.isoformat() if address.updated_at else None,
            })

        return data
    except Exception as e:
        print(f"Error serializing address {address.id}: {e}")
        return None


def serialize_addresses(addresses: List[Address], is_admin: bool = False) -> List[Dict[str, Any]]:
    """Serialize list of addresses"""
    return [serialize_address(address, is_admin) for address in addresses]