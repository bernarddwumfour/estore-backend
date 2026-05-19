# apps/orders/services/payment_config.py
from decimal import Decimal
from typing import Dict, Any, Tuple
from django.conf import settings
from apps.orders.models import Order


class PaymentConfigService:
    """Payment configuration and business rules"""
    
    # Pay on Delivery limits
    POD_MAX_ORDER_VALUE = Decimal('500.00')  # Maximum order value for POD
    POD_MAX_QUANTITY = 10  # Maximum items for POD
    POD_ALLOWED_STATUSES = ['pending', 'confirmed']  # Statuses that allow POD
    
    # Paystack limits
    PAYSTACK_MIN_AMOUNT = Decimal('1.00')  # Minimum amount for Paystack
    PAYSTACK_MAX_AMOUNT = Decimal('999999.99')  # Maximum amount for Paystack
    
    @classmethod
    def check_pod_eligibility(cls, order: Order) -> Tuple[bool, str]:
        """
        Check if order is eligible for Pay on Delivery
        
        Returns:
            Tuple of (is_eligible, reason)
        """
        # Check order value
        if order.total > cls.POD_MAX_ORDER_VALUE:
            return False, f"Order value exceeds POD limit of ${cls.POD_MAX_ORDER_VALUE}"
        
        # Check item count
        if order.item_count > cls.POD_MAX_QUANTITY:
            return False, f"Order has {order.item_count} items. POD limit is {cls.POD_MAX_QUANTITY} items"
        
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
        methods = []
        
        # Check Paystack eligibility
        if cls.PAYSTACK_MIN_AMOUNT <= order.total <= cls.PAYSTACK_MAX_AMOUNT:
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
        
        return {
            'available_methods': methods,
            'default_method': 'paystack' if methods else None,
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