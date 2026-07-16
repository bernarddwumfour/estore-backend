"""
Product Analytics Schemas - Serialization and validation
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal

from apps.common.schemas.analytics_schemas import validate_date_range, validate_limit


# ==================== HELPER FUNCTIONS ====================

def format_decimal(value: Decimal, default: float = 0.0) -> float:
    """Format decimal to float for JSON response"""
    if value is None:
        return default
    return float(value)


# ==================== OVERVIEW SCHEMAS ====================

def serialize_overview_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize overview statistics"""
    return {
        "summary": {
            "total_products": stats["summary"]["total_products"],
            "total_variants": stats["summary"]["total_variants"],
            "active_products": stats["summary"]["active_products"],
            "draft_products": stats["summary"]["draft_products"],
            "archived_products": stats["summary"]["archived_products"],
            "total_categories": stats["summary"]["total_categories"],
            "total_brands": stats["summary"]["total_brands"],
        },
        "inventory_summary": {
            "total_stock": stats["inventory_summary"]["total_stock"],
            "out_of_stock_variants": stats["inventory_summary"]["out_of_stock_variants"],
            "low_stock_variants": stats["inventory_summary"]["low_stock_variants"],
            "total_inventory_value": format_decimal(stats["inventory_summary"]["total_inventory_value"]),
        },
        "engagement": {
            "total_reviews": stats["engagement"]["total_reviews"],
            "average_rating": stats["engagement"]["average_rating"],
            "total_wishlists": stats["engagement"]["total_wishlists"],
            "products_with_reviews": stats["engagement"]["products_with_reviews"],
        },
        "recent_activity": {
            "products_added_30d": stats["recent_activity"]["products_added_30d"],
            "products_updated_30d": stats["recent_activity"]["products_updated_30d"],
            "variants_added_30d": stats["recent_activity"]["variants_added_30d"],
        }
    }


# ==================== SALES PERFORMANCE SCHEMAS ====================

def serialize_sales_performance(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize sales performance data"""
    return {
        "sales_summary": {
            "total_revenue": data["sales_summary"]["total_revenue"],
            "total_quantity_sold": data["sales_summary"]["total_quantity_sold"],
            "total_orders": data["sales_summary"]["total_orders"],
            "average_order_value": data["sales_summary"]["average_order_value"],
            "average_unit_price": data["sales_summary"]["average_unit_price"],
            "items_per_order": data["sales_summary"]["items_per_order"],
        },
        "top_products": [
            {
                "product_id": p["product_id"],
                "title": p["title"],
                "quantity_sold": p["quantity_sold"],
                "revenue": p["revenue"],
                "orders": p["orders"],
            }
            for p in data["top_products"]
        ],
        "products_without_sales": data["products_without_sales"],
        "revenue_trends": [
            {
                "date": t["date"],
                "revenue": t["revenue"],
                "orders": t["orders"],
            }
            for t in data["revenue_trends"]
        ],
    }


# ==================== PRODUCT FUNNEL SCHEMAS ====================

def serialize_product_funnel(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize product funnel data"""
    return {
        "total_products": data["total_products"],
        "products_with_views": data["products_with_views"],
        "products_with_wishlists": data["products_with_wishlists"],
        "products_with_carts": data["products_with_carts"],
        "products_with_purchases": data["products_with_purchases"],
        "conversion_rates": {
            "view_to_wishlist": data["conversion_rates"]["view_to_wishlist"],
            "wishlist_to_cart": data["conversion_rates"]["wishlist_to_cart"],
            "cart_to_purchase": data["conversion_rates"]["cart_to_purchase"],
            "overall_conversion": data["conversion_rates"]["overall_conversion"],
        }
    }


# ==================== INVENTORY HEALTH SCHEMAS ====================

def serialize_inventory_health(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize inventory health data"""
    return {
        "summary": {
            "total_variants_analyzed": data["summary"]["total_variants_analyzed"],
            "average_turnover_rate": data["summary"]["average_turnover_rate"],
            "slow_movers_count": data["summary"]["slow_movers_count"],
            "fast_movers_count": data["summary"]["fast_movers_count"],
        },
        "slow_movers": [
            {
                "variant_id": m["variant_id"],
                "sku": m["sku"],
                "product_title": m["product_title"],
                "current_stock": m["current_stock"],
                "days_of_stock": m["days_of_stock"],
                "turnover_rate": m["turnover_rate"],
            }
            for m in data["slow_movers"]
        ],
        "fast_movers": [
            {
                "variant_id": m["variant_id"],
                "sku": m["sku"],
                "product_title": m["product_title"],
                "current_stock": m["current_stock"],
                "days_of_stock": m["days_of_stock"],
                "turnover_rate": m["turnover_rate"],
            }
            for m in data["fast_movers"]
        ],
        "reorder_recommendations": [
            {
                "variant_id": r["variant_id"],
                "sku": r["sku"],
                "product_title": r["product_title"],
                "current_stock": r["current_stock"],
                "days_until_out": r["days_until_out"],
                "reorder_quantity": r["reorder_quantity"],
                "priority": r["priority"],
            }
            for r in data["reorder_recommendations"]
        ],
    }


# ==================== PRICING ANALYTICS SCHEMAS ====================

def serialize_pricing_analytics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize pricing analytics data"""
    return {
        "distribution": [
            {
                "range": r["range"],
                "variant_count": r["variant_count"],
                "product_count": r["product_count"],
                "percentage": r["percentage"],
            }
            for r in data["distribution"]
        ],
        "statistics": {
            "min_price": data["statistics"]["min_price"],
            "max_price": data["statistics"]["max_price"],
            "avg_price": data["statistics"]["avg_price"],
            "median_price": data["statistics"]["median_price"],
            "total_variants": data["statistics"]["total_variants"],
        },
        "discount_analysis": {
            "total_discounted_variants": data["discount_analysis"]["total_discounted_variants"],
            "discounted_percentage": data["discount_analysis"]["discounted_percentage"],
            "average_discount_percentage": data["discount_analysis"]["average_discount_percentage"],
        },
        "price_elasticity": [
            {
                "price": p["price"],
                "estimated_demand": p["estimated_demand"],
                "estimated_revenue": p["estimated_revenue"],
            }
            for p in data["price_elasticity"]
        ],
        "optimal_price_point": {
            "price": data["optimal_price_point"]["price"],
            "estimated_revenue": data["optimal_price_point"]["estimated_revenue"],
            "estimated_demand": data["optimal_price_point"]["estimated_demand"],
        },
    }


# ==================== CATEGORY ANALYTICS SCHEMAS ====================

def serialize_category_analytics(categories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize category analytics data"""
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "slug": c["slug"],
            "metrics": {
                "total_products": c["metrics"]["total_products"],
                "total_variants": c["metrics"]["total_variants"],
                "total_quantity_sold": c["metrics"]["total_quantity_sold"],
                "total_revenue": format_decimal(c["metrics"]["total_revenue"]),
                "total_orders": c["metrics"]["total_orders"],
                "avg_product_price": format_decimal(c["metrics"]["avg_product_price"]),
            },
            "top_products": [
                {
                    "product_id": p["product_id"],
                    "title": p["title"],
                    "revenue": format_decimal(p["revenue"]),
                    "quantity": p["quantity"],
                }
                for p in c["top_products"]
            ],
        }
        for c in categories
    ]


# ==================== TOP PRODUCTS SCHEMAS ====================

def serialize_top_product(product: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize a single top product"""
    return {
        "id": product["id"],
        "title": product["title"],
        "slug": product["slug"],
        "category": product["category"],
        "category_id": product["category_id"],
        "brand": product.get("brand"),
        "thumbnail": product.get("thumbnail"),
        "metrics": {
            "total_quantity_sold": product["metrics"]["total_quantity_sold"],
            "total_revenue": format_decimal(product["metrics"]["total_revenue"]),
            "total_orders": product["metrics"]["total_orders"],
            "average_price": format_decimal(product["metrics"]["average_price"]),
            "revenue_percentage": product["metrics"]["revenue_percentage"],
        },
        "inventory": {
            "current_stock": product["inventory"]["current_stock"],
            "total_variants": product["inventory"]["total_variants"],
            "stock_status": product["inventory"]["stock_status"],
        },
        "ratings": {
            "average_rating": product["ratings"]["average_rating"],
            "total_reviews": product["ratings"]["total_reviews"],
        }
    }


def serialize_top_products_response(
    products: List[Dict[str, Any]],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Serialize top products response"""
    total_revenue = sum(p["metrics"]["total_revenue"] for p in products)
    
    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "products": [serialize_top_product(p) for p in products],
        "summary": {
            "total_products_sold": len(products),
            "total_revenue": format_decimal(total_revenue),
            "total_quantity_sold": sum(p["metrics"]["total_quantity_sold"] for p in products),
            "top_product_revenue": format_decimal(products[0]["metrics"]["total_revenue"]) if products else 0,
            "top_product_percentage": products[0]["metrics"]["revenue_percentage"] if products else 0,
        }
    }


# ==================== VARIANT ANALYTICS SCHEMAS ====================

def serialize_variant_analytics(variant: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize variant analytics data"""
    return {
        "id": variant["id"],
        "sku": variant["sku"],
        "product_title": variant["product_title"],
        "product_id": variant["product_id"],
        "attributes": variant["attributes"],
        "metrics": {
            "quantity_sold": variant["metrics"]["quantity_sold"],
            "revenue": format_decimal(variant["metrics"]["revenue"]),
            "orders_count": variant["metrics"]["orders_count"],
            "conversion_rate": variant["metrics"]["conversion_rate"],
            "return_rate": variant["metrics"]["return_rate"],
            "average_days_to_sell": variant["metrics"]["average_days_to_sell"],
        },
        "pricing": {
            "price": format_decimal(variant["pricing"]["price"]),
            "discounted_price": format_decimal(variant["pricing"]["discounted_price"]),
            "discount_percentage": variant["pricing"]["discount_percentage"],
            "competitor_price_avg": format_decimal(variant["pricing"].get("competitor_price_avg")) if variant["pricing"].get("competitor_price_avg") else None,
            "price_position": variant["pricing"].get("price_position"),
        },
        "inventory": {
            "current_stock": variant["inventory"]["current_stock"],
            "initial_stock": variant["inventory"]["initial_stock"],
            "stock_turnover_rate": variant["inventory"]["stock_turnover_rate"],
            "days_until_out_of_stock": variant["inventory"]["days_until_out_of_stock"],
            "reorder_point": variant["inventory"]["reorder_point"],
            "stock_status": variant["inventory"]["stock_status"],
        },
        "performance": {
            "views": variant["performance"]["views"],
            "wishlist_adds": variant["performance"]["wishlist_adds"],
            "cart_adds": variant["performance"]["cart_adds"],
            "abandoned_carts": variant["performance"]["abandoned_carts"],
            "sell_through_rate": variant["performance"]["sell_through_rate"],
            "profit_margin": variant["performance"]["profit_margin"],
            "rank_in_category": variant["performance"]["rank_in_category"],
        }
    }


def serialize_variants_response(
    variants: List[Dict[str, Any]],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Serialize variants response"""
    total_revenue = sum(v["metrics"]["revenue"] for v in variants)
    total_quantity = sum(v["metrics"]["quantity_sold"] for v in variants)
    avg_conversion = sum(v["metrics"]["conversion_rate"] for v in variants) / len(variants) if variants else 0
    
    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "variants": [serialize_variant_analytics(v) for v in variants],
        "summary": {
            "total_variants": len(variants),
            "total_revenue": format_decimal(total_revenue),
            "total_quantity_sold": total_quantity,
            "avg_conversion_rate": round(avg_conversion, 2),
        }
    }


# ==================== INVENTORY STATUS SCHEMAS ====================

def serialize_inventory_status(inventory: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize inventory status response"""
    return {
        "summary": {
            "total_variants": inventory["summary"]["total_variants"],
            "total_stock": inventory["summary"]["total_stock"],
            "total_inventory_value": format_decimal(inventory["summary"]["total_inventory_value"]),
            "avg_stock_per_variant": inventory["summary"]["avg_stock_per_variant"],
        },
        "stock_status": inventory["stock_status"],
        "low_stock_alerts": [
            {
                "variant_id": alert["variant_id"],
                "sku": alert["sku"],
                "product_title": alert["product_title"],
                "attributes": alert["attributes"],
                "current_stock": alert["current_stock"],
                "threshold": alert["threshold"],
                "severity": alert["severity"],
            }
            for alert in inventory["low_stock_alerts"]
        ],
        "out_of_stock": [
            {
                "variant_id": item["variant_id"],
                "sku": item["sku"],
                "product_title": item["product_title"],
                "attributes": item["attributes"],
                "days_out_of_stock": item["days_out_of_stock"],
            }
            for item in inventory["out_of_stock"]
        ],
        "inventory_by_category": [
            {
                "category": cat["category"],
                "total_stock": cat["total_stock"],
                "total_value": format_decimal(cat["total_value"]),
                "variants_count": cat["variants_count"],
                "low_stock_count": cat["low_stock_count"],
                "out_of_stock_count": cat["out_of_stock_count"],
            }
            for cat in inventory["inventory_by_category"]
        ],
        "inventory_by_brand": [
            {
                "brand": brand["brand"],
                "total_stock": brand["total_stock"],
                "total_value": format_decimal(brand["total_value"]),
                "variants_count": brand["variants_count"],
            }
            for brand in inventory["inventory_by_brand"]
        ],
    }


# ==================== PRICE DISTRIBUTION SCHEMAS ====================

def serialize_price_distribution(price_data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize price distribution response"""
    return {
        "ranges": [
            {
                "range": r["range"],
                "min": r["min"],
                "max": r["max"],
                "variant_count": r["variant_count"],
                "product_count": r["product_count"],
                "percentage": r["percentage"],
                "total_value": format_decimal(r["total_value"]),
            }
            for r in price_data["ranges"]
        ],
        "statistics": {
            "min_price": format_decimal(price_data["statistics"]["min_price"]),
            "max_price": format_decimal(price_data["statistics"]["max_price"]),
            "avg_price": format_decimal(price_data["statistics"]["avg_price"]),
            "total_variants": price_data["statistics"]["total_variants"],
            "total_products": price_data["statistics"]["total_products"],
        }
    }


# ==================== REVIEW ANALYTICS SCHEMAS ====================

def serialize_review_analytics(review_data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize review analytics response"""
    return {
        "summary": {
            "total_reviews": review_data["summary"]["total_reviews"],
            "average_rating": review_data["summary"]["average_rating"],
            "verified_purchases": review_data["summary"]["verified_purchases"],
            "verified_percentage": review_data["summary"]["verified_percentage"],
            "products_with_reviews": review_data["summary"]["products_with_reviews"],
            "products_without_reviews": review_data["summary"]["products_without_reviews"],
        },
        "rating_distribution": {
            "5_stars": review_data["rating_distribution"].get("5_stars", 0),
            "4_stars": review_data["rating_distribution"].get("4_stars", 0),
            "3_stars": review_data["rating_distribution"].get("3_stars", 0),
            "2_stars": review_data["rating_distribution"].get("2_stars", 0),
            "1_star": review_data["rating_distribution"].get("1_star", 0),
        },
        "recent_reviews": [
            {
                "id": r["id"],
                "product_title": r["product_title"],
                "product_id": r["product_id"],
                "rating": r["rating"],
                "title": r["title"],
                "comment": r["comment"],
                "user_email": r["user_email"],
                "is_verified_purchase": r["is_verified_purchase"],
                "created_at": r["created_at"],
            }
            for r in review_data["recent_reviews"]
        ],
        "top_rated_products": [
            {
                "product_id": p["product_id"],
                "title": p["title"],
                "average_rating": p["average_rating"],
                "total_reviews": p["total_reviews"],
                "category": p["category"],
            }
            for p in review_data["top_rated_products"]
        ],
        "lowest_rated_products": [
            {
                "product_id": p["product_id"],
                "title": p["title"],
                "average_rating": p["average_rating"],
                "total_reviews": p["total_reviews"],
                "category": p["category"],
            }
            for p in review_data["lowest_rated_products"]
        ],
    }


# ==================== CATEGORY PERFORMANCE SCHEMAS (legacy) ====================

def serialize_category_performance(category: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize category performance data"""
    return {
        "id": category["id"],
        "name": category["name"],
        "slug": category["slug"],
        "metrics": {
            "total_products": category["metrics"]["total_products"],
            "total_variants": category["metrics"]["total_variants"],
            "total_quantity_sold": category["metrics"]["total_quantity_sold"],
            "total_revenue": format_decimal(category["metrics"]["total_revenue"]),
            "revenue_percentage": category["metrics"]["revenue_percentage"],
            "quantity_percentage": category["metrics"]["quantity_percentage"],
            "avg_product_price": format_decimal(category["metrics"]["avg_product_price"]),
        },
        "inventory": {
            "total_stock": category["inventory"]["total_stock"],
            "out_of_stock_products": category["inventory"]["out_of_stock_products"],
            "low_stock_products": category["inventory"]["low_stock_products"],
        },
        "engagement": {
            "average_rating": category["engagement"]["average_rating"],
            "total_reviews": category["engagement"]["total_reviews"],
        }
    }


def serialize_categories_response(
    categories: List[Dict[str, Any]],
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Serialize categories response"""
    total_revenue = sum(c["metrics"]["total_revenue"] for c in categories)
    
    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "categories": [serialize_category_performance(c) for c in categories],
        "summary": {
            "total_categories": len(categories),
            "total_revenue": format_decimal(total_revenue),
            "top_category_revenue": format_decimal(categories[0]["metrics"]["total_revenue"]) if categories else 0,
            "top_category_percentage": categories[0]["metrics"]["revenue_percentage"] if categories else 0,
        }
    }