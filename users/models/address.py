"""
users/models/address.py

Simple, practical address management for e-commerce
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from users.models.user import User


class Address(models.Model):
    """
    Reusable address model for both shipping and billing
    """

    ADDRESS_TYPE_SHIPPING = "shipping"
    ADDRESS_TYPE_BILLING = "billing"

    ADDRESS_TYPE_CHOICES = [
        (ADDRESS_TYPE_SHIPPING, "Shipping Address"),
        (ADDRESS_TYPE_BILLING, "Billing Address"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # User relationship (optional for guest orders)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="addresses",
    )

    # Address type
    address_type = models.CharField(
        _("address type"),
        max_length=20,
        choices=ADDRESS_TYPE_CHOICES,
        default=ADDRESS_TYPE_SHIPPING,
    )

    # Contact information
    first_name = models.CharField(_("first name"), max_length=50)
    last_name = models.CharField(_("last name"), max_length=50)
    company = models.CharField(_("company"), max_length=100, blank=True)
    phone = models.CharField(_("phone number"), max_length=20)
    email = models.EmailField(_("email"))

    # Address details
    address_line1 = models.CharField(_("address line 1"), max_length=255)
    address_line2 = models.CharField(_("address line 2"), max_length=255, blank=True)
    city = models.CharField(_("city"), max_length=100)
    state = models.CharField(_("state/province"), max_length=100)
    postal_code = models.CharField(_("postal code"), max_length=20)
    country = models.CharField(_("country"), max_length=100)

    # Flags
    is_default = models.BooleanField(_("default address"), default=False)
    is_active = models.BooleanField(_("active"), default=True)

    # Additional info
    instructions = models.TextField(_("delivery instructions"), blank=True)

    # Timestamps
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "addresses"
        verbose_name = _("address")
        verbose_name_plural = _("addresses")
        ordering = ["-is_default", "-created_at"]
        indexes = [
            models.Index(fields=["user", "address_type"]),
            models.Index(fields=["user", "is_default"]),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}, {self.city}"

    def save(self, *args, **kwargs):
        """Ensure only one default address per user per type"""
        if self.is_default and self.user:
            # Clear other defaults of same type for this user
            Address.objects.filter(
                user=self.user, address_type=self.address_type, is_default=True
            ).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_address(self):
        parts = [
            self.full_name,
            self.company,
            self.address_line1,
            self.address_line2,
            f"{self.city}, {self.state} {self.postal_code}",
            self.country,
        ]
        return ", ".join(filter(None, parts))

    def to_dict(self):
        """Convert address to dictionary"""
        return {
            "id": str(self.id),
            "address_type": self.address_type,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "company": self.company,
            "phone": self.phone,
            "email": self.email,
            "address_line1": self.address_line1,
            "address_line2": self.address_line2,
            "city": self.city,
            "state": self.state,
            "postal_code": self.postal_code,
            "country": self.country,
            "instructions": self.instructions,
            "is_default": self.is_default,
            "full_address": self.full_address,
        }
