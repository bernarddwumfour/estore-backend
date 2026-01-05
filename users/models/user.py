"""
users/models/user.py

ULTIMATE LEAN User model - authentication only
Everything else moved to related models
"""

import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from ..managers import UserManager


class User(AbstractUser):
    """
    Core User model - authentication and identity only
    Following "Lean Models, Fat Services" pattern
    """

    # Roles for single business
    ROLE_ADMIN = "admin"
    ROLE_STAFF = "staff"
    ROLE_CUSTOMER = "customer"

    ROLE_CHOICES = [
        (ROLE_ADMIN, "Administrator"),
        (ROLE_STAFF, "Staff"),
        (ROLE_CUSTOMER, "Customer"),
    ]

    # Core identity
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(_("email"), unique=True, db_index=True)

    # Username optional
    username = models.CharField(
        _("username"),
        max_length=150,
        unique=False,  # Not unique
        blank=True,
        null=True,
    )

    # Basic personal info
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)

    # Single phone field for basic contact
    phone = models.CharField(_("phone"), max_length=20, blank=True)

    # Role & status
    role = models.CharField(
        max_length=20, choices=ROLE_CHOICES, default=ROLE_CUSTOMER, db_index=True
    )

    email_verified = models.BooleanField(_("email verified"), default=False)

    email_verified_at = models.DateTimeField(
        _("email verified at"), null=True, blank=True, db_index=True
    )

    # Add this property method to your User class:
    @property
    def is_verified(self):
        """Alias for email_verified for compatibility"""
        return self.email_verified

    def mark_email_verified(self):
        """Mark email as verified with timestamp"""
        self.email_verified = True
        self.email_verified_at = timezone.now()
        self.save()

    is_active = models.BooleanField(_("active"), default=True, db_index=True)

    # Timestamps
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    # Manager
    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []  # No required fields except email

    class Meta:
        db_table = "users"
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["email"]),
            models.Index(fields=["role", "is_active"]),
        ]

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email.split("@")[0]

    # Role checkers
    def is_admin(self):
        return self.role == self.ROLE_ADMIN

    def is_staff_member(self):
        return self.role == self.ROLE_STAFF

    def is_customer(self):
        return self.role == self.ROLE_CUSTOMER

    def can_access_admin(self):
        return self.is_admin() or (self.is_staff_member() and self.is_staff)


class PasswordResetToken(models.Model):
    """Password reset token model"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="password_reset_tokens"
    )
    token = models.CharField(max_length=100, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Security logging
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)

    class Meta:
        db_table = "password_reset_tokens"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token"]),
            models.Index(fields=["user", "used_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Password reset for {self.user.email}"

    def is_valid(self):
        """Check if token is still valid"""
        return not self.used_at and timezone.now() < self.expires_at

    def mark_as_used(self):
        self.used_at = timezone.now()
        self.save()
