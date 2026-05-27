"""
Shipping Views - Shipping rate calculation endpoints
"""

import logging
from decimal import Decimal
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
from estore.utils.responses import APIResponse
from apps.users.decorators.auth import json_request_required

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def get_shipping_rates(request):
    """Get real-time shipping rates from Terminal Africa"""
    try:
        data = request.json_data
        
        shipping_address = data.get('shipping_address', {})
        items = data.get('items', [])
        currency = data.get('currency', 'GHS')
        
        if not shipping_address:
            return APIResponse.bad_request("Shipping address is required")
        
        if not items:
            return APIResponse.bad_request("Items are required")
        
        origin = {
            "country": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('country', 'GH'),
            "state": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('state', 'Greater Accra'),
            "city": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('city', 'Accra'),
            "postal_code": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('postal_code', '00233'),
            "address": getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {}).get('address', ''),
        }
        
        destination = {
            "country": shipping_address.get('country', 'GH'),
            "state": shipping_address.get('state', ''),
            "city": shipping_address.get('city', ''),
            "postal_code": shipping_address.get('postal_code', ''),
            "address": shipping_address.get('address_line1', ''),
        }
        
        total_weight = Decimal('0.00')
        
        for item in items:
            variant_id = item.get('variant_id')
            quantity = item.get('quantity', 1)
            
            try:
                from apps.products.models import ProductVariant
                variant = ProductVariant.objects.get(id=variant_id)
                if variant.weight:
                    total_weight += Decimal(str(variant.weight)) * Decimal(str(quantity))
                else:
                    total_weight += Decimal('0.5') * Decimal(str(quantity))
            except ProductVariant.DoesNotExist:
                total_weight += Decimal('0.5') * Decimal(str(quantity))
        
        parcels = [{
            "weight": float(total_weight),
            "quantity": 1,
            "description": "Package",
        }]
        
        from apps.orders.terminal_africa_service import TerminalAfricaService
        
        rates, error = TerminalAfricaService.get_shipping_rates(
            origin=origin,
            destination=destination,
            parcels=parcels,
            currency=currency,
        )
        
        if error or not rates:
            subtotal = Decimal('0.00')
            
            for item in items:
                variant_id = item.get('variant_id')
                quantity = item.get('quantity', 1)
                try:
                    from apps.products.models import ProductVariant
                    variant = ProductVariant.objects.get(id=variant_id)
                    subtotal += variant.price * Decimal(str(quantity))
                except ProductVariant.DoesNotExist:
                    pass
            
            from apps.orders.shipping_calculator import ShippingCalculator
            rates = ShippingCalculator.get_shipping_options(
                country_code=destination['country'],
                total_weight_kg=total_weight,
                subtotal=subtotal,
            )
            
            formatted_rates = []
            for rate in rates:
                formatted_rates.append({
                    'id': rate['id'],
                    'carrier': 'Internal',
                    'carrier_code': 'internal',
                    'service_level': rate['name'],
                    'service_level_code': rate['id'],
                    'amount': rate['cost'],
                    'currency': currency,
                    'estimated_days': rate.get('estimated_days', '3-7 business days'),
                    'guaranteed_delivery': False,
                    'description': rate.get('estimated_days', ''),
                })
            rates = formatted_rates
        
        return APIResponse.success(
            data={
                "rates": rates,
                "origin": origin,
                "destination": destination,
                "weight_kg": float(total_weight),
            },
            message="Shipping rates retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Get shipping rates error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def get_shipping_options(request):
    """Get shipping options based on internal calculation"""
    try:
        data = request.json_data
        
        country_code = data.get('country_code', 'GH')
        subtotal = data.get('subtotal', 0)
        items = data.get('items', [])
        
        if not items:
            return APIResponse.bad_request("Items are required")
        
        from apps.orders.shipping_calculator import ShippingCalculator
        
        total_weight = Decimal('0.00')
        
        for item in items:
            variant_id = item.get('variant_id')
            quantity = item.get('quantity', 1)
            
            try:
                from apps.products.models import ProductVariant
                variant = ProductVariant.objects.get(id=variant_id)
                if variant.weight:
                    total_weight += Decimal(str(variant.weight)) * Decimal(str(quantity))
                else:
                    total_weight += Decimal('0.5') * Decimal(str(quantity))
            except ProductVariant.DoesNotExist:
                total_weight += Decimal('0.5') * Decimal(str(quantity))
        
        options = ShippingCalculator.get_shipping_options(
            country_code=country_code,
            total_weight_kg=total_weight,
            subtotal=Decimal(str(subtotal)),
        )
        
        return APIResponse.success(
            data={
                "options": options,
                "weight_kg": float(total_weight),
                "subtotal": subtotal,
                "country": country_code,
            },
            message="Shipping options retrieved successfully"
        )
        
    except Exception as e:
        logger.error(f"Get shipping options error: {str(e)}")
        return APIResponse.server_error()