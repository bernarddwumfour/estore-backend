"""
General config schemas — validation and serialization for store-wide settings.
"""

from decimal import Decimal, InvalidOperation
from typing import Dict, Optional, Tuple

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.common.models import GeneralConfig, default_notifications

PAYMENT_METHODS = {"paystack", "pod"}
NOTIFICATION_EVENTS = ("order_confirmation", "order_shipped", "order_delivered")
NOTIFICATION_CHANNELS = ("email", "sms", "whatsapp")


def _parse_decimal(value, field: str, errors: Dict, *, minimum=Decimal("0"), maximum=None):
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


def _parse_int(value, field: str, errors: Dict, *, minimum=0, maximum=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        errors[field] = f"{field.replace('_', ' ').capitalize()} must be a whole number"
        return None
    if parsed < minimum or (maximum is not None and parsed > maximum):
        errors[field] = f"{field.replace('_', ' ').capitalize()} is out of range"
        return None
    return parsed


def _clean_notifications(value, errors: Dict):
    if not isinstance(value, dict):
        errors["notifications"] = "Notifications must be an object"
        return None
    cleaned = default_notifications()
    for event in NOTIFICATION_EVENTS:
        entry = value.get(event)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            errors["notifications"] = f"Notifications for '{event}' must be an object"
            return None
        for channel in NOTIFICATION_CHANNELS:
            if channel in entry:
                cleaned[event][channel] = bool(entry[channel])
    return cleaned


def validate_general_config_update(data: Dict) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate a partial general-config update. Only provided keys are cleaned."""
    errors: Dict = {}
    cleaned: Dict = {}

    bool_fields = (
        "paystack_enabled", "pod_enabled", "guest_checkout_enabled", "hide_out_of_stock",
        "tax_inclusive",
    )
    for field in bool_fields:
        if field in data:
            if not isinstance(data[field], bool):
                errors[field] = f"{field.replace('_', ' ').capitalize()} must be true or false"
            else:
                cleaned[field] = data[field]

    if "default_payment_method" in data:
        method = data["default_payment_method"]
        if method not in PAYMENT_METHODS:
            errors["default_payment_method"] = (
                f"Invalid payment method. Must be one of: {', '.join(sorted(PAYMENT_METHODS))}"
            )
        else:
            cleaned["default_payment_method"] = method

    decimal_fields = {
        "pod_max_order_value": {},
        "paystack_min_amount": {},
        "paystack_max_amount": {},
        "min_order_value": {},
        "tax_rate": {"maximum": Decimal("100")},
    }
    for field, kwargs in decimal_fields.items():
        if field in data:
            parsed = _parse_decimal(data[field], field, errors, **kwargs)
            if field not in errors:
                cleaned[field] = parsed

    int_fields = ("pod_max_quantity", "auto_cancel_unpaid_hours", "default_low_stock_threshold")
    for field in int_fields:
        if field in data:
            parsed = _parse_int(data[field], field, errors)
            if field not in errors:
                cleaned[field] = parsed

    if "notifications" in data:
        parsed = _clean_notifications(data["notifications"], errors)
        if parsed is not None:
            cleaned["notifications"] = parsed

    if "order_number_prefix" in data:
        prefix = data["order_number_prefix"]
        if not isinstance(prefix, str) or not prefix.strip() or not prefix.strip().isalnum():
            errors["order_number_prefix"] = "Prefix must be alphanumeric"
        else:
            cleaned["order_number_prefix"] = prefix.strip().upper()[:10]

    if "support_email" in data:
        email = (data["support_email"] or "").strip()
        if email:
            try:
                validate_email(email)
                cleaned["support_email"] = email[:255]
            except ValidationError:
                errors["support_email"] = "Invalid email address"
        else:
            cleaned["support_email"] = ""

    if "currency" in data:
        currency = (data["currency"] or "").strip().upper()
        if len(currency) != 3 or not currency.isalpha():
            errors["currency"] = "Currency must be a 3-letter code"
        else:
            cleaned["currency"] = currency

    if "store_country" in data:
        country = (data["store_country"] or "").strip().upper()
        if country and (len(country) != 2 or not country.isalpha()):
            errors["store_country"] = "Country must be a 2-letter code"
        else:
            cleaned["store_country"] = country

    text_fields = {
        "store_name": 100, "support_phone": 30, "store_state": 80,
        "store_city": 80, "store_postal_code": 20, "store_address": 255,
    }
    for field, max_length in text_fields.items():
        if field in data:
            value = data[field]
            if not isinstance(value, str):
                errors[field] = f"{field.replace('_', ' ').capitalize()} must be a string"
            else:
                cleaned[field] = value.strip()[:max_length]

    # Cross-field: paystack bounds must stay ordered (consider pending values)
    if not errors and ("paystack_min_amount" in cleaned or "paystack_max_amount" in cleaned):
        current = GeneralConfig.get()
        min_amount = cleaned.get("paystack_min_amount", current.paystack_min_amount)
        max_amount = cleaned.get("paystack_max_amount", current.paystack_max_amount)
        if min_amount > max_amount:
            errors["paystack_min_amount"] = "Minimum amount cannot exceed maximum amount"

    if errors:
        return None, errors
    if not cleaned:
        return None, {"general": "No valid configuration fields provided"}
    return cleaned, None


def serialize_general_config(config: GeneralConfig) -> Dict:
    return {
        "paystack_enabled": config.paystack_enabled,
        "pod_enabled": config.pod_enabled,
        "default_payment_method": config.default_payment_method,
        "pod_max_order_value": str(config.pod_max_order_value),
        "pod_max_quantity": config.pod_max_quantity,
        "paystack_min_amount": str(config.paystack_min_amount),
        "paystack_max_amount": str(config.paystack_max_amount),
        "notifications": config.notifications or default_notifications(),
        "guest_checkout_enabled": config.guest_checkout_enabled,
        "min_order_value": str(config.min_order_value),
        "order_number_prefix": config.order_number_prefix,
        "auto_cancel_unpaid_hours": config.auto_cancel_unpaid_hours,
        "store_name": config.store_name,
        "support_email": config.support_email,
        "support_phone": config.support_phone,
        "currency": config.currency,
        "store_country": config.store_country,
        "store_state": config.store_state,
        "store_city": config.store_city,
        "store_postal_code": config.store_postal_code,
        "store_address": config.store_address,
        "default_low_stock_threshold": config.default_low_stock_threshold,
        "hide_out_of_stock": config.hide_out_of_stock,
        "tax_rate": str(config.tax_rate),
        "tax_inclusive": config.tax_inclusive,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }
