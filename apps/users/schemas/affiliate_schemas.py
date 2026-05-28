"""
Affiliate Schemas - Serialization and validation for affiliates
"""

from typing import Dict, Any, List, Optional
from apps.users.models.affiliate import Affiliate
from apps.users.schemas.address_schemas import serialize_address, serialize_addresses


def serialize_affiliate_user(
    affiliate: Affiliate, is_admin: bool = False, include_addresses: bool = False
) -> Dict[str, Any]:
    """Serialize an affiliate user"""

    user = affiliate.user

    data = {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "full_name": user.full_name,
        "phone": user.phone or "",
        "role": user.role,
        "is_active": user.is_active,
        "email_verified": user.email_verified,
        "is_affiliate": True,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }

    # Add addresses if requested
    if include_addresses and hasattr(user, "addresses"):
        addresses = list(user.addresses.all()) if hasattr(user, "addresses") else []
        data["addresses"] = serialize_addresses(addresses, is_admin)
        default_address = addresses.filter(is_default=True).first() if addresses else None
        if default_address:
            data["default_address"] = serialize_address(default_address, is_admin)

    # Add affiliate details
    data["affiliate"] = {
        "id": str(affiliate.id),
        "referral_code": affiliate.referral_code,
        "total_earnings": float(affiliate.total_earnings),
        "pending_earnings": float(affiliate.pending_earnings),
        "paid_earnings": float(affiliate.paid_earnings),
        "total_referrals": affiliate.total_referrals,
        "active_referrals": affiliate.active_referrals,
        "level": affiliate.level,
        "display_level": affiliate.display_level,
        "commission_rate": float(affiliate.commission_rate),
        "is_active": affiliate.is_active,
        "is_approved": affiliate.is_approved,
        "joined_at": affiliate.joined_at.isoformat() if affiliate.joined_at else None,
        "last_payout_at": affiliate.last_payout_at.isoformat() if affiliate.last_payout_at else None,
    }

    # Admin-only fields
    if is_admin:
        data.update({
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        })

    return data


def serialize_affiliate_list(
    affiliates: List[Affiliate], is_admin: bool = False, include_addresses: bool = False
) -> List[Dict]:
    """Serialize list of affiliate users"""
    return [serialize_affiliate_user(affiliate, is_admin, include_addresses) for affiliate in affiliates]