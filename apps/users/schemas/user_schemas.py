"""
User Schemas - Serialization and validation for users
"""

from typing import Dict, Any, List, Optional, Tuple
from apps.users.models.user import User
from apps.users.schemas.address_schemas import serialize_address, serialize_addresses


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
            if hasattr(user, 'addresses'):
                addresses_qs = user.addresses.filter(is_active=True)
                addresses = list(addresses_qs)
                
                if addresses:
                    data["addresses"] = serialize_addresses(addresses, is_admin)
                    
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