"""
Views module - API endpoints for orders
"""

from .address_views import (
    get_user_addresses,
    create_address,
    update_address,
    delete_address,
)

from .user_order_views import (
    user_orders,
    create_order,
    order_detail,
    order_items,
    cancel_order,
    order_payment_options,
)

from .payment_views import (
    initiate_payment,
    verify_payment,
    paystack_webhook,
    payment_callback,
)

from .shipping_views import (
    get_shipping_rates,
    get_shipping_options,
)

from .admin_order_views import (
    admin_order_list,
    admin_order_detail,
    admin_order_by_number,
    admin_update_order_status,
    admin_update_payment_status,
    admin_order_stats,
    admin_order_analytics,
    admin_export_orders,
    admin_bulk_order_action,
)

from .shipment_views import (
    admin_create_shipment,
    admin_update_shipment_status,
    admin_shipments_list,
    order_shipment_info,
    track_shipment,
    admin_bulk_update_shipments,
    admin_shipment_detail,
)

from .transaction_views import (
    order_transactions,
    admin_process_refund,
    admin_transactions_list,
    admin_transaction_detail,
)

from .debug_views import (
    order_debug_info,
)

from .pos_views import (
    pos_create_order,
    pos_search_customers,
    pos_get_active_promotions,
)

__all__ = [
    'pos_create_order',
    'pos_search_customers',
    'pos_get_active_promotions',
    # Address views
    'get_user_addresses',
    'create_address',
    'update_address',
    'delete_address',
    # User order views
    'user_orders',
    'create_order',
    'order_detail',
    'order_items',
    'cancel_order',
    'order_payment_options',
    # Payment views
    'initiate_payment',
    'verify_payment',
    'paystack_webhook',
    'payment_callback',
    # Shipping views
    'get_shipping_rates',
    'get_shipping_options',
    # Admin order views
    'admin_order_list',
    'admin_order_detail',
    'admin_order_by_number',
    'admin_update_order_status',
    'admin_update_payment_status',
    'admin_order_stats',
    'admin_order_analytics',
    'admin_export_orders',
    'admin_bulk_order_action',
    # Shipment views
    'admin_create_shipment',
    'admin_update_shipment_status',
    'admin_shipments_list',
    'order_shipment_info',
    'track_shipment',
    'admin_bulk_update_shipments',
    'admin_shipment_detail',
    # Transaction views
    'order_transactions',
    'admin_process_refund',
    'admin_transactions_list',
    'admin_transaction_detail',
    # Debug views
    'order_debug_info',
]