"""
Promotion Schemas - Serialization and validation
"""

from typing import Dict, Any, Optional, List, Tuple
from decimal import Decimal
from datetime import datetime
from .models import PromotionItem,Promotion

def validate_promotion_create(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate promotion creation data"""
    errors = {}
    cleaned = {}
    
    # Required fields
    name = data.get("name", "").strip()
    if not name:
        errors["name"] = "This field is required"
    elif len(name) > 200:
        errors["name"] = "Cannot exceed 200 characters"
    else:
        cleaned["name"] = name
    
    # Bundle price
    bundle_price = data.get("bundle_price")
    try:
        bundle_price = Decimal(str(bundle_price))
        if bundle_price < 0:
            errors["bundle_price"] = "Must be positive"
        else:
            cleaned["bundle_price"] = bundle_price
    except (TypeError, ValueError):
        errors["bundle_price"] = "Valid decimal number required"
    
    # Start date
    starts_at = data.get("starts_at")
    if not starts_at:
        errors["starts_at"] = "This field is required"
    else:
        try:
            if isinstance(starts_at, str):
                starts_at = datetime.fromisoformat(starts_at.replace('Z', '+00:00'))
            cleaned["starts_at"] = starts_at
        except ValueError:
            errors["starts_at"] = "Invalid date format"
    
    # End date (optional)
    ends_at = data.get("ends_at")
    if ends_at:
        try:
            if isinstance(ends_at, str):
                ends_at = datetime.fromisoformat(ends_at.replace('Z', '+00:00'))
            cleaned["ends_at"] = ends_at
        except ValueError:
            errors["ends_at"] = "Invalid date format"
    
    # Items validation
    items = data.get("items", [])
    if not items:
        errors["items"] = "At least one item is required"
    elif not isinstance(items, list):
        errors["items"] = "Must be a list"
    else:
        cleaned_items = []
        for idx, item in enumerate(items):
            item_errors = {}
            
            variant_id = item.get("variant_id")
            if not variant_id:
                item_errors["variant_id"] = "Variant ID required"
            
            quantity = item.get("quantity", 1)
            try:
                quantity = int(quantity)
                if quantity < 1:
                    item_errors["quantity"] = "Must be at least 1"
            except (TypeError, ValueError):
                item_errors["quantity"] = "Must be an integer"
            
            if item_errors:
                errors[f"items[{idx}]"] = item_errors
            else:
                cleaned_items.append({
                    "variant_id": variant_id,
                    "quantity": quantity,
                    "is_free": item.get("is_free", False),
                })
        
        cleaned["items"] = cleaned_items
    
    # Optional fields
    cleaned["description"] = data.get("description", "")
    cleaned["meta_title"] = data.get("meta_title", "")[:200]
    cleaned["meta_description"] = data.get("meta_description", "")[:500]
    
    if errors:
        return None, errors
    
    return cleaned, None


def serialize_promotion_item(
    item: 'PromotionItem',
    is_admin: bool = False
) -> Dict[str, Any]:
    """Serialize a single promotion item"""
    variant = item.variant
    
    data = {
        "variant_id": str(variant.id),
        "sku": variant.sku,
        "product_title": variant.product.title,
        "product_slug": variant.product.slug,
        "quantity": item.quantity,
        "original_price": float(item.original_price),
        "is_free": item.is_free,
        "attributes": variant.attributes,
    }
    
    # Add first image if available
    first_image = variant.images.filter(is_active=True).order_by('order').first()
    if first_image:
        data["image"] = first_image.image.url
    
    # Admin-only fields
    if is_admin:
        data.update({
            "is_available": item.is_available,
            "current_stock": variant.stock,
            "current_price": float(variant.price),
            "cost_price_snapshot": float(item.cost_price_snapshot),
            "item_gross_profit": round(item.item_gross_profit, 2),
            "item_margin_percentage": round(item.item_margin_percentage, 2),
            "has_sufficient_stock": item.has_sufficient_stock,
        })
    
    return data


def serialize_promotion(
    promotion: 'Promotion',
    is_admin: bool = False
) -> Dict[str, Any]:
    """Serialize a promotion"""
    items = promotion.items.all()
    
    # Split into paid items and free items
    paid_items = [serialize_promotion_item(item, is_admin) for item in items if not item.is_free]
    free_items = [serialize_promotion_item(item, is_admin) for item in items if item.is_free]
    
    # Get images
    images = [
        {
            "id": str(img.id),
            "url": img.image.url,
            "type": img.image_type,
            "alt_text": img.alt_text,
        }
        for img in promotion.images.filter(is_active=True).order_by('order')
    ]
    
    # Convert Decimal to float for calculations
    bundle_price_float = float(promotion.bundle_price)
    original_total_float = float(promotion.original_total)
    savings_amount_float = float(promotion.savings_amount)
    
    # Calculate savings percentage safely
    if original_total_float > 0:
        savings_percentage = round((savings_amount_float / original_total_float * 100), 1)
    else:
        savings_percentage = 0
    
    data = {
        "id": str(promotion.id),
        "name": promotion.name,
        "slug": promotion.slug,
        "description": promotion.description,
        "bundle_price": round(bundle_price_float, 2),
        "original_total": round(original_total_float, 2),
        "savings_amount": round(savings_amount_float, 2),
        "savings_percentage": savings_percentage,
        "starts_at": promotion.starts_at.isoformat() if promotion.starts_at else None,
        "ends_at": promotion.ends_at.isoformat() if promotion.ends_at else None,
        "items": paid_items,
        "free_items": free_items,
        "images": images,
        "has_stock": promotion.has_stock,
    }
    
    # Admin-only fields
    if is_admin:
        # Calculate financial metrics with proper Decimal handling
        total_cost = sum(float(item.cost_price_snapshot * item.quantity) for item in items)
        bundle_gross_profit = float(promotion.savings_amount) - total_cost
        
        if bundle_price_float > 0:
            bundle_margin_percentage = round((bundle_gross_profit / bundle_price_float * 100), 2)
        else:
            bundle_margin_percentage = 0
        
        data.update({
            "status": promotion.status,
            "created_at": promotion.created_at.isoformat() if promotion.created_at else None,
            "updated_at": promotion.updated_at.isoformat() if promotion.updated_at else None,
            "created_by": {
                "id": str(promotion.created_by.id) if promotion.created_by else None,
                "email": promotion.created_by.email if promotion.created_by else None,
            } if promotion.created_by else None,
            "unavailable_items": promotion.unavailable_items,
            "bundle_cost": round(total_cost, 2),
            "bundle_gross_profit": round(bundle_gross_profit, 2),
            "bundle_margin_percentage": bundle_margin_percentage,
        })
    
    return data

def serialize_promotion_list(
    promotions: List['Promotion'],
    is_admin: bool = False
) -> List[Dict]:
    """Serialize a list of promotions"""
    return [serialize_promotion(p, is_admin) for p in promotions]



def validate_bulk_action(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate bulk action request"""
    errors = {}
    cleaned = {}
    
    # Validate action
    action = data.get("action")
    valid_actions = ["activate", "pause", "delete"]
    
    if not action:
        errors["action"] = "This field is required"
    elif action not in valid_actions:
        errors["action"] = f"Invalid action. Must be one of: {', '.join(valid_actions)}"
    else:
        cleaned["action"] = action
    
    # Validate promotion_ids
    promotion_ids = data.get("promotion_ids", [])
    if not promotion_ids:
        errors["promotion_ids"] = "At least one promotion ID is required"
    elif not isinstance(promotion_ids, list):
        errors["promotion_ids"] = "Must be a list of promotion IDs"
    else:
        cleaned["promotion_ids"] = promotion_ids
    
    if errors:
        return None, errors
    
    return cleaned, None


def serialize_bulk_action_result(results: Dict) -> Dict:
    """Serialize bulk action result for API response"""
    return {
        "success": [
            {"id": item["id"], "name": item["name"]} 
            for item in results["success"]
        ],
        "failed": [
            {"id": item["id"], "name": item["name"], "reason": item["reason"]} 
            for item in results["failed"]
        ],
        "total": results["total"],
        "success_count": len(results["success"]),
        "failed_count": len(results["failed"]),
    }