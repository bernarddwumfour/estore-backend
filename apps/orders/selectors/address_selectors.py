"""
Address Selectors - Database read operations for addresses
No business logic - just queries
"""

from typing import Optional, List
from apps.users.models import Address


def get_user_addresses(user, address_type: str = None, only_active: bool = True) -> List[Address]:
    """Get addresses for a user"""
    queryset = Address.objects.filter(user=user)
    
    if only_active:
        queryset = queryset.filter(is_active=True)
    if address_type:
        queryset = queryset.filter(address_type=address_type)
    
    return list(queryset.order_by('-is_default', '-created_at'))


def get_address_by_id(address_id: str, user=None) -> Optional[Address]:
    """Get address by ID"""
    try:
        queryset = Address.objects.all()
        if user:
            queryset = queryset.filter(user=user)
        return queryset.get(id=address_id)
    except Address.DoesNotExist:
        return None