"""
Validators - Input validation for create/update operations
"""

from typing import Dict, Any, Tuple, Optional
from decimal import Decimal, InvalidOperation


def _default_low_stock_threshold() -> int:
    """Store-wide default from GeneralConfig; falls back to the historical 5."""
    try:
        from apps.common.models import GeneralConfig
        return GeneralConfig.get_cached().default_low_stock_threshold
    except Exception:
        return 5


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off", ""}:
            return False
    return bool(value)


def _coerce_non_negative_int(value: Any, field: str, errors: Dict[str, str]) -> Optional[int]:
    if isinstance(value, bool):
        errors[field] = "Must be non-negative integer"
        return None

    try:
        coerced = int(str(value))
    except (TypeError, ValueError):
        errors[field] = "Must be non-negative integer"
        return None

    if coerced < 0:
        errors[field] = "Must be non-negative integer"
        return None

    return coerced


def _coerce_decimal(
    value: Any,
    field: str,
    errors: Dict[str, str],
    *,
    positive: bool = False,
) -> Optional[Decimal]:
    try:
        coerced = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        errors[field] = "Valid decimal number required"
        return None

    if positive and coerced <= 0:
        errors[field] = "Must be positive"
        return None
    if not positive and coerced < 0:
        errors[field] = "Cannot be negative"
        return None

    return coerced


