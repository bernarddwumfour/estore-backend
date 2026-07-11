from decimal import Decimal

from apps.orders.models import ShippingConfig
from apps.products.tests.factories import (  # noqa: F401
    make_admin,
    make_product,
    make_user,
    make_variant,
)


def make_shipping_config(**overrides) -> ShippingConfig:
    """Fetch the singleton and apply overrides."""
    config = ShippingConfig.get()
    for field, value in overrides.items():
        setattr(config, field, value)
    if overrides:
        config.save()
    return config


def shipping_address_data(**overrides) -> dict:
    data = {
        "first_name": "Ama",
        "last_name": "Mensah",
        "email": "ama@example.com",
        "phone": "+233200000000",
        "address_line1": "12 Osu Lane",
        "city": "Accra",
        "state": "Greater Accra",
        "postal_code": "00233",
        "country": "Ghana",
    }
    data.update(overrides)
    return data


TA_RATES = [
    {
        "id": "rate_abc",
        "carrier": "DHL",
        "service_level": "DHL Express",
        "amount": 42.50,
        "currency": "GHS",
        "estimated_days": "1-2 business days",
    },
    {
        "id": "rate_def",
        "carrier": "GIG",
        "service_level": "GIG Standard",
        "amount": 18.00,
        "currency": "GHS",
        "estimated_days": "3-5 business days",
    },
]
