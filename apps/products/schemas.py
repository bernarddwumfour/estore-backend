# apps/products/schemas.py
"""
Serialization and validation - converts models to dicts and validates input
Admin-aware serialization (some fields only visible to staff)
"""
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Tuple, Optional, List


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

def serialize_category(category, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize category - hide hidden field from customers"""
    if not category:
        return None
    
    # Base fields (visible to everyone for non-hidden categories)
    data = {
        "id": str(category.id),
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "parent_id": str(category.parent.id) if category.parent else None,
        "parent_name": category.parent.name if category.parent else None,
        "image": category.image.url if category.image else None,
        "full_path": category.full_path,
    }
    
    # Admin-only fields
    if is_admin:
        data.update({
            "is_active": category.is_active,    
            "meta_title": category.meta_title,
            "meta_description": category.meta_description,
            "is_hidden": category.is_hidden,  
            "created_at": category.created_at.isoformat(),
            "updated_at": category.updated_at.isoformat(),
        })
    
    return data

def validate_bulk_action(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate bulk action request"""
    errors = {}
    cleaned = {}
    
    # Validate action
    action = data.get('action')
    valid_actions = ['activate', 'deactivate', 'hide', 'unhide', 'delete']
    
    if not action:
        errors['action'] = "This field is required"
    elif action not in valid_actions:
        errors['action'] = f"Invalid action. Must be one of: {', '.join(valid_actions)}"
    else:
        cleaned['action'] = action
    
    # Validate category_ids
    category_ids = data.get('category_ids', [])
    if not category_ids:
        errors['category_ids'] = "At least one category ID is required"
    elif not isinstance(category_ids, list):
        errors['category_ids'] = "Must be a list of category IDs"
    else:
        cleaned['category_ids'] = category_ids
    
    if errors:
        return None, errors
    
    return cleaned, None


def serialize_bulk_action_result(results: Dict) -> Dict:
    """Serialize bulk action result for API response"""
    return {
        "success": [
            {"id": item['id'], "name": item['name']}
            for item in results['success']
        ],
        "failed": [
            {"id": item['id'], "name": item['name'], "reason": item['reason']}
            for item in results['failed']
        ],
        "total": results['total'],
        "success_count": len(results['success']),
        "failed_count": len(results['failed'])
    }


def serialize_category_list(categories, is_admin: bool = False) -> List[Dict]:
    """Serialize list of categories"""
    return [serialize_category(cat, is_admin) for cat in categories]

def serialize_variant_image(image, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize variant image"""
    if not image:
        return None
    
    data = {
        "id": str(image.id),
        "url": image.image.url,
        "alt_text": image.alt_text,
        "type": image.image_type,
        "order": image.order,
    }
    
    if is_admin:
        data["is_active"] = image.is_active
        data["created_at"] = image.created_at.isoformat()
    
    return data


def serialize_variant(variant, is_admin: bool = False, include_images: bool = True) -> Dict[str, Any]:
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
        data.update({
            "is_active": variant.is_active,
            "is_low_stock": variant.is_low_stock,
            "low_stock_threshold": variant.low_stock_threshold,
            "dimensions": {
                "weight": float(variant.weight) if variant.weight else None,
                "height": float(variant.height) if variant.height else None,
                "width": float(variant.width) if variant.width else None,
                "depth": float(variant.depth) if variant.depth else None,
            },
            "created_at": variant.created_at.isoformat(),
            "updated_at": variant.updated_at.isoformat(),
        })
    else:
        # Public-facing stock info
        data["stock_status"] = _get_stock_status(variant)
    
    if include_images:
        data["images"] = [serialize_variant_image(img, is_admin) for img in variant.images.filter(is_active=True).order_by("order")]
    
    return data


def serialize_product(product, is_admin: bool = False, include_variants: bool = True) -> Dict[str, Any]:
    """Serialize product - admin fields only for staff"""
    if not product:
        return None
    
    # Base fields (visible to everyone)
    data = {
        "id": str(product.id),
        "title": product.title,
        "slug": product.slug,
        "description": product.description,
        "short_description": product.description[:200] + "..." if len(product.description) > 200 else product.description,
        "category": serialize_category(product.category, is_admin) if product.category else None,
        "features": product.features,
        "options": product.options,
        "average_rating": float(product.average_rating),
        "total_reviews": product.total_reviews,
        "min_price": float(product.min_price),
        "max_price": float(product.max_price),
        "has_stock": product.has_stock,
        "is_featured": product.is_featured,
        "is_bestseller": product.is_bestseller,
        "is_new": product.is_new,
        "default_variant": serialize_variant(product.default_variant, is_admin, include_images=True) if product.default_variant else None,
        "created_at": product.created_at.isoformat(),
        "total_stock": product.total_stock,
        "meta_title": product.meta_title,
        "meta_description": product.meta_description,
    }
    
    # Admin-only fields
    if is_admin:
        data.update({
            "status": product.status,
            "updated_at": product.updated_at.isoformat(),
            "published_at": product.published_at.isoformat() if product.published_at else None,
        })
    
    if include_variants:
        data["variants"] = [serialize_variant(v, is_admin, include_images=True) for v in product.variants.filter(is_active=True)]
    
    return data


def serialize_product_list(products, is_admin: bool = False) -> List[Dict]:
    """Serialize list of products (lighter version)"""
    return [serialize_product(p, is_admin, include_variants=False) for p in products]

def validate_product_bulk_action(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate product bulk action request"""
    errors = {}
    cleaned = {}
    
    # Validate action
    action = data.get('action')
    valid_actions = [
        'publish', 'draft', 'archive',  # Status actions
        'feature', 'unfeature',          # Featured flag
        'bestseller', 'unbestseller',    # Bestseller flag
        'new', 'unnew',                  # New flag
        'delete'                         # Delete action
    ]
    
    if not action:
        errors['action'] = "This field is required"
    elif action not in valid_actions:
        errors['action'] = f"Invalid action. Must be one of: {', '.join(valid_actions)}"
    else:
        cleaned['action'] = action
    
    # Validate product_ids
    product_ids = data.get('product_ids', [])
    if not product_ids:
        errors['product_ids'] = "At least one product ID is required"
    elif not isinstance(product_ids, list):
        errors['product_ids'] = "Must be a list of product IDs"
    else:
        cleaned['product_ids'] = product_ids
    
    if errors:
        return None, errors
    
    return cleaned, None


def serialize_product_bulk_action_result(results: Dict) -> Dict:
    """Serialize product bulk action result for API response"""
    return {
        "success": [
            {"id": item['id'], "name": item['name']}
            for item in results['success']
        ],
        "failed": [
            {"id": item['id'], "name": item['name'], "reason": item['reason']}
            for item in results['failed']
        ],
        "total": results['total'],
        "success_count": len(results['success']),
        "failed_count": len(results['failed'])
    }


def serialize_review(review, is_admin: bool = False, include_user: bool = True) -> Dict[str, Any]:
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
        "created_at": review.created_at.isoformat(),
    }
    
    # Admin-only fields
    if is_admin:
        data.update({
            "is_edited": review.is_edited,
            "is_approved": review.is_approved,
            "updated_at": review.updated_at.isoformat(),
            "user_id": str(review.user.id) if review.user else None,
            "user_email": review.user.email if review.user else None,
        })
    
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

def serialize_wishlist_product(product, variants: List[Dict], is_admin: bool = False) -> Dict[str, Any]:
    """Serialize product with specific variants from wishlist"""
    if not product:
        return None
    
    # Get base product data (without variants)
    base_product = serialize_product(product, is_admin=is_admin, include_variants=False)
    
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
    
    product_data = serialize_product(product, is_admin=is_admin, include_variants=False)
    
    product_data["variant"] = variant_data
    
    if variant.is_default:
        product_data["default_variant"] = variant_data
    else:
        default_variant = product.variants.filter(is_default=True).first()
        if default_variant:
            product_data["default_variant"] = serialize_variant(default_variant, is_admin=is_admin, include_images=True)
        else:
            product_data["default_variant"] = variant_data
    
    return {
        "wishlist_id": str(item.id),
        "added_at": item.created_at.isoformat(),
        "product": product_data,
    }


def serialize_wishlist_grouped(products_dict: Dict, is_admin: bool = False) -> List[Dict]:
    """Serialize grouped wishlist products with their variants"""
    result = []
    
    for product_id, group_data in products_dict.items():
        product = group_data["product"]
        variants = group_data["variants"]
        
        product_data = serialize_product(product, is_admin=is_admin, include_variants=False)
        
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

def validate_product_create(data: Dict[str, Any], is_admin: bool = False) -> Tuple[Optional[Dict], Optional[Dict]]:
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


def validate_product_update(data: Dict[str, Any], is_admin: bool = False) -> Tuple[Optional[Dict], Optional[Dict]]:
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
        
        for field in ["is_featured", "is_bestseller", "is_new", "meta_title", "meta_description"]:
            if field in data:
                cleaned[field] = data[field]
    
    if errors:
        return None, errors
    
    return cleaned, None


def validate_variant_create(data: Dict[str, Any], is_admin: bool = False) -> Tuple[Optional[Dict], Optional[Dict]]:
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


def validate_review_create(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
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