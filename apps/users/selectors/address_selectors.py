"""
Address Selectors - Database read operations for user addresses
No business logic - just queries
"""

from typing import List, Optional
from apps.users.models.address import Address
import logging

logger = logging.getLogger(__name__)


def get_user_addresses(user_id: str) -> List[Address]:
    """Get all addresses for a user"""
    try:
        return list(Address.objects.filter(user_id=user_id, is_active=True).order_by('-is_default', '-created_at'))
    except Exception as e:
        logger.error(f"Failed to get addresses for user {user_id}: {str(e)}")
        return []


def get_user_default_address(user_id: str, address_type: str = 'shipping') -> Optional[Address]:
    """Get default address for a user by type"""
    try:
        return Address.objects.filter(
            user_id=user_id, 
            address_type=address_type, 
            is_default=True, 
            is_active=True
        ).first()
    except Exception as e:
        logger.error(f"Failed to get default address for user {user_id}: {str(e)}")
        return None