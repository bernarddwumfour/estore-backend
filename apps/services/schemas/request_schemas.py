from django.core.exceptions import ValidationError
from django.core.validators import validate_email


def validate_service_request(data):
    if not isinstance(data, dict):
        return None, {"request": "Request body must be an object"}

    errors = {}
    cleaned = {}
    limits = {
        "service_type": 220,
        "custom_service_type": 200,
        "device_model": 200,
        "customer_name": 200,
        "customer_email": 254,
        "customer_phone": 40,
        "issue_description": 5000,
    }
    for field, limit in limits.items():
        value = data.get(field, "")
        value = value.strip() if isinstance(value, str) else ""
        if len(value) > limit:
            errors[field] = f"Must be {limit} characters or fewer"
        cleaned[field] = value

    for field in ("service_type", "device_model", "customer_name", "customer_email", "customer_phone", "issue_description"):
        if not cleaned[field]:
            errors[field] = "Required"
    if cleaned["service_type"] == "other" and not cleaned["custom_service_type"]:
        errors["custom_service_type"] = "Required for other services"
    if cleaned["customer_email"]:
        try:
            validate_email(cleaned["customer_email"])
        except ValidationError:
            errors["customer_email"] = "Enter a valid email address"
    return (cleaned, errors) if not errors else (None, errors)
