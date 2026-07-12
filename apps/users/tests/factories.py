"""
Test data factories/helpers for the users app test-suite.

Plain helper functions that build valid model instances so each test stays
focused on the behaviour under test rather than fixture setup.
"""

import uuid

from django.contrib.auth import get_user_model

from apps.users.models.address import Address
from apps.users.models.affiliate import Affiliate

User = get_user_model()


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def make_user(role: str = "customer", **kwargs) -> "User":
    """Create a user with sensible defaults.  Override any field via kwargs."""
    email = kwargs.pop("email", f"{_unique('user')}@example.com")
    password = kwargs.pop("password", "Str0ng-Pass!23")
    first_name = kwargs.pop("first_name", "Test")
    last_name = kwargs.pop("last_name", "User")
    is_active = kwargs.pop("is_active", True)
    email_verified = kwargs.pop("email_verified", True)
    return User.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=role,
        is_active=is_active,
        email_verified=email_verified,
        **kwargs,
    )


def make_admin(**kwargs) -> "User":
    """Shortcut for creating an admin user."""
    return make_user(role="admin", **kwargs)


def make_staff(**kwargs) -> "User":
    """Shortcut for creating a staff user."""
    return make_user(role="staff", **kwargs)


def make_inactive_user(**kwargs) -> "User":
    """Shortcut for creating an inactive user."""
    return make_user(is_active=False, email_verified=False, **kwargs)


def make_address(user: User = None, **kwargs) -> Address:
    """Create a shipping/billing address.  Creates a user if none provided."""
    if user is None:
        user = make_user()
    return Address.objects.create(
        user=user,
        address_type=kwargs.pop("address_type", "shipping"),
        first_name=kwargs.pop("first_name", "Test"),
        last_name=kwargs.pop("last_name", "User"),
        address_line1=kwargs.pop("address_line1", "123 Test Street"),
        address_line2=kwargs.pop("address_line2", ""),
        city=kwargs.pop("city", "Accra"),
        state=kwargs.pop("state", "Greater Accra"),
        postal_code=kwargs.pop("postal_code", "GA-123"),
        country=kwargs.pop("country", "GH"),
        phone=kwargs.pop("phone", "+233501234567"),
        is_default=kwargs.pop("is_default", False),
        **kwargs,
    )


def make_affiliate(user: User = None, **kwargs) -> Affiliate:
    """Create an affiliate linked to a user.  Creates a user if none provided."""
    if user is None:
        user = make_user()
    return Affiliate.objects.create(
        user=user,
        referral_code=kwargs.pop("referral_code", _unique("REF").upper()),
        commission_rate=kwargs.pop("commission_rate", 5.00),
        is_active=kwargs.pop("is_active", True),
        **kwargs,
    )
