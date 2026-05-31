# apps/orders/services/shipping_calculator.py
import logging
from decimal import Decimal
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ShippingCalculator:
    """Shipping cost calculation based on various factors"""
    
    # Base rates by country/region
    BASE_RATES = {
        'GH': {  # Ghana
            'base': Decimal('15.00'),
            'per_kg': Decimal('5.00'),
            'free_shipping_threshold': Decimal('500.00'),
        },
        'NG': {  # Nigeria
            'base': Decimal('20.00'),
            'per_kg': Decimal('7.00'),
            'free_shipping_threshold': Decimal('150.00'),
        },
        'KE': {  # Kenya
            'base': Decimal('18.00'),
            'per_kg': Decimal('6.00'),
            'free_shipping_threshold': Decimal('120.00'),
        },
        'ZA': {  # South Africa
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
    
    # Shipping methods
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
        # Get rates for country
        rates = cls.BASE_RATES.get(country_code.upper(), cls.BASE_RATES['DEFAULT'])
        
        # Free shipping if subtotal exceeds threshold
        if subtotal >= rates['free_shipping_threshold']:
            return {
                'cost': Decimal('0.00'),
                'method': shipping_method,
                'method_name': cls.SHIPPING_METHODS.get(shipping_method, {}).get('name', 'Standard Shipping'),
                'estimated_days': cls.SHIPPING_METHODS.get(shipping_method, {}).get('estimated_days', '3-7 business days'),
                'reason': 'Free shipping',
            }
        
        # Calculate base cost
        base_cost = rates['base']
        weight_cost = total_weight_kg * rates['per_kg']
        
        # Apply method multiplier
        method = cls.SHIPPING_METHODS.get(shipping_method, cls.SHIPPING_METHODS['standard'])
        total_cost = (base_cost + weight_cost) * method['multiplier']
        
        # Round to 2 decimal places
        total_cost = total_cost.quantize(Decimal('0.01'))
        
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
        
        for method_id, method in cls.SHIPPING_METHODS.items():
            calculation = cls.calculate_shipping_cost(
                country_code=country_code,
                total_weight_kg=total_weight_kg,
                subtotal=subtotal,
                shipping_method=method_id,
            )
            options.append({
                'id': method_id,
                'name': method['name'],
                'cost': float(calculation['cost']),
                'estimated_days': calculation['estimated_days'],
                'is_free': calculation['cost'] == 0,
            })
        
        return options