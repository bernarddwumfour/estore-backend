# apps/orders/payment_config.py
from typing import Dict, Any, Tuple
from django.conf import settings

from apps.common.models import GeneralConfig
from apps.orders.models import Order


class PaymentConfigService:
    """Payment configuration and business rules (driven by GeneralConfig)"""

    POD_ALLOWED_STATUSES = ['pending', 'confirmed']  # Statuses that allow POD

    @classmethod
    def _config(cls) -> GeneralConfig:
        return GeneralConfig.get_cached()

    @classmethod
    def check_pod_eligibility(cls, order: Order) -> Tuple[bool, str]:
        """
        Check if order is eligible for Pay on Delivery

        Returns:
            Tuple of (is_eligible, reason)
        """
        config = cls._config()

        if not config.pod_enabled:
            return False, "Pay on Delivery is currently disabled"

        # Check order value
        if order.total > config.pod_max_order_value:
            return False, (
                f"Order value exceeds POD limit of {config.currency} {config.pod_max_order_value}"
            )

        # Check item count
        if order.item_count > config.pod_max_quantity:
            return False, (
                f"Order has {order.item_count} items. POD limit is {config.pod_max_quantity} items"
            )

        # Check order status
        if order.status not in cls.POD_ALLOWED_STATUSES:
            return False, f"Order status '{order.status}' does not allow Pay on Delivery"

        # Check if customer is in allowed location (optional)
        if order.shipping_address:
            restricted_countries = getattr(settings, 'POD_RESTRICTED_COUNTRIES', [])
            if order.shipping_address.country in restricted_countries:
                return False, f"Pay on Delivery not available in {order.shipping_address.country}"

        return True, "Eligible for Pay on Delivery"

    @classmethod
    def get_available_payment_methods(cls, order: Order) -> Dict[str, Any]:
        """
        Get available payment methods for an order
        """
        config = cls._config()
        methods = []

        # Check Paystack eligibility
        if (
            config.paystack_enabled
            and config.paystack_min_amount <= order.total <= config.paystack_max_amount
        ):
            methods.append({
                'id': 'paystack',
                'name': 'Paystack',
                'type': 'online',
                'description': 'Pay securely with card, bank transfer, or mobile money',
                'icon': 'paystack',
            })

        # Check Pay on Delivery eligibility
        is_pod_eligible, pod_reason = cls.check_pod_eligibility(order)
        if is_pod_eligible:
            methods.append({
                'id': 'pod',
                'name': 'Pay on Delivery',
                'type': 'pod',
                'description': 'Pay when you receive your order',
                'icon': 'delivery',
            })

        method_ids = [m['id'] for m in methods]
        if config.default_payment_method in method_ids:
            default_method = config.default_payment_method
        else:
            default_method = method_ids[0] if method_ids else None

        return {
            'available_methods': methods,
            'default_method': default_method,
            'pod_eligible': is_pod_eligible,
            'pod_reason': pod_reason if not is_pod_eligible else None,
        }

    @classmethod
    def validate_payment_method(cls, order: Order, payment_method: str) -> Tuple[bool, str]:
        """
        Validate if payment method is available for the order
        """
        available_methods = cls.get_available_payment_methods(order)

        method_ids = [m['id'] for m in available_methods['available_methods']]

        if payment_method not in method_ids:
            return False, f"Payment method '{payment_method}' is not available for this order"

        return True, "Payment method is available"
