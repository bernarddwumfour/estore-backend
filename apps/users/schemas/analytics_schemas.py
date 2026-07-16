"""
User Analytics Schemas - Serialization for user analytics
"""

from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from decimal import Decimal

from apps.common.schemas.analytics_schemas import (
    validate_date_range,
    validate_interval,
    validate_limit,
)


# ==================== HELPER FUNCTIONS ====================

def format_decimal(value: Decimal, default: float = 0.0) -> float:
    """Format decimal to float for JSON response"""
    if value is None:
        return default
    return float(value)


# ==================== USER OVERVIEW SERIALIZER ====================

def serialize_user_overview_stats(stats: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize user overview statistics"""
    return {
        "summary": {
            "total_users": stats["summary"]["total_users"],
            "active_users": stats["summary"]["active_users"],
            "inactive_users": stats["summary"]["inactive_users"],
            "verified_emails": stats["summary"]["verified_emails"],
            "unverified_emails": stats["summary"]["unverified_emails"],
            "verified_percentage": stats["summary"]["verified_percentage"],
        },
        "role_distribution": {
            "customers": stats["role_distribution"]["customers"],
            "staff": stats["role_distribution"]["staff"],
            "admins": stats["role_distribution"]["admins"],
            "guests": stats["role_distribution"]["guests"],
            "registered": stats["role_distribution"]["registered"],
            "customer_percentage": stats["role_distribution"]["customer_percentage"],
            "staff_percentage": stats["role_distribution"]["staff_percentage"],
            "guest_percentage": stats["role_distribution"]["guest_percentage"],
        },
        "growth": {
            "new_users_30d": stats["growth"]["new_users_30d"],
            "new_users_7d": stats["growth"]["new_users_7d"],
            "active_today": stats["growth"]["active_today"],
        }
    }


# ==================== USER GROWTH TRENDS SERIALIZER ====================

def serialize_user_growth_trends(trends: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize user growth trends"""
    return [
        {
            "period": t["period"],
            "new_users": t["new_users"],
            "active_users": t["active_users"],
            "verified_users": t["verified_users"],
        }
        for t in trends
    ]


# ==================== USER ENGAGEMENT SERIALIZER ====================

def serialize_user_engagement_analytics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize user engagement analytics"""
    return {
        "customer_engagement": {
            "total_customers": data["customer_engagement"]["total_customers"],
            "active_customers": data["customer_engagement"]["active_customers"],
            "inactive_customers": data["customer_engagement"]["inactive_customers"],
            "active_percentage": data["customer_engagement"]["active_percentage"],
            "repeat_customers": data["customer_engagement"]["repeat_customers"],
            "repeat_purchase_rate": data["customer_engagement"]["repeat_purchase_rate"],
        },
        "customer_lifetime_value": {
            "average_clv": data["customer_lifetime_value"]["average_clv"],
            "average_orders_per_customer": data["customer_lifetime_value"]["average_orders_per_customer"],
        },
        "guest_conversion": {
            "total_guests": data["guest_conversion"]["total_guests"],
            "converted_guests": data["guest_conversion"]["converted_guests"],
            "conversion_rate": data["guest_conversion"]["conversion_rate"],
        }
    }


# ==================== GEOGRAPHIC DISTRIBUTION SERIALIZER ====================

def serialize_geographic_distribution(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize geographic distribution"""
    total_users = sum(c["user_count"] for c in data["by_country"])
    
    return {
        "by_country": [
            {
                "country": c["country"],
                "user_count": c["user_count"],
                "percentage": round(c["user_count"] / total_users * 100, 2) if total_users > 0 else 0,
            }
            for c in data["by_country"]
        ],
        "by_city": data["by_city"]
    }


# ==================== USER ACTIVITY SERIALIZER ====================

def serialize_user_activity_analytics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize user activity analytics"""
    return {
        "login_activity": {
            "average_days_since_last_login": data["login_activity"]["average_days_since_last_login"],
            "recently_active_7d": data["login_activity"]["recently_active_7d"],
            "never_logged_in": data["login_activity"]["never_logged_in"],
            "login_percentage": data["login_activity"]["login_percentage"],
        },
        "registration_timing": {
            "by_hour": data["registration_timing"]["by_hour"],
            "by_day_of_week": data["registration_timing"]["by_day_of_week"],
        }
    }


# ==================== AFFILIATE ANALYTICS SERIALIZER ====================

def serialize_affiliate_analytics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize affiliate analytics"""
    return {
        "summary": {
            "total_affiliates": data["summary"]["total_affiliates"],
            "approved_affiliates": data["summary"]["approved_affiliates"],
            "pending_affiliates": data["summary"]["pending_affiliates"],
            "approval_rate": data["summary"]["approval_rate"],
        },
        "level_distribution": data["level_distribution"],
        "earnings_summary": {
            "total_earnings": data["earnings_summary"]["total_earnings"],
            "total_pending": data["earnings_summary"]["total_pending"],
            "total_paid": data["earnings_summary"]["total_paid"],
            "total_referrals": data["earnings_summary"]["total_referrals"],
            "average_earnings_per_affiliate": data["earnings_summary"]["average_earnings_per_affiliate"],
        },
        "top_affiliates": [
            {
                "affiliate_id": a["affiliate_id"],
                "email": a["email"],
                "name": a["name"],
                "level": a["level"],
                "total_earnings": a["total_earnings"],
                "total_referrals": a["total_referrals"],
                "commission_rate": a["commission_rate"],
            }
            for a in data["top_affiliates"]
        ]
    }


# ==================== AFFILIATE GROWTH TRENDS SERIALIZER ====================

def serialize_affiliate_growth_trends(trends: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize affiliate growth trends"""
    return [
        {
            "period": t["period"],
            "new_affiliates": t["new_affiliates"],
            "total_earnings": t["total_earnings"],
            "total_referrals": t["total_referrals"],
        }
        for t in trends
    ]


# ==================== CUSTOMER DEMOGRAPHICS SERIALIZER ====================

def serialize_customer_demographics(data: Dict[str, Any]) -> Dict[str, Any]:
    """Serialize customer demographics"""
    total = sum(ag["count"] for ag in data["age_distribution"])
    
    return {
        "age_distribution": [
            {
                "group": ag["group"],
                "count": ag["count"],
                "percentage": round(ag["count"] / total * 100, 2) if total > 0 else 0,
            }
            for ag in data["age_distribution"]
        ],
        "marketing_preferences": data["marketing_preferences"],
        "loyalty_program": data["loyalty_program"],
    }


# ==================== TOP CUSTOMERS SERIALIZER ====================

def serialize_top_customers(customers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Serialize top customers"""
    return [
        {
            "user_id": c["user_id"],
            "email": c["email"],
            "name": c["name"],
            "total_spent": c["total_spent"],
            "order_count": c["order_count"],
            "average_order_value": c["average_order_value"],
            "first_order": c["first_order"],
            "last_order": c["last_order"],
        }
        for c in customers
    ]