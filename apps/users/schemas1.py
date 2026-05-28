# apps/users/schemas.py

from typing import Dict, Any, List, Optional, Tuple
from apps.users.models.user import User
from apps.users.models.address import Address
from apps.users.models.affiliate import Affiliate

def serialize_address(address: Address, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize an address"""
    if not address:
        return None
    
    try:
        data = {
            "id": str(address.id),
            "address_type": address.address_type,
            "first_name": address.first_name,
            "last_name": address.last_name,
            "company": address.company,
            "phone": address.phone,
            "email": address.email,
            "address_line1": address.address_line1,
            "address_line2": address.address_line2,
            "city": address.city,
            "state": address.state,
            "postal_code": address.postal_code,
            "country": address.country,
            "instructions": address.instructions,
            "is_default": address.is_default,
            "full_address": address.full_address,
        }

        if is_admin:
            data.update({
                "user_id": str(address.user.id) if address.user else None,
                "is_active": address.is_active,
                "created_at": address.created_at.isoformat() if address.created_at else None,
                "updated_at": address.updated_at.isoformat() if address.updated_at else None,
            })

        return data
    except Exception as e:
        print(f"Error serializing address {address.id}: {e}")
        return None


def serialize_addresses(addresses: List[Address], is_admin: bool = False) -> List[Dict[str, Any]]:
    """Serialize list of addresses"""
    return [serialize_address(address, is_admin) for address in addresses]

def serialize_user(
    user: User, is_admin: bool = False, include_addresses: bool = False
) -> Dict[str, Any]:
    """Serialize a single user for API response"""

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
        "is_guest": user.is_guest,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }

    # Add addresses if requested
    if include_addresses:
        try:
            # Check if the user has the addresses attribute (related manager)
            if hasattr(user, 'addresses'):
                # Get all active addresses for this user
                addresses_qs = user.addresses.filter(is_active=True)
                addresses = list(addresses_qs)
                
                if addresses:
                    data["addresses"] = serialize_addresses(addresses, is_admin)
                    
                    # Find default address
                    default_address = None
                    for addr in addresses:
                        if addr.is_default:
                            default_address = addr
                            break
                    if default_address:
                        data["default_address"] = serialize_address(default_address, is_admin)
                else:
                    data["addresses"] = []
                    data["default_address"] = None
            else:
                data["addresses"] = []
                data["default_address"] = None
        except Exception as e:
            # If there's any error with addresses, log it and return empty lists
            print(f"Error serializing addresses for user {user.email}: {e}")
            data["addresses"] = []
            data["default_address"] = None

    # Add affiliate info if user has affiliate profile
    try:
        if hasattr(user, 'affiliate_profile') and user.affiliate_profile:
            data["is_affiliate"] = True
            data["affiliate_profile"] = {
                "id": str(user.affiliate_profile.id),
                "referral_code": user.affiliate_profile.referral_code,
                "level": user.affiliate_profile.level,
                "total_earnings": float(user.affiliate_profile.total_earnings),
            }
        else:
            data["is_affiliate"] = False
    except Exception:
        data["is_affiliate"] = False

    # Admin-only fields
    if is_admin:
        data.update({
            "username": user.username or "",
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "email_verified_at": user.email_verified_at.isoformat() if user.email_verified_at else None,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        })

    return data


def serialize_user_list(
    users: List[User], is_admin: bool = False, include_addresses: bool = False
) -> List[Dict]:
    """Serialize list of users"""
    return [serialize_user(user, is_admin, include_addresses) for user in users]


def serialize_customer(
    user: User, is_admin: bool = False, include_addresses: bool = True
) -> Dict[str, Any]:
    """Serialize a customer user (registered, non-staff)"""
    
    # Pass include_addresses parameter down to serialize_user
    data = serialize_user(user, is_admin, include_addresses=include_addresses)

    # Add customer-specific fields
    if is_admin:
        data.update({
            "total_orders": getattr(user, 'order_count', 0),
            "total_spent": float(getattr(user, 'total_spent', 0)),
            "last_order_date": getattr(user, 'last_order_date', None),
        })

    return data


def serialize_customer_list(
    customers: List[User], is_admin: bool = False, include_addresses: bool = True
) -> List[Dict]:
    """Serialize list of customers"""
    return [serialize_customer(customer, is_admin, include_addresses) for customer in customers]


def serialize_staff_user(user: User, is_admin: bool = False) -> Dict[str, Any]:
    """Serialize a staff or admin user"""
    
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
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }
    
    if is_admin:
        data.update({
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            "is_staff": user.is_staff,
            "is_superuser": user.is_superuser,
            "permissions": getattr(user, 'permissions_list', []),
        })
    
    return data


def serialize_staff_list(staff_users: List[User], is_admin: bool = False) -> List[Dict]:
    """Serialize list of staff users"""
    return [serialize_staff_user(user, is_admin) for user in staff_users]


def serialize_guest_user(
    user: User, is_admin: bool = False, include_addresses: bool = True
) -> Dict[str, Any]:
    """Serialize a guest user"""

    data = serialize_user(user, is_admin, include_addresses)
    
    # Add guest-specific fields
    data["converted_to_registered"] = user.has_usable_password()

    return data


def serialize_guest_list(
    guests: List[User], is_admin: bool = False, include_addresses: bool = True
) -> List[Dict]:
    """Serialize list of guest users"""
    return [serialize_guest_user(guest, is_admin, include_addresses) for guest in guests]


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


def serialize_user_statistics(stats: Dict) -> Dict:
    """Serialize user statistics for dashboard"""
    return {
        "total_users": stats["total_users"],
        "total_customers": stats["total_customers"],
        "total_guests": stats["total_guests"],
        "total_staff": stats["total_staff"],
        "total_admins": stats["total_admins"],
        "total_affiliates": stats["total_affiliates"],
        "active_users": stats["active_users"],
        "inactive_users": stats["inactive_users"],
        "verified_emails": stats["verified_emails"],
        "unverified_emails": stats["unverified_emails"],
    }


def serialize_guest_checkout_data(user: User, order_data: Dict = None) -> Dict[str, Any]:
    """Serialize guest checkout response"""
    data = {
        "id": str(user.id),
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_guest": user.is_guest,
    }
    
    if order_data:
        data["order"] = order_data
    
    return data


# ==================== VALIDATION SCHEMAS ====================

def validate_user_create(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate user creation data"""
    errors = {}
    cleaned = {}
    
    required_fields = ["email", "first_name", "last_name"]
    for field in required_fields:
        if not data.get(field):
            errors[field] = f"{field.replace('_', ' ').title()} is required"
    
    if errors:
        return None, errors
    
    # Validate email
    email = data["email"].lower().strip()
    if "@" not in email or "." not in email:
        errors["email"] = "Invalid email address"
    else:
        cleaned["email"] = email
    
    cleaned["first_name"] = data["first_name"].strip()
    cleaned["last_name"] = data["last_name"].strip()
    
    if data.get("phone"):
        cleaned["phone"] = data["phone"].strip()
    
    if data.get("role"):
        valid_roles = ["customer", "staff", "admin"]
        if data["role"] not in valid_roles:
            errors["role"] = f"Role must be one of: {', '.join(valid_roles)}"
        else:
            cleaned["role"] = data["role"]
    
    if errors:
        return None, errors
    
    return cleaned, None


def validate_staff_create(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate staff user creation"""
    errors = {}
    cleaned = {}
    
    required_fields = ["email", "password", "first_name", "last_name", "role"]
    for field in required_fields:
        if not data.get(field):
            errors[field] = f"{field.replace('_', ' ').title()} is required"
    
    if errors:
        return None, errors
    
    # Validate email
    email = data["email"].lower().strip()
    if "@" not in email or "." not in email:
        errors["email"] = "Invalid email address"
    else:
        cleaned["email"] = email
    
    # Validate role
    if data["role"] not in ["staff", "admin"]:
        errors["role"] = "Role must be 'staff' or 'admin'"
    else:
        cleaned["role"] = data["role"]
    
    # Validate password
    if len(data["password"]) < 8:
        errors["password"] = "Password must be at least 8 characters"
    else:
        cleaned["password"] = data["password"]
    
    cleaned["first_name"] = data["first_name"].strip()
    cleaned["last_name"] = data["last_name"].strip()
    
    if data.get("phone"):
        cleaned["phone"] = data["phone"].strip()
    
    if errors:
        return None, errors
    
    return cleaned, None


def validate_bulk_user_action(data: Dict[str, Any]) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Validate bulk user action request"""
    errors = {}
    cleaned = {}
    
    action = data.get("action")
    valid_actions = ["activate", "deactivate", "delete"]
    
    if not action:
        errors["action"] = "Action is required"
    elif action not in valid_actions:
        errors["action"] = f"Invalid action. Must be one of: {', '.join(valid_actions)}"
    else:
        cleaned["action"] = action
    
    user_ids = data.get("user_ids", [])
    if not user_ids:
        errors["user_ids"] = "At least one user ID is required"
    elif not isinstance(user_ids, list):
        errors["user_ids"] = "Must be a list of user IDs"
    else:
        cleaned["user_ids"] = user_ids
    
    if errors:
        return None, errors
    
    return cleaned, None