# apps/products/schemas.py
"""
Serialization and validation - converts models to dicts and validates input
Admin-aware serialization (some fields only visible to staff)
"""

from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Tuple, Optional, List

from apps.products.models import Category, Product, ProductVariant, VariantImage

# ==================== HELPER FUNCTIONS ====================


def _mask_sku(sku: str) -> str:
    """Mask SKU for non-admin users"""
    if len(sku) <= 8:
        return "****"
    return f"{sku[:4]}****{sku[-4:]}"


def _get_stock_status(variant) -> str:
    """Get human-readable stock status for customers"""
    if variant.stock > 10:
        return "in_stock"
    elif variant.stock > 0:
        return "low_stock"
    else:
        return "out_of_stock"


def _get_user_display_name(user) -> str:
    """Get user display name"""
    if user.first_name and user.last_name:
        return f"{user.first_name} {user.last_name}"
    return user.email.split("@")[0]


def _get_user_initials(user) -> str:
    """Get user initials for avatar"""
    if user.first_name and user.last_name:
        return f"{user.first_name[0]}{user.last_name[0]}".upper()
    return user.email[0].upper()


# ==================== OUTPUT SERIALIZERS ====================


def serialize_category(category: Category, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize a single category"""
    data = {
        "id": str(category.id),
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "parent_id": str(category.parent_id) if category.parent_id else None,
        "parent_name": category.parent.name if category.parent else None,
        "image": category.image.url if category.image else None,
        "full_path": category.full_path,
        "is_active": category.is_active,
    }
    
    # Only include admin-only fields for admin users
    if is_admin:
        data["is_hidden"] = category.is_hidden
        data["meta_title"] = category.meta_title
        data["meta_description"] = category.meta_description
        data["created_at"] = category.created_at.isoformat() if category.created_at else None
        data["updated_at"] = category.updated_at.isoformat() if category.updated_at else None
    
    return data


def serialize_category_list(
    categories: List[Category], is_admin: bool = False
) -> List[Dict]:
    """Serialize list of categories"""
    return [serialize_category(cat, is_admin) for cat in categories]


def serialize_pagination_metadata(pagination_meta: Dict) -> Dict:
    """Serialize pagination metadata"""
    return {
        "current_page": pagination_meta["current_page"],
        "per_page": pagination_meta["per_page"],
        "total": pagination_meta["total"],
        "total_pages": pagination_meta["total_pages"],
        "has_next": pagination_meta["has_next"],
        "has_previous": pagination_meta["has_previous"],
        "next_page": pagination_meta["next_page"],
        "previous_page": pagination_meta["previous_page"],
        "start_index": pagination_meta["start_index"],
        "end_index": pagination_meta["end_index"],
    }


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


def serialize_bulk_action_result(results: Dict) -> Dict:
    """Serialize bulk action result for API response"""
    return {
        "success": [
            {"id": item["id"], "name": item["name"]} for item in results["success"]
        ],
        "failed": [
            {"id": item["id"], "name": item["name"], "reason": item["reason"]}
            for item in results["failed"]
        ],
        "total": results["total"],
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
    }


def serialize_variant_image(image: VariantImage, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize variant image"""
    if not image:
        return None

    data = {
        "id": str(image.id),
        "url": image.image.url if image.image else None,
        "alt_text": image.alt_text,
        "image_type": image.image_type,
        "order": image.order,
    }

    if is_admin:
        data["is_active"] = image.is_active
        data["created_at"] = image.created_at.isoformat() if image.created_at else None

    return data


def serialize_variant(
    variant: ProductVariant, is_admin: bool = False, include_images: bool = True
) -> Dict[str, Any]:
    """Serialize variant - sensitive data only for admins"""
    if not variant:
        return None

    # Base fields (visible to everyone)
    data = {
        "id": str(variant.id),
        "sku": variant.sku if is_admin else _mask_sku(variant.sku),
        "attributes": variant.attributes,
        "price": float(variant.price),
        "discounted_price": float(variant.discounted_price),
        "discount_percentage": float(variant.discount_percentage),
        "is_in_stock": variant.is_in_stock,
        "stock": variant.stock,
        "discount_amount": float(variant.discount_amount),
        "is_default": variant.is_default,
    }

    # Admin-only fields
    if is_admin:
        data.update(
            {
                "is_active": variant.is_active,
                "is_low_stock": variant.is_low_stock,
                "low_stock_threshold": variant.low_stock_threshold,
                "dimensions": {
                    "weight": float(variant.weight) if variant.weight else None,
                    "height": float(variant.height) if variant.height else None,
                    "width": float(variant.width) if variant.width else None,
                    "depth": float(variant.depth) if variant.depth else None,
                },
                "created_at": variant.created_at.isoformat() if variant.created_at else None,
                "updated_at": variant.updated_at.isoformat() if variant.updated_at else None,
            }
        )
    else:
        # Public-facing stock info
        data["stock_status"] = _get_stock_status(variant)

    if include_images:
        data["images"] = [
            serialize_variant_image(img, is_admin)
            for img in variant.images.filter(is_active=True).order_by("order")
        ]

    return data


def serialize_product(product: Product, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize a single product with variants and images"""
    
    # Get all variants with their images
    variants = []
    for variant in product.variants.all():
        variant_data = serialize_variant(variant, is_admin=is_admin, include_images=True)
        variants.append(variant_data)
    
    # Get default variant
    default_variant = None
    if product.default_variant:
        default_variant = serialize_variant(product.default_variant, is_admin=is_admin, include_images=True)
    
    data = {
        "id": str(product.id),
        "title": product.title,
        "slug": product.slug,
        "description": product.description,
        "features": product.features,
        "options": product.options,
        "average_rating": float(product.average_rating),
        "total_reviews": product.total_reviews,
        "min_price": float(product.min_price),
        "max_price": float(product.max_price),
        "has_stock": product.has_stock,
        "total_stock": product.total_stock,
        "is_featured": product.is_featured,
        "is_bestseller": product.is_bestseller,
        "is_new": product.is_new,
        "default_variant": default_variant,
        "variants": variants,
        "category": {
            "id": str(product.category.id) if product.category else None,
            "name": product.category.name if product.category else None,
            "slug": product.category.slug if product.category else None,
        } if product.category else None,
    }
    
    # Only include admin-only fields for admin users
    if is_admin:
        data["status"] = product.status
        data["meta_title"] = product.meta_title
        data["meta_description"] = product.meta_description
        data["created_at"] = product.created_at.isoformat() if product.created_at else None
        data["updated_at"] = product.updated_at.isoformat() if product.updated_at else None
        data["published_at"] = product.published_at.isoformat() if product.published_at else None
    
    return data


def serialize_product_list(products: List[Product], is_admin: bool = False) -> List[Dict]:
    """Serialize list of products"""
    return [serialize_product(product, is_admin) for product in products]


def serialize_variant_list(variant: ProductVariant, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize variant for list view with product info"""
    if not variant:
        return None

    # Get base variant data
    variant_data = serialize_variant(variant, is_admin=is_admin, include_images=True)

    # Add product information
    product = variant.product
    variant_data["product"] = {
        "id": str(product.id),
        "title": product.title,
        "slug": product.slug,
        "status": product.status if is_admin else None,
        "category": (
            {
                "id": str(product.category.id) if product.category else None,
                "name": product.category.name if product.category else None,
            }
            if is_admin
            else None
        ),
    }

    return variant_data


def serialize_variant_list_response(variants: List[ProductVariant], is_admin: bool = False) -> List[Dict]:
    """Serialize list of variants for response"""
    return [serialize_variant_list(v, is_admin) for v in variants]


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


def serialize_product_bulk_action_result(results: Dict) -> Dict:
    """Serialize product bulk action result for API response"""
    return {
        "success": [
            {"id": item["id"], "name": item["name"]} for item in results["success"]
        ],
        "failed": [
            {"id": item["id"], "name": item["name"], "reason": item["reason"]}
            for item in results["failed"]
        ],
        "total": results["total"],
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
    }


def serialize_review(
    review, is_admin: bool = False, include_user: bool = True
) -> Dict[str, Any]:
    """Serialize review - admin sees more details"""
    if not review:
        return None

    # Base fields
    data = {
        "id": str(review.id),
        "rating": review.rating,
        "title": review.title,
        "comment": review.comment,
        "helpful_yes": review.helpful_yes,
        "helpful_no": review.helpful_no,
        "is_verified_purchase": review.is_verified_purchase,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }

    # Admin-only fields
    if is_admin:
        data.update(
            {
                "is_edited": review.is_edited,
                "is_approved": review.is_approved,
                "updated_at": review.updated_at.isoformat() if review.updated_at else None,
                "user_id": str(review.user.id) if review.user else None,
                "user_email": review.user.email if review.user else None,
            }
        )

    # User info
    if include_user and review.user:
        data["user"] = {
            "name": _get_user_display_name(review.user),
            "initials": _get_user_initials(review.user),
        }
        if is_admin:
            data["user"]["id"] = str(review.user.id)
            data["user"]["email"] = review.user.email

    return data


def serialize_wishlist_product(
    product, variants: List[Dict], is_admin: bool = False
) -> Dict[str, Any]:
    """Serialize product with specific variants from wishlist"""
    if not product:
        return None

    # Get base product data (without variants)
    base_product = serialize_product(product, is_admin=is_admin)

    # Add the wishlist-specific variants
    base_product["variants"] = variants

    # Set default variant from the variants list
    default_variant = None
    for variant in variants:
        if variant.get("is_default"):
            default_variant = variant
            break

    if not default_variant and variants:
        default_variant = variants[0]

    base_product["default_variant"] = default_variant
    base_product["variant"] = default_variant  # For backward compatibility

    return base_product


def serialize_wishlist_item(item, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize a wishlist item with product and variant info"""
    if not item:
        return None

    variant = item.variant
    product = variant.product

    # Serialize the variant
    variant_data = serialize_variant(variant, is_admin=is_admin, include_images=True)

    product_data = serialize_product(product, is_admin=is_admin)

    product_data["variant"] = variant_data

    if variant.is_default:
        product_data["default_variant"] = variant_data
    else:
        default_variant = product.variants.filter(is_default=True).first()
        if default_variant:
            product_data["default_variant"] = serialize_variant(
                default_variant, is_admin=is_admin, include_images=True
            )
        else:
            product_data["default_variant"] = variant_data

    return {
        "wishlist_id": str(item.id),
        "added_at": item.created_at.isoformat() if item.created_at else None,
        "product": product_data,
    }


def serialize_wishlist_grouped(
    products_dict: Dict, is_admin: bool = False
) -> List[Dict]:
    """Serialize grouped wishlist products with their variants"""
    result = []

    for product_id, group_data in products_dict.items():
        product = group_data["product"]
        variants = group_data["variants"]

        product_data = serialize_product(
            product, is_admin=is_admin
        )

        product_data["variants"] = variants

        default_variant = None
        for variant in variants:
            if variant.get("is_default"):
                default_variant = variant
                break

        if not default_variant and variants:
            default_variant = variants[0]

        product_data["default_variant"] = default_variant
        product_data["variant"] = default_variant

        result.append(product_data)

    return result


# ==================== INPUT VALIDATORS ====================


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
    sku = data.get("sku", "").strip()
    if not sku:
        errors["sku"] = "This field is required"
    elif len(sku) > 100:
        errors["sku"] = "Cannot exceed 100 characters"
    else:
        cleaned["sku"] = sku

    # Price validation
    price = data.get("price")
    try:
        price = Decimal(str(price))
        if price <= 0:
            errors["price"] = "Must be positive"
        else:
            cleaned["price"] = price
    except (InvalidOperation, TypeError, ValueError):
        errors["price"] = "Valid decimal number required"

    # Attributes validation
    attributes = data.get("attributes", {})
    if not isinstance(attributes, dict):
        errors["attributes"] = "Must be an object"
    else:
        cleaned["attributes"] = attributes

    # Stock
    stock = data.get("stock", 0)
    if not isinstance(stock, int) or stock < 0:
        errors["stock"] = "Must be non-negative integer"
    else:
        cleaned["stock"] = stock

    # Admin-only fields
    if is_admin:
        discount_amount = data.get("discount_amount", 0)
        try:
            discount_amount = Decimal(str(discount_amount))
            if discount_amount < 0:
                errors["discount_amount"] = "Cannot be negative"
            elif discount_amount > cleaned.get("price", 0):
                errors["discount_amount"] = "Cannot exceed price"
            else:
                cleaned["discount_amount"] = discount_amount
        except (InvalidOperation, TypeError, ValueError):
            errors["discount_amount"] = "Valid decimal number required"

        cleaned["is_default"] = bool(data.get("is_default", False))
        cleaned["is_active"] = bool(data.get("is_active", True))
        cleaned["low_stock_threshold"] = int(data.get("low_stock_threshold", 5))

        for dim in ["weight", "height", "width", "depth"]:
            if dim in data and data[dim]:
                try:
                    cleaned[dim] = Decimal(str(data[dim]))
                except (InvalidOperation, TypeError, ValueError):
                    errors[dim] = "Valid decimal number required"
    else:
        cleaned["discount_amount"] = Decimal(0)
        cleaned["is_default"] = False
        cleaned["is_active"] = True
        cleaned["low_stock_threshold"] = 5

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