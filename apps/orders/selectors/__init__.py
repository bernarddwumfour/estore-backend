"""
Selectors module - Database read operations for orders
"""

from .order_selectors import (
    get_order_by_id,
    get_user_orders,
    get_admin_orders_filtered,
    get_admin_orders,
    get_order_items,
)

from .statistics_selectors import (
    get_order_statistics_filtered,
    get_order_statistics,
)

from .address_selectors import (
    get_user_addresses,
    get_address_by_id,
)

from .shipment_selectors import (
    get_shipments_filtered,
    get_orders_by_shipment_status,
    get_shipment_tracking,
    get_shipment_by_id,
)

from .transaction_selectors import (
    get_transactions_filtered,
    get_order_transactions,
    get_transaction_by_id,
    get_refundable_amount,
    get_transaction_statistics,
)

__all__ = [
    # Order selectors
    'get_order_by_id',
    'get_user_orders',
    'get_admin_orders_filtered',
    'get_admin_orders',
    'get_order_items',
    # Statistics selectors
    'get_order_statistics_filtered',
    'get_order_statistics',
    # Address selectors
    'get_user_addresses',
    'get_address_by_id',
    # Shipment selectors
    'get_shipments_filtered',
    'get_orders_by_shipment_status',
    'get_shipment_tracking',
    'get_shipment_by_id',
    # Transaction selectors
    'get_transactions_filtered',
    'get_order_transactions',
    'get_transaction_by_id',
    'get_refundable_amount',
    'get_transaction_statistics',
]