# apps/orders/shipping_calculator.py
import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ShippingCalculator:
    """Config-driven shipping cost calculation (internal fallback rates).

    Rates and methods come from the ShippingConfig singleton; the hardcoded
    dicts below are the last-resort defaults when config JSON is malformed.
    Public classmethod signatures are stable — order creation, POS, and the
    rate endpoints all call these.
    """

    # Last-resort defaults (mirror ShippingConfig seed values)
    BASE_RATES = {
        'GH': {
            'base': Decimal('15.00'),
            'per_kg': Decimal('5.00'),
            'free_shipping_threshold': Decimal('500.00'),
        },
        'NG': {
            'base': Decimal('20.00'),
            'per_kg': Decimal('7.00'),
            'free_shipping_threshold': Decimal('150.00'),
        },
        'KE': {
            'base': Decimal('18.00'),
            'per_kg': Decimal('6.00'),
            'free_shipping_threshold': Decimal('120.00'),
        },
        'ZA': {
            'base': Decimal('25.00'),
            'per_kg': Decimal('8.00'),
            'free_shipping_threshold': Decimal('200.00'),
        },
        'DEFAULT': {
            'base': Decimal('30.00'),
            'per_kg': Decimal('10.00'),
            'free_shipping_threshold': Decimal('500.00'),
        },
    }

    SHIPPING_METHODS = {
        'standard': {
            'name': 'Standard Shipping',
            'multiplier': Decimal('1.0'),
            'estimated_days': '3-7 business days',
        },
        'express': {
            'name': 'Express Shipping',
            'multiplier': Decimal('2'),
            'estimated_days': '1-3 business days',
        },
        'overnight': {
            'name': 'Overnight Shipping',
            'multiplier': Decimal('3.0'),
            'estimated_days': 'Next business day',
        },
    }

    @classmethod
    def _get_rates(cls) -> Dict[str, Dict[str, Decimal]]:
        """Country rates from config, Decimal-parsed, with safe fallback"""
        from apps.orders.models import ShippingConfig

        try:
            raw = ShippingConfig.get_cached().fallback_rates or {}
            rates = {}
            for code, entry in raw.items():
                rates[code.upper()] = {
                    'base': Decimal(str(entry['base'])),
                    'per_kg': Decimal(str(entry['per_kg'])),
                    'free_shipping_threshold': Decimal(
                        str(entry.get('free_shipping_threshold', '999999'))
                    ),
                }
            if 'DEFAULT' in rates:
                return rates
        except (KeyError, TypeError, ValueError, InvalidOperation) as e:
            logger.error(f"Malformed shipping fallback_rates config: {str(e)}")
        return cls.BASE_RATES

    @classmethod
    def _get_methods(cls) -> Dict[str, Dict[str, Any]]:
        """Shipping methods from config, Decimal-parsed, with safe fallback"""
        from apps.orders.models import ShippingConfig

        try:
            raw = ShippingConfig.get_cached().shipping_methods or {}
            methods = {}
            for key, entry in raw.items():
                methods[key] = {
                    'name': str(entry['name']),
                    'multiplier': Decimal(str(entry['multiplier'])),
                    'estimated_days': str(entry.get('estimated_days', '')),
                    'enabled': bool(entry.get('enabled', True)),
                }
            if any(m['enabled'] for m in methods.values()):
                return methods
        except (KeyError, TypeError, ValueError, InvalidOperation) as e:
            logger.error(f"Malformed shipping_methods config: {str(e)}")
        return cls.SHIPPING_METHODS

    @classmethod
    def calculate_shipping_cost(
        cls,
        country_code: str,
        total_weight_kg: Decimal,
        subtotal: Decimal,
        shipping_method: str = 'standard',
    ) -> Dict[str, Any]:
        """
        Calculate shipping cost based on country, weight, and subtotal
        """
        from apps.orders.models import ShippingConfig
        from apps.orders.shipping_quote_service import ShippingQuoteService

        config = ShippingConfig.get_cached()
        all_rates = cls._get_rates()
        all_methods = cls._get_methods()

        normalized = ShippingQuoteService.normalize_country(country_code)
        rates = all_rates.get(normalized, all_rates['DEFAULT'])
        method = all_methods.get(shipping_method)
        if not method or not method.get('enabled', True):
            # Fall back to the first enabled method (legacy/POS callers)
            method = next(
                (m for m in all_methods.values() if m.get('enabled', True)),
                {'name': 'Standard Shipping', 'multiplier': Decimal('1.0'),
                 'estimated_days': '3-7 business days'},
            )

        # Free-shipping overlays — a threshold of 0 or less means "disabled"
        global_threshold_met = (
            config.free_shipping_threshold is not None
            and config.free_shipping_threshold > 0
            and subtotal >= config.free_shipping_threshold
        )
        country_threshold = rates['free_shipping_threshold']
        country_threshold_met = country_threshold > 0 and subtotal >= country_threshold

        if config.free_shipping_all or global_threshold_met or country_threshold_met:
            if config.free_shipping_all:
                reason = 'Free shipping enabled for all orders'
            elif global_threshold_met:
                reason = f'Orders over GHS {config.free_shipping_threshold} ship free'
            else:
                reason = f'Orders over GHS {country_threshold} ship free ({normalized} rate rule)'
            return {
                'cost': Decimal('0.00'),
                'method': shipping_method,
                'method_name': method['name'],
                'estimated_days': method['estimated_days'],
                'reason': reason,
            }

        base_cost = rates['base']
        weight_cost = total_weight_kg * rates['per_kg']
        total_cost = ((base_cost + weight_cost) * method['multiplier']).quantize(Decimal('0.01'))

        return {
            'cost': total_cost,
            'method': shipping_method,
            'method_name': method['name'],
            'estimated_days': method['estimated_days'],
            'breakdown': {
                'base_rate': base_cost,
                'weight_cost': weight_cost,
                'multiplier': method['multiplier'],
            },
        }

    @classmethod
    def calculate_order_weight(cls, items: List[Dict]) -> Decimal:
        """Calculate total weight of order items"""
        total_weight = Decimal('0.00')

        for item in items:
            variant = item.get('variant')
            if variant and variant.weight:
                weight = Decimal(str(variant.weight))
                quantity = Decimal(str(item.get('quantity', 1)))
                total_weight += weight * quantity
            else:
                # Default weight 0.5kg per item
                total_weight += Decimal('0.5') * Decimal(str(item.get('quantity', 1)))

        return total_weight

    @classmethod
    def get_shipping_options(
        cls,
        country_code: str,
        total_weight_kg: Decimal,
        subtotal: Decimal,
    ) -> List[Dict]:
        """Get all available shipping options"""
        options = []

        for method_id, method in cls._get_methods().items():
            if not method.get('enabled', True):
                continue
            calculation = cls.calculate_shipping_cost(
                country_code=country_code,
                total_weight_kg=total_weight_kg,
                subtotal=subtotal,
                shipping_method=method_id,
            )
            option = {
                'id': method_id,
                'name': method['name'],
                'cost': float(calculation['cost']),
                'estimated_days': calculation['estimated_days'],
                'is_free': calculation['cost'] == 0,
            }
            if calculation['cost'] == 0 and calculation.get('reason'):
                option['reason'] = calculation['reason']
            options.append(option)

        return options
