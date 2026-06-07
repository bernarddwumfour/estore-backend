"""
Store Address Helper - Get or create store address for POS orders
"""

import logging
from django.conf import settings

from apps.users.models import Address

logger = logging.getLogger(__name__)


def get_or_create_store_address(created_by) -> Address:
    """
    Get or create the store address for POS in-store pickup orders.
    Uses settings.STORE_ADDRESS configuration.
    """
    store_config = getattr(settings, 'STORE_ADDRESS', {})
    
    # Try to find existing store address
    store_address = Address.objects.filter(
        address_type='shipping',
        first_name=store_config.get('first_name', 'Store'),
        last_name=store_config.get('last_name', 'Pickup'),
        address_line1=store_config.get('address_line1', '123 Main Street'),
        city=store_config.get('city', 'Accra'),
        country=store_config.get('country', 'GH'),
    ).first()
    
    if store_address:
        return store_address
    
    # Create new store address
    store_address = Address.objects.create(
        user=created_by,
        address_type='shipping',
        first_name=store_config.get('first_name', 'Store'),
        last_name=store_config.get('last_name', 'Pickup'),
        company='Main Store',
        email=store_config.get('email', 'store@example.com'),
        phone=store_config.get('phone', '+233000000000'),
        address_line1=store_config.get('address_line1', '123 Main Street'),
        address_line2=store_config.get('address_line2', ''),
        city=store_config.get('city', 'Accra'),
        state=store_config.get('state', 'Greater Accra'),
        postal_code=store_config.get('postal_code', 'GA-123'),
        country=store_config.get('country', 'GH'),
        instructions=store_config.get('instructions', 'In-Store Pickup'),
        is_default=False,
        is_active=True,
    )
    
    logger.info(f"Created store address: {store_address.address_line1}, {store_address.city}")
    return store_address