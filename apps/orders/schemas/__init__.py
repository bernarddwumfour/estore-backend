"""
Schemas module - Serialization and validation for orders
"""

from .address_schemas import (
    serialize_address,
    validate_address_create,
    validate_address_update,
)

from .order_schemas import (
    serialize_order_item,
    serialize_order,
    serialize_order_list,
    validate_order_create,
    validate_order_status_update,
    validate_payment_status_update,
    validate_bulk_order_action,
)

from .shipment_schemas import (
    serialize_shipment_info,
    serialize_shipment_list,
    serialize_tracking_history,
    validate_shipment_update,
)

from .transaction_schemas import (
    serialize_transaction,
    serialize_transaction_list,
    validate_payment_initiation,
    validate_refund_request,
)

from .common_schemas import (
    serialize_pagination_metadata,
)

from .shipping_schemas import (
    validate_shipping_config_update,
    serialize_shipping_config,
    serialize_popular_address,
)

__all__ = [
    # Address schemas
    'serialize_address',
    'validate_address_create',
    'validate_address_update',
    # Order schemas
    'serialize_order_item',
    'serialize_order',
    'serialize_order_list',
    'validate_order_create',
    'validate_order_status_update',
    'validate_payment_status_update',
    'validate_bulk_order_action',
    # Shipment schemas
    'serialize_shipment_info',
    'serialize_shipment_list',
    'serialize_tracking_history',
    'validate_shipment_update',
    # Transaction schemas
    'serialize_transaction',
    'serialize_transaction_list',
    'validate_payment_initiation',
    'validate_refund_request',
    # Common schemas
    'serialize_pagination_metadata',
    # Shipping config schemas
    'validate_shipping_config_update',
    'serialize_shipping_config',
    'serialize_popular_address',
]