def validate_bulk_action(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate bulk action request"""
    errors = {}
    cleaned = {}

    # Validate action
    action = data.get("action")
    valid_actions = ["activate", "deactivate", "hide", "unhide", "delete"]

    if not action:
        errors["action"] = "This field is required"
    elif action not in valid_actions:
        errors["action"] = f"Invalid action. Must be one of: {', '.join(valid_actions)}"
    else:
        cleaned["action"] = action

    # Validate category_ids
    category_ids = data.get("category_ids", [])
    if not category_ids:
        errors["category_ids"] = "At least one category ID is required"
    elif not isinstance(category_ids, list):
        errors["category_ids"] = "Must be a list of category IDs"
    else:
        cleaned["category_ids"] = category_ids

    if errors:
        return None, errors

    return cleaned, None


def validate_product_bulk_action(
    data: Dict[str, Any],
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate product bulk action request"""
    errors = {}
    cleaned = {}

    # Validate action
    action = data.get("action")
    valid_actions = [
        "publish",
        "draft",
        "archive",  # Status actions
        "feature",
        "unfeature",  # Featured flag
        "bestseller",
        "unbestseller",  # Bestseller flag
        "new",
        "unnew",  # New flag
        "delete",  # Delete action
    ]

    if not action:
        errors["action"] = "This field is required"
    elif action not in valid_actions:
        errors["action"] = f"Invalid action. Must be one of: {', '.join(valid_actions)}"
    else:
        cleaned["action"] = action

    # Validate product_ids
    product_ids = data.get("product_ids", [])
    if not product_ids:
        errors["product_ids"] = "At least one product ID is required"
    elif not isinstance(product_ids, list):
        errors["product_ids"] = "Must be a list of product IDs"
    else:
        cleaned["product_ids"] = product_ids

    if errors:
        return None, errors

    return cleaned, None


def validate_product_create(
    data: Dict[str, Any], is_admin: bool = False
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate product creation - admin can set more fields"""
    errors = {}
    cleaned = {}

    # Required fields
    title = data.get("title", "").strip()
    if not title:
        errors["title"] = "This field is required"
    elif len(title) > 200:
        errors["title"] = "Cannot exceed 200 characters"
    else:
        cleaned["title"] = title

    description = data.get("description", "").strip()
    if not description:
        errors["description"] = "This field is required"
    else:
        cleaned["description"] = description

    category_id = data.get("category_id")
    if not category_id:
        errors["category_id"] = "This field is required"
    else:
        cleaned["category_id"] = category_id

    # Optional fields
    cleaned["features"] = data.get("features", [])
    if not isinstance(cleaned["features"], list):
        errors["features"] = "Must be a list"

    cleaned["options"] = data.get("options", {})
    if not isinstance(cleaned["options"], dict):
        errors["options"] = "Must be an object"

    # Admin-only fields
    if is_admin:
        cleaned["status"] = data.get("status", "draft")
        if cleaned["status"] not in ["draft", "published", "archived"]:
            errors["status"] = "Invalid status"

        cleaned["is_featured"] = bool(data.get("is_featured", False))
        cleaned["is_bestseller"] = bool(data.get("is_bestseller", False))
        cleaned["is_new"] = bool(data.get("is_new", False))
        cleaned["meta_title"] = data.get("meta_title", "")[:200]
        cleaned["meta_description"] = data.get("meta_description", "")[:500]
    else:
        cleaned["status"] = "draft"
        cleaned["is_featured"] = False
        cleaned["is_bestseller"] = False
        cleaned["is_new"] = False

    if errors:
        return None, errors

    return cleaned, None


def validate_product_update(
    data: Dict[str, Any], is_admin: bool = False
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate product update - admin can update more fields"""
    errors = {}
    cleaned = {}

    # Base fields
    if "title" in data:
        title = data["title"].strip()
        if not title:
            errors["title"] = "Cannot be empty"
        elif len(title) > 200:
            errors["title"] = "Cannot exceed 200 characters"
        else:
            cleaned["title"] = title

    if "description" in data:
        description = data["description"].strip()
        if not description:
            errors["description"] = "Cannot be empty"
        else:
            cleaned["description"] = description

    if "category_id" in data:
        cleaned["category_id"] = data["category_id"] if data["category_id"] else None

    if "features" in data:
        if not isinstance(data["features"], list):
            errors["features"] = "Must be a list"
        else:
            cleaned["features"] = data["features"]

    if "options" in data:
        if not isinstance(data["options"], dict):
            errors["options"] = "Must be an object"
        else:
            cleaned["options"] = data["options"]

    # Admin-only fields
    if is_admin:
        if "status" in data:
            if data["status"] not in ["draft", "published", "archived"]:
                errors["status"] = "Invalid status"
            else:
                cleaned["status"] = data["status"]

        for field in [
            "is_featured",
            "is_bestseller",
            "is_new",
            "meta_title",
            "meta_description",
        ]:
            if field in data:
                cleaned[field] = data[field]

    if errors:
        return None, errors

    return cleaned, None


def validate_variant_create(
    data: Dict[str, Any], is_admin: bool = False
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate variant creation - some fields admin-only"""
    errors = {}
    cleaned = {}

    # Required fields
    sku = str(data.get("sku", "") or "").strip()
    if not sku:
        errors["sku"] = "This field is required"
    elif len(sku) > 100:
        errors["sku"] = "Cannot exceed 100 characters"
    else:
        cleaned["sku"] = sku

    # Price validation
    if _is_blank(data.get("price")):
        errors["price"] = "Valid decimal number required"
    else:
        price = _coerce_decimal(data.get("price"), "price", errors, positive=True)
        if price is not None:
            cleaned["price"] = price

    # Attributes validation
    attributes = data.get("attributes", {})
    if not isinstance(attributes, dict):
        errors["attributes"] = "Must be an object"
    else:
        cleaned["attributes"] = attributes

    # Stock
    stock = _coerce_non_negative_int(data.get("stock", 0), "stock", errors)
    if stock is not None:
        cleaned["stock"] = stock

    # Admin-only fields
    if is_admin:
        discount_amount = data.get("discount_amount", 0)
        if "cost_price" in data and not _is_blank(data["cost_price"]):
            cost_price = _coerce_decimal(data["cost_price"], "cost_price", errors)
            if cost_price is not None:
                cleaned["cost_price"] = cost_price
        else:
            cleaned["cost_price"] = Decimal("0.00")

        discount_amount = _coerce_decimal(
            discount_amount, "discount_amount", errors
        )
        if discount_amount is not None:
            if discount_amount > cleaned.get("price", Decimal("0")):
                errors["discount_amount"] = "Cannot exceed price"
            else:
                cleaned["discount_amount"] = discount_amount

        cleaned["is_default"] = _coerce_bool(data.get("is_default"), False)
        cleaned["is_active"] = _coerce_bool(data.get("is_active"), True)
        low_stock_threshold = _coerce_non_negative_int(
            data.get("low_stock_threshold", _default_low_stock_threshold()),
            "low_stock_threshold", errors,
        )
        if low_stock_threshold is not None:
            cleaned["low_stock_threshold"] = low_stock_threshold

        for dim in ["weight", "height", "width", "depth"]:
            if dim in data and not _is_blank(data[dim]):
                value = _coerce_decimal(data[dim], dim, errors)
                if value is not None:
                    cleaned[dim] = value
    else:
        cleaned["discount_amount"] = Decimal(0)
        cleaned["is_default"] = False
        cleaned["is_active"] = True
        cleaned["low_stock_threshold"] = _default_low_stock_threshold()

    if errors:
        return None, errors

    return cleaned, None


def validate_variant_update(
    data: Dict[str, Any], is_admin: bool = False
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate partial variant updates.

    Multipart form fields arrive as strings, so update validation must coerce
    values before the service writes them to Decimal/Integer/Boolean fields.
    """
    errors = {}
    cleaned = {}

    if "sku" in data:
        sku = str(data.get("sku", "") or "").strip()
        if not sku:
            errors["sku"] = "This field is required"
        elif len(sku) > 100:
            errors["sku"] = "Cannot exceed 100 characters"
        else:
            cleaned["sku"] = sku

    if "price" in data:
        if _is_blank(data["price"]):
            errors["price"] = "Valid decimal number required"
        else:
            price = _coerce_decimal(data["price"], "price", errors, positive=True)
            if price is not None:
                cleaned["price"] = price

    if "attributes" in data:
        attributes = data.get("attributes", {})
        if not isinstance(attributes, dict):
            errors["attributes"] = "Must be an object"
        else:
            cleaned["attributes"] = attributes

    if "stock" in data:
        stock = _coerce_non_negative_int(data["stock"], "stock", errors)
        if stock is not None:
            cleaned["stock"] = stock

    if is_admin:
        if "cost_price" in data:
            if _is_blank(data["cost_price"]):
                cleaned["cost_price"] = Decimal("0.00")
            else:
                cost_price = _coerce_decimal(data["cost_price"], "cost_price", errors)
                if cost_price is not None:
                    cleaned["cost_price"] = cost_price

        if "discount_amount" in data:
            discount_amount = _coerce_decimal(
                data["discount_amount"], "discount_amount", errors
            )
            if discount_amount is not None:
                cleaned["discount_amount"] = discount_amount

        if "is_default" in data:
            cleaned["is_default"] = _coerce_bool(data.get("is_default"), False)

        if "is_active" in data:
            cleaned["is_active"] = _coerce_bool(data.get("is_active"), True)

        if "low_stock_threshold" in data:
            low_stock_threshold = _coerce_non_negative_int(
                data["low_stock_threshold"], "low_stock_threshold", errors
            )
            if low_stock_threshold is not None:
                cleaned["low_stock_threshold"] = low_stock_threshold

        for dim in ["weight", "height", "width", "depth"]:
            if dim in data:
                if _is_blank(data[dim]):
                    cleaned[dim] = None
                else:
                    value = _coerce_decimal(data[dim], dim, errors)
                    if value is not None:
                        cleaned[dim] = value

    if errors:
        return None, errors

    return cleaned, None


def validate_review_create(
    data: Dict[str, Any],
) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate review creation"""
    errors = {}
    cleaned = {}

    rating = data.get("rating")
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        errors["rating"] = "Must be integer between 1 and 5"
    else:
        cleaned["rating"] = rating

    comment = data.get("comment", "").strip()
    if not comment:
        errors["comment"] = "This field is required"
    elif len(comment) > 5000:
        errors["comment"] = "Cannot exceed 5000 characters"
    else:
        cleaned["comment"] = comment

    cleaned["title"] = data.get("title", "")[:200]
    cleaned["is_verified_purchase"] = False

    if errors:
        return None, errors

    return cleaned, None
