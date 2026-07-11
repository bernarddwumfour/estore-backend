# apps/orders/shipping_quote_service.py
"""
Unified shipping quoting and selection resolution.

Terminal Africa is the primary rate source when enabled/configured; the
config-driven internal calculator is the fallback. Config overlays
(free-shipping-all, threshold, popular addresses, pickup, allowed
countries) apply on top of either source. resolve_selected_option() is
the single server-side authority for what an order is charged — quoted
and charged amounts always agree.
"""

import logging
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings

from apps.orders.models import ShippingConfig

logger = logging.getLogger(__name__)

COUNTRY_ALIASES = {
    "GHANA": "GH",
    "NIGERIA": "NG",
    "KENYA": "KE",
    "SOUTH AFRICA": "ZA",
    "TOGO": "TG",
    "IVORY COAST": "CI",
    "COTE D'IVOIRE": "CI",
    "BURKINA FASO": "BF",
    "UNITED STATES": "US",
    "UNITED KINGDOM": "GB",
}

FREE_OPTION_ID = "free"
PICKUP_OPTION_ID = "pickup"
CARRIER_RATE_PREFIX = "ta_"


def _shipping_origin() -> Dict[str, str]:
    """Origin address for carrier quotes: store identity config first
    (per-field), then settings.DEFAULT_SHIPPING_ORIGIN, then literals."""
    defaults = getattr(settings, 'DEFAULT_SHIPPING_ORIGIN', {})
    config = None
    try:
        from apps.common.models import GeneralConfig
        config = GeneralConfig.get_cached()
    except Exception:
        pass

    def pick(config_attr: str, settings_key: str, fallback: str) -> str:
        if config is not None:
            value = getattr(config, config_attr, "")
            if value:
                return value
        return defaults.get(settings_key, fallback)

    return {
        "country": pick("store_country", "country", "GH"),
        "state": pick("store_state", "state", "Greater Accra"),
        "city": pick("store_city", "city", "Accra"),
        "postal_code": pick("store_postal_code", "postal_code", "00233"),
        "address": pick("store_address", "address", ""),
    }


def _to_decimal(value: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        return default


class ShippingQuoteService:
    """Quote shipping options and resolve a checkout selection to a cost"""

    @staticmethod
    def normalize_country(value: str) -> str:
        """Normalize a country name or code to an upper-case ISO-3166 alpha-2 code"""
        if not value:
            return "DEFAULT"
        value = value.strip().upper()
        if len(value) == 2:
            return value
        return COUNTRY_ALIASES.get(value, value)

    @staticmethod
    def build_items_context(items: List[Dict]) -> Tuple[Decimal, Decimal, List[Dict]]:
        """Compute (total_weight_kg, subtotal, parcels) from request items"""
        from apps.products.models import ProductVariant

        total_weight = Decimal("0.00")
        subtotal = Decimal("0.00")

        for item in items:
            variant_id = item.get("variant_id")
            quantity = Decimal(str(item.get("quantity", 1)))
            try:
                variant = ProductVariant.objects.get(id=variant_id, is_active=True)
                if variant.weight:
                    total_weight += Decimal(str(variant.weight)) * quantity
                else:
                    total_weight += Decimal("0.5") * quantity
                subtotal += variant.discounted_price * quantity
            except (ProductVariant.DoesNotExist, ValueError, TypeError):
                total_weight += Decimal("0.5") * quantity

        parcels = [{
            "weight": float(total_weight),
            "quantity": 1,
            "description": "Package",
        }]
        return total_weight, subtotal, parcels

    # ---------- Config overlay helpers ----------

    @classmethod
    def country_allowed(cls, config: ShippingConfig, country: str) -> bool:
        allowed = config.allowed_countries or []
        if not allowed:
            return True
        code = cls.normalize_country(country)
        return any(
            (entry.get("code") or "").upper() == code
            for entry in allowed
            if isinstance(entry, dict)
        )

    @classmethod
    def find_popular_address(
        cls, config: ShippingConfig, address_id: str, country: str = "", region: str = ""
    ) -> Optional[Dict]:
        """Find an active popular address by id, optionally checking destination match"""
        code = cls.normalize_country(country) if country else ""
        for entry in config.popular_addresses or []:
            if not isinstance(entry, dict) or not entry.get("active", True):
                continue
            if str(entry.get("id")) != str(address_id):
                continue
            if code and cls.normalize_country(entry.get("country", "")) != code:
                return None
            if region and (entry.get("region") or "").strip().lower() != region.strip().lower():
                # Region mismatch is tolerated — the address is still a valid
                # config entry; region only drives checkout filtering.
                pass
            return entry
        return None

    @staticmethod
    def _apply_fees(config: ShippingConfig, cost: Decimal, internal_source: bool) -> Decimal:
        """Apply surcharge (internal only), handling fee, and cap to a non-free cost"""
        if cost <= 0:
            return Decimal("0.00")
        if internal_source:
            surcharge = _to_decimal(config.fallback_surcharge_percent)
            if surcharge > 0:
                cost += (cost * surcharge / Decimal("100"))
        handling = _to_decimal(config.handling_fee)
        if handling > 0:
            cost += handling
        cap = config.max_shipping_cap
        if cap is not None and cost > cap:
            cost = cap
        return cost.quantize(Decimal("0.01"))

    @staticmethod
    def _free_option(reason: str = "", name: str = "Free Shipping") -> Dict:
        option = {
            "id": FREE_OPTION_ID,
            "name": name,
            "carrier": "Store",
            "cost": 0.0,
            "currency": "GHS",
            "estimated_days": "3-7 business days",
            "is_free": True,
            "source": "free",
        }
        if reason:
            option["reason"] = reason
        return option

    @staticmethod
    def _global_threshold_met(config: ShippingConfig, subtotal: Decimal) -> bool:
        """A threshold of 0 or less means the rule is disabled"""
        return (
            config.free_shipping_threshold is not None
            and config.free_shipping_threshold > 0
            and subtotal >= config.free_shipping_threshold
        )

    @staticmethod
    def _pickup_option() -> Dict:
        return {
            "id": PICKUP_OPTION_ID,
            "name": "In-store Pickup",
            "carrier": "Store",
            "cost": 0.0,
            "currency": "GHS",
            "estimated_days": "Same day",
            "is_free": True,
            "source": "pickup",
        }

    # ---------- Quoting ----------

    @classmethod
    def get_quote_options(
        cls,
        destination: Dict,
        items: List[Dict],
        currency: str = "GHS",
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Build the unified shipping options list for checkout"""
        config = ShippingConfig.get_cached()
        country = destination.get("country", "")

        if not cls.country_allowed(config, country):
            return None, "We do not ship to this destination"

        total_weight, subtotal, parcels = cls.build_items_context(items)
        options: List[Dict] = []
        source = "internal"

        if config.free_shipping_all:
            options = [cls._free_option("Free shipping enabled for all orders")]
            source = "free"
        elif cls._global_threshold_met(config, subtotal):
            options = [cls._free_option(
                f"Orders over GHS {config.free_shipping_threshold} ship free"
            )]
            source = "free"
        else:
            options, source = cls._rate_options(
                config, destination, parcels, total_weight, subtotal, currency
            )

        if config.pickup_enabled:
            options.insert(0, cls._pickup_option())

        return {
            "options": options,
            "weight_kg": float(total_weight),
            "subtotal": float(subtotal),
            "source": source,
        }, None

    @classmethod
    def _rate_options(
        cls,
        config: ShippingConfig,
        destination: Dict,
        parcels: List[Dict],
        total_weight: Decimal,
        subtotal: Decimal,
        currency: str,
    ) -> Tuple[List[Dict], str]:
        """Carrier-first rate options with internal fallback"""
        from apps.orders.terminal_africa_service import TerminalAfricaService

        if config.use_carrier_rates and TerminalAfricaService.is_configured():
            origin = _shipping_origin()
            rates, error = TerminalAfricaService.get_shipping_rates(
                origin=origin,
                destination=destination,
                parcels=parcels,
                currency=currency,
            )
            if not error and rates:
                options = []
                for rate in rates:
                    cost = cls._apply_fees(
                        config, _to_decimal(rate.get("amount")), internal_source=False
                    )
                    options.append({
                        "id": f"{CARRIER_RATE_PREFIX}{rate.get('id')}",
                        "name": rate.get("service_level") or rate.get("carrier", "Courier"),
                        "carrier": rate.get("carrier", "Courier"),
                        "cost": float(cost),
                        "currency": rate.get("currency", currency),
                        "estimated_days": rate.get("estimated_days", ""),
                        "is_free": cost == 0,
                        "source": "terminal_africa",
                    })
                return options, "terminal_africa"

        from apps.orders.shipping_calculator import ShippingCalculator

        internal = ShippingCalculator.get_shipping_options(
            country_code=destination.get("country", ""),
            total_weight_kg=total_weight,
            subtotal=subtotal,
        )
        options = []
        for opt in internal:
            cost = cls._apply_fees(config, _to_decimal(opt.get("cost")), internal_source=True)
            option = {
                "id": opt["id"],
                "name": opt["name"],
                "carrier": "Store Courier",
                "cost": float(cost),
                "currency": currency,
                "estimated_days": opt.get("estimated_days", ""),
                "is_free": cost == 0,
                "source": "internal",
            }
            if cost == 0 and opt.get("reason"):
                option["reason"] = opt["reason"]
            options.append(option)
        return options, "internal"

    # ---------- Selection resolution (order creation) ----------

    @classmethod
    def resolve_selected_option(
        cls,
        shipping_method_id: str,
        popular_address_id: str,
        destination: Dict,
        items: List[Dict],
        subtotal: Decimal,
        total_weight: Decimal,
        currency: str = "GHS",
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Resolve the checkout selection to the authoritative shipping charge.

        Returns ({cost, method_name, is_pickup}, error_dict).
        """
        config = ShippingConfig.get_cached()
        country = destination.get("country", "")

        if not cls.country_allowed(config, country):
            return None, {"shipping_address": "We do not ship to this destination"}

        if config.free_shipping_all:
            return {"cost": Decimal("0.00"), "method_name": "Free Shipping", "is_pickup": False}, None

        if popular_address_id:
            entry = cls.find_popular_address(config, popular_address_id, country=country)
            if not entry:
                return None, {
                    "popular_address_id": "Selected delivery area is not available"
                }
            price = _to_decimal(entry.get("price"))
            name = entry.get("name", "Popular address")
            method_name = (
                f"Free delivery — {name}" if price <= 0 else f"Delivery — {name}"
            )
            return {"cost": max(price, Decimal("0.00")), "method_name": method_name[:100], "is_pickup": False}, None

        if shipping_method_id == PICKUP_OPTION_ID:
            if not config.pickup_enabled:
                return None, {"shipping_method": "In-store pickup is not available"}
            return {"cost": Decimal("0.00"), "method_name": "In-store Pickup", "is_pickup": True}, None

        if cls._global_threshold_met(config, subtotal):
            return {"cost": Decimal("0.00"), "method_name": "Free Shipping", "is_pickup": False}, None

        if shipping_method_id == FREE_OPTION_ID:
            # Client selected the free option but no free rule matches anymore
            return None, {
                "shipping_method": "Selected shipping rate is no longer available. Please refresh shipping options."
            }

        if shipping_method_id.startswith(CARRIER_RATE_PREFIX):
            return cls._resolve_carrier_rate(
                config, shipping_method_id, destination, total_weight, currency
            )

        # Internal method key (or empty/legacy value → standard)
        from apps.orders.shipping_calculator import ShippingCalculator

        methods = config.shipping_methods or {}
        known = methods.get(shipping_method_id)
        if known is not None and not known.get("enabled", True):
            # Explicitly chosen method was disabled since quoting — never
            # silently charge a different method than the customer picked
            return None, {
                "shipping_method": "Selected shipping rate is no longer available. Please refresh shipping options."
            }
        method_key = shipping_method_id if known is not None else "standard"
        calculation = ShippingCalculator.calculate_shipping_cost(
            country_code=country,
            total_weight_kg=total_weight,
            subtotal=subtotal,
            shipping_method=method_key,
        )
        cost = cls._apply_fees(config, _to_decimal(calculation["cost"]), internal_source=True)
        return {
            "cost": cost,
            "method_name": calculation["method_name"],
            "is_pickup": False,
        }, None

    @classmethod
    def _resolve_carrier_rate(
        cls,
        config: ShippingConfig,
        shipping_method_id: str,
        destination: Dict,
        total_weight: Decimal,
        currency: str,
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Re-quote Terminal Africa (5-min cached) and match the selected rate id"""
        from apps.orders.terminal_africa_service import TerminalAfricaService

        stale_error = {
            "shipping_method": "Selected shipping rate is no longer available. Please refresh shipping options."
        }
        if not (config.use_carrier_rates and TerminalAfricaService.is_configured()):
            return None, stale_error

        rate_id = shipping_method_id[len(CARRIER_RATE_PREFIX):]
        parcels = [{
            "weight": float(total_weight),
            "quantity": 1,
            "description": "Package",
        }]
        origin = _shipping_origin()
        rates, error = TerminalAfricaService.get_shipping_rates(
            origin=origin, destination=destination, parcels=parcels, currency=currency
        )
        if error or not rates:
            return None, stale_error

        for rate in rates:
            if str(rate.get("id")) == rate_id:
                cost = cls._apply_fees(config, _to_decimal(rate.get("amount")), internal_source=False)
                name = rate.get("service_level") or rate.get("carrier", "Courier")
                return {"cost": cost, "method_name": str(name)[:100], "is_pickup": False}, None

        return None, stale_error
