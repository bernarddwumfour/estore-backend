"""
Shipping schemas — validation and serialization for the shipping config.
"""

import uuid
from decimal import Decimal, InvalidOperation
from typing import Dict, Optional, Tuple


def _parse_decimal(value, field: str, errors: Dict, *, minimum=Decimal("0"), maximum=None, allow_null=False):
    if value is None:
        if allow_null:
            return None
        errors[field] = f"{field.replace('_', ' ').capitalize()} is required"
        return None
    try:
        parsed = Decimal(str(value))
    except (TypeError, ValueError, InvalidOperation):
        errors[field] = f"{field.replace('_', ' ').capitalize()} must be a number"
        return None
    if minimum is not None and parsed < minimum:
        errors[field] = f"{field.replace('_', ' ').capitalize()} cannot be less than {minimum}"
        return None
    if maximum is not None and parsed > maximum:
        errors[field] = f"{field.replace('_', ' ').capitalize()} cannot exceed {maximum}"
        return None
    return parsed


def _clean_allowed_countries(value, errors: Dict):
    if not isinstance(value, list):
        errors["allowed_countries"] = "Allowed countries must be a list"
        return None
    cleaned = []
    for entry in value:
        code = (entry.get("code") or "").strip().upper() if isinstance(entry, dict) else ""
        name = (entry.get("name") or "").strip() if isinstance(entry, dict) else ""
        if len(code) != 2 or not code.isalpha() or not name:
            errors["allowed_countries"] = "Each country needs a 2-letter code and a name"
            return None
        cleaned.append({"code": code, "name": name[:60]})
    return cleaned


def _clean_fallback_rates(value, errors: Dict):
    if not isinstance(value, dict) or "DEFAULT" not in value:
        errors["fallback_rates"] = "Fallback rates must be an object containing a DEFAULT entry"
        return None
    cleaned = {}
    for code, entry in value.items():
        code_up = str(code).strip().upper()
        if code_up != "DEFAULT" and (len(code_up) != 2 or not code_up.isalpha()):
            errors["fallback_rates"] = f"Invalid country code: {code}"
            return None
        if not isinstance(entry, dict):
            errors["fallback_rates"] = f"Rates for {code_up} must be an object"
            return None
        rate_errors: Dict = {}
        base = _parse_decimal(entry.get("base"), "base", rate_errors)
        per_kg = _parse_decimal(entry.get("per_kg"), "per_kg", rate_errors)
        threshold = _parse_decimal(
            entry.get("free_shipping_threshold"), "free_shipping_threshold",
            rate_errors, allow_null=True,
        )
        if rate_errors:
            errors["fallback_rates"] = f"Invalid rates for {code_up}: {', '.join(rate_errors.values())}"
            return None
        cleaned[code_up] = {
            "base": str(base),
            "per_kg": str(per_kg),
            "free_shipping_threshold": str(threshold) if threshold is not None else "999999",
        }
    return cleaned


def _clean_shipping_methods(value, errors: Dict):
    if not isinstance(value, dict) or not value:
        errors["shipping_methods"] = "At least one shipping method is required"
        return None
    cleaned = {}
    for key, entry in value.items():
        key_clean = str(key).strip().lower()
        if not key_clean or not isinstance(entry, dict):
            errors["shipping_methods"] = "Invalid shipping method entry"
            return None
        name = (entry.get("name") or "").strip()
        if not name:
            errors["shipping_methods"] = f"Method '{key_clean}' needs a name"
            return None
        method_errors: Dict = {}
        multiplier = _parse_decimal(entry.get("multiplier"), "multiplier", method_errors)
        if method_errors or multiplier is None or multiplier <= 0:
            errors["shipping_methods"] = f"Method '{key_clean}' needs a multiplier greater than 0"
            return None
        cleaned[key_clean] = {
            "name": name[:60],
            "multiplier": str(multiplier),
            "estimated_days": (entry.get("estimated_days") or "")[:60],
            "enabled": bool(entry.get("enabled", True)),
        }
    if not any(method["enabled"] for method in cleaned.values()):
        errors["shipping_methods"] = "At least one shipping method must be enabled"
        return None
    return cleaned


