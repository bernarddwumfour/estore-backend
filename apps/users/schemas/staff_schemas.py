"""
Staff Schemas - Serialization and validation for staff/admin users
"""

from typing import Dict, Any, List, Optional, Tuple
from apps.users.models.user import User


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