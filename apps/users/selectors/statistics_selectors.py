"""
Statistics Selectors - Database read operations for user statistics
No business logic - just queries
"""

from typing import Dict
from apps.users.models.user import User
from apps.users.models.affiliate import Affiliate
import logging

logger = logging.getLogger(__name__)


def get_user_statistics() -> Dict[str, int]:
    """Get user statistics counts"""
    stats = {
        "total_users": User.objects.count(),
        "total_customers": User.objects.filter(role=User.ROLE_CUSTOMER, is_guest=False).count(),
        "total_guests": User.objects.filter(is_guest=True).count(),
        "total_staff": User.objects.filter(role__in=['admin', 'staff'], is_guest=False).count(),
        "total_admins": User.objects.filter(role='admin', is_guest=False).count(),
        "total_affiliates": Affiliate.objects.filter(is_active=True).count(),
        "active_users": User.objects.filter(is_active=True).count(),
        "inactive_users": User.objects.filter(is_active=False).count(),
        "verified_emails": User.objects.filter(email_verified=True).count(),
        "unverified_emails": User.objects.filter(email_verified=False).count(),
    }
    
    return stats