"""
Affiliate Schemas - Serialization and validation for affiliates
"""

from typing import Dict, Any, List, Optional
from apps.users.models.affiliate import Affiliate
from apps.users.schemas.address_schemas import serialize_address, serialize_addresses
from apps.promotions.models import DiscountCode


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
        "is_active": affiliate.is_active,
        "user_is_active": user.is_active,
        "email_verified": user.email_verified,
        "is_affiliate": True,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }

    discount_code = getattr(affiliate, "discount_codes", None)
    primary_discount_code = None
    if discount_code is not None:
        primary_discount_code = discount_code.order_by("created_at").first()
    if primary_discount_code is None:
        primary_discount_code = DiscountCode.objects.filter(affiliate=affiliate).order_by("created_at").first()

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
        "discount_code": primary_discount_code.code if primary_discount_code else None,
        "total_earnings": float(affiliate.total_earnings),
        "pending_earnings": float(affiliate.pending_earnings),
        "paid_earnings": float(affiliate.paid_earnings),
        "total_referrals": affiliate.total_referrals,
        "active_referrals": affiliate.active_referrals,
        "level": affiliate.level,
        "display_level": affiliate.display_level,
        "commission_rate": float(affiliate.commission_rate),
        "commission_basis": affiliate.commission_basis,
        "commission_basis_display": affiliate.get_commission_basis_display(),
        "is_active": affiliate.is_active,
        "is_approved": affiliate.is_approved,
        "joined_at": affiliate.joined_at.isoformat() if affiliate.joined_at else None,
        "last_payout_at": affiliate.last_payout_at.isoformat() if affiliate.last_payout_at else None,
        "attributed_orders_count": int(getattr(affiliate, "attributed_orders_count", 0) or 0),
        "attributed_sales_total": float(getattr(affiliate, "attributed_sales_total", 0) or 0),
        "pending_commissions_count": int(getattr(affiliate, "pending_commissions_count", 0) or 0),
        "accrued_commissions_count": int(getattr(affiliate, "accrued_commissions_count", 0) or 0),
        "reversed_commissions_count": int(getattr(affiliate, "reversed_commissions_count", 0) or 0),
    }

    data.update({
        "referral_code": data["affiliate"]["referral_code"],
        "discount_code": data["affiliate"]["discount_code"],
        "total_earnings": data["affiliate"]["total_earnings"],
        "pending_earnings": data["affiliate"]["pending_earnings"],
        "paid_earnings": data["affiliate"]["paid_earnings"],
        "total_referrals": data["affiliate"]["total_referrals"],
        "active_referrals": data["affiliate"]["active_referrals"],
        "affiliate_level": data["affiliate"]["level"],
        "commission_rate": data["affiliate"]["commission_rate"],
        "commission_basis": data["affiliate"]["commission_basis"],
        "joined_affiliate_at": data["affiliate"]["joined_at"],
        "last_payout_at": data["affiliate"]["last_payout_at"],
        "attributed_orders_count": data["affiliate"]["attributed_orders_count"],
        "attributed_sales_total": data["affiliate"]["attributed_sales_total"],
        "pending_commissions_count": data["affiliate"]["pending_commissions_count"],
        "accrued_commissions_count": data["affiliate"]["accrued_commissions_count"],
        "reversed_commissions_count": data["affiliate"]["reversed_commissions_count"],
    })

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