def _clean_popular_addresses(value, errors: Dict):
    if not isinstance(value, list):
        errors["popular_addresses"] = "Popular addresses must be a list"
        return None
    cleaned = []
    seen_ids = set()
    for entry in value:
        if not isinstance(entry, dict):
            errors["popular_addresses"] = "Each popular address must be an object"
            return None
        name = (entry.get("name") or "").strip()
        region = (entry.get("region") or "").strip()
        country = (entry.get("country") or "").strip().upper()
        if not name or not region or len(country) != 2 or not country.isalpha():
            errors["popular_addresses"] = (
                "Each popular address needs a name, region and 2-letter country code"
            )
            return None
        addr_errors: Dict = {}
        price = _parse_decimal(entry.get("price", "0.00"), "price", addr_errors)
        if addr_errors:
            errors["popular_addresses"] = f"Invalid price for '{name}'"
            return None
        addr_id = str(entry.get("id") or uuid.uuid4())
        if addr_id in seen_ids:
            errors["popular_addresses"] = "Duplicate popular address id"
            return None
        seen_ids.add(addr_id)
        cleaned.append({
            "id": addr_id,
            "name": name[:80],
            "region": region[:80],
            "country": country,
            "price": str(price),
            "active": bool(entry.get("active", True)),
        })
    return cleaned


def validate_shipping_config_update(data: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate a partial shipping-config update. Only provided keys are cleaned."""
    errors: Dict = {}
    cleaned: Dict = {}

    for flag in ("use_carrier_rates", "free_shipping_all", "pickup_enabled"):
        if flag in data:
            if not isinstance(data[flag], bool):
                errors[flag] = f"{flag.replace('_', ' ').capitalize()} must be true or false"
            else:
                cleaned[flag] = data[flag]

    if "free_shipping_threshold" in data:
        parsed = _parse_decimal(
            data["free_shipping_threshold"], "free_shipping_threshold", errors, allow_null=True
        )
        if "free_shipping_threshold" not in errors:
            if parsed is not None and parsed <= 0:
                errors["free_shipping_threshold"] = (
                    "Threshold must be greater than 0 — leave empty to disable"
                )
            else:
                cleaned["free_shipping_threshold"] = parsed

    if "handling_fee" in data:
        parsed = _parse_decimal(data["handling_fee"], "handling_fee", errors)
        if "handling_fee" not in errors:
            cleaned["handling_fee"] = parsed

    if "max_shipping_cap" in data:
        parsed = _parse_decimal(data["max_shipping_cap"], "max_shipping_cap", errors, allow_null=True)
        if "max_shipping_cap" not in errors:
            cleaned["max_shipping_cap"] = parsed

    if "fallback_surcharge_percent" in data:
        parsed = _parse_decimal(
            data["fallback_surcharge_percent"], "fallback_surcharge_percent",
            errors, maximum=Decimal("100"),
        )
        if "fallback_surcharge_percent" not in errors:
            cleaned["fallback_surcharge_percent"] = parsed

    if "allowed_countries" in data:
        parsed = _clean_allowed_countries(data["allowed_countries"], errors)
        if parsed is not None:
            cleaned["allowed_countries"] = parsed

    if "fallback_rates" in data:
        parsed = _clean_fallback_rates(data["fallback_rates"], errors)
        if parsed is not None:
            cleaned["fallback_rates"] = parsed

    if "shipping_methods" in data:
        parsed = _clean_shipping_methods(data["shipping_methods"], errors)
        if parsed is not None:
            cleaned["shipping_methods"] = parsed

    if "popular_addresses" in data:
        parsed = _clean_popular_addresses(data["popular_addresses"], errors)
        if parsed is not None:
            cleaned["popular_addresses"] = parsed

    if errors:
        return None, errors
    if not cleaned:
        return None, {"general": "No valid configuration fields provided"}
    return cleaned, None


def serialize_popular_address(addr: Dict) -> Dict:
    price = addr.get("price", "0.00")
    try:
        is_free = Decimal(str(price)) <= 0
    except (InvalidOperation, TypeError, ValueError):
        is_free = False
    return {
        "id": addr.get("id"),
        "name": addr.get("name"),
        "region": addr.get("region"),
        "country": addr.get("country"),
        "price": str(price),
        "is_free": is_free,
        "active": addr.get("active", True),
    }


def serialize_shipping_config(config) -> Dict:
    from apps.orders.terminal_africa_service import TerminalAfricaService

    return {
        "use_carrier_rates": config.use_carrier_rates,
        "terminal_africa_configured": TerminalAfricaService.is_configured(),
        "free_shipping_all": config.free_shipping_all,
        "free_shipping_threshold": (
            str(config.free_shipping_threshold)
            if config.free_shipping_threshold is not None else None
        ),
        "pickup_enabled": config.pickup_enabled,
        "handling_fee": str(config.handling_fee),
        "max_shipping_cap": (
            str(config.max_shipping_cap) if config.max_shipping_cap is not None else None
        ),
        "fallback_surcharge_percent": str(config.fallback_surcharge_percent),
        "allowed_countries": config.allowed_countries or [],
        "fallback_rates": config.fallback_rates or {},
        "shipping_methods": config.shipping_methods or {},
        "popular_addresses": [
            serialize_popular_address(a) for a in (config.popular_addresses or [])
        ],
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }
