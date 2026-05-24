"""
users/models/verification_token.py
"""

import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .user import User
from ..utils.token_utils import generate_verification_token


class VerificationToken(models.Model):
    """Unified token model for verification and password reset"""

    # CHANGED: Added password_reset to TOKEN_TYPES
    TOKEN_TYPES = [
        ("email_verification", "Email Verification"),
        ("account_activation", "Account Activation"),
        ("password_reset", "Password Reset"),  # NEW: Added password reset token type
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="verification_tokens"
    )
    token = models.CharField(_("token"), max_length=100, unique=True, db_index=True)
    token_type = models.CharField(
        _("token type"),
        max_length=20,
        choices=TOKEN_TYPES,
        default="email_verification",
    )

    # Token validity
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    expires_at = models.DateTimeField(_("expires at"), db_index=True)
    is_used = models.BooleanField(_("is used"), default=False, db_index=True)
    used_at = models.DateTimeField(_("used at"), null=True, blank=True, db_index=True)

    # Security logging
    ip_address = models.GenericIPAddressField(_("IP address"), null=True, blank=True)
    user_agent = models.TextField(_("user agent"), blank=True)

    # NEW: Additional metadata for password reset tokens
    additional_data = models.JSONField(
        _("additional data"),
        null=True,
        blank=True,
        help_text="Additional data like IP for password reset",
    )

    class Meta:
        db_table = "verification_tokens"
        verbose_name = _("verification token")
        verbose_name_plural = _("verification tokens")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["token", "is_used"]),
            models.Index(fields=["user", "token_type"]),
            models.Index(fields=["expires_at", "is_used"]),
            models.Index(fields=["created_at"]),
            # NEW: Added index for password reset tokens
            models.Index(fields=["token_type", "is_used", "expires_at"]),
        ]

    def __str__(self):
        return f"{self.token_type} token for {self.user.email}"

    def is_valid(self):
        """Check if token is still valid"""
        return not self.is_used and timezone.now() < self.expires_at

    def mark_as_used(self):
        """Mark token as used"""
        self.is_used = True
        self.used_at = timezone.now()
        self.save()

    @property
    def is_expired(self):
        """Check if token is expired"""
        return timezone.now() >= self.expires_at

    @property
    def age_in_minutes(self):
        """Get token age in minutes"""
        return (timezone.now() - self.created_at).total_seconds() / 60

    # NEW: Helper methods for password reset tokens
    @property
    def is_password_reset_token(self):
        """Check if this is a password reset token"""
        return self.token_type == "password_reset"

    @property
    def is_email_verification_token(self):
        """Check if this is an email verification token"""
        return self.token_type == "email_verification"

    @classmethod
    def create_password_reset_token(cls, user, expires_in_hours=1, request=None):
        """Create a password reset token"""

        token = generate_verification_token(user)
        expires_at = timezone.now() + timezone.timedelta(hours=expires_in_hours)

        verification_token = cls.objects.create(
            user=user, token=token, token_type="password_reset", expires_at=expires_at
        )

        # Log request info if available
        if request:
            verification_token.ip_address = request.META.get("REMOTE_ADDR")
            verification_token.user_agent = request.META.get("HTTP_USER_AGENT", "")
            verification_token.save()

        return verification_token
