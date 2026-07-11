"""
Shipping Views - rate quoting, shipping meta, popular addresses, admin config
"""

import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from estore.utils.responses import APIResponse
from apps.common.logging import log_action, LogSeverity
from apps.users.decorators.auth import json_request_required, jwt_required, role_required

logger = logging.getLogger(__name__)
APP_NAME = "orders"


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def get_shipping_rates(request):
    """Get shipping rates for a destination (carrier-first, internal fallback)"""
    try:
        data = request.json_data
        shipping_address = data.get('shipping_address', {})
        items = data.get('items', [])
        currency = data.get('currency', 'GHS')

        if not shipping_address:
            return APIResponse.bad_request("Shipping address is required")
        if not items:
            return APIResponse.bad_request("Items are required")

        destination = {
            "country": shipping_address.get('country', 'GH'),
            "state": shipping_address.get('state', ''),
            "city": shipping_address.get('city', ''),
            "postal_code": shipping_address.get('postal_code', ''),
            "address": shipping_address.get('address_line1', ''),
        }

        from apps.orders.shipping_quote_service import ShippingQuoteService

        quote, error = ShippingQuoteService.get_quote_options(destination, items, currency)
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(
            data={
                "rates": quote["options"],
                "destination": destination,
                "weight_kg": quote["weight_kg"],
                "subtotal": quote["subtotal"],
                "source": quote["source"],
            },
            message="Shipping rates retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Get shipping rates error: {str(e)}", exc_info=True)
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@json_request_required
def get_shipping_options(request):
    """Get shipping options for checkout (carrier-first, internal fallback)"""
    try:
        data = request.json_data
        items = data.get('items', [])
        currency = data.get('currency', 'GHS')

        if not items:
            return APIResponse.bad_request("Items are required")

        destination = {
            "country": data.get('country_code', 'GH'),
            "state": data.get('state', ''),
            "city": data.get('city', ''),
            "postal_code": data.get('postal_code', ''),
            "address": data.get('address_line1', ''),
        }

        from apps.orders.shipping_quote_service import ShippingQuoteService

        quote, error = ShippingQuoteService.get_quote_options(destination, items, currency)
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(
            data={
                "options": quote["options"],
                "weight_kg": quote["weight_kg"],
                "subtotal": quote["subtotal"],
                "source": quote["source"],
                "country": destination["country"],
            },
            message="Shipping options retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Get shipping options error: {str(e)}", exc_info=True)
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
def get_shipping_meta(request):
    """Public: shipping metadata for checkout (allowed countries, pickup)"""
    try:
        from apps.orders.models import ShippingConfig

        config = ShippingConfig.get_cached()
        return APIResponse.success(
            data={
                "allowed_countries": config.allowed_countries or [],
                "pickup_enabled": config.pickup_enabled,
                "free_shipping_all": config.free_shipping_all,
            },
            message="Shipping metadata retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Get shipping meta error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
def get_popular_addresses(request):
    """Public: active popular delivery addresses for a country/region"""
    try:
        from apps.orders.models import ShippingConfig
        from apps.orders.schemas import serialize_popular_address
        from apps.orders.shipping_quote_service import ShippingQuoteService

        country = request.GET.get("country", "")
        region = request.GET.get("region", "")
        code = ShippingQuoteService.normalize_country(country) if country else ""

        config = ShippingConfig.get_cached()
        locations = []
        for entry in config.popular_addresses or []:
            if not isinstance(entry, dict) or not entry.get("active", True):
                continue
            if code and ShippingQuoteService.normalize_country(entry.get("country", "")) != code:
                continue
            if region and (entry.get("region") or "").strip().lower() != region.strip().lower():
                continue
            locations.append(serialize_popular_address(entry))

        return APIResponse.success(
            data={"addresses": locations},
            message="Popular addresses retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Get popular addresses error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "POST"])
@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_shipping_config(request):
    """Admin: read or update the shipping configuration."""
    try:
        from apps.orders.models import ShippingConfig
        from apps.orders.schemas import (
            serialize_shipping_config,
            validate_shipping_config_update,
        )

        config = ShippingConfig.get()

        if request.method == "POST":
            import json as json_lib
            try:
                payload = json_lib.loads(request.body or b"{}")
            except ValueError:
                return APIResponse.bad_request("Invalid JSON body")

            cleaned, errors = validate_shipping_config_update(payload)
            if errors:
                return APIResponse.validation_error(errors)

            for field, value in cleaned.items():
                setattr(config, field, value)
            config.save()

            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action="shipping_config_update",
                description="Shipping configuration updated",
                status_code=200,
                user=request.user,
                request=request,
                app_name=APP_NAME,
                extra={"updated_fields": sorted(cleaned.keys())},
            )

        return APIResponse.success(
            data=serialize_shipping_config(config),
            message="Shipping configuration retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin shipping config error: {str(e)}")
        return APIResponse.server_error()
