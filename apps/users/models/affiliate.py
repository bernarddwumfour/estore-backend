# apps/users/models/affiliate.py

"""
Affiliate model for tracking affiliate marketers
"""

import uuid
import secrets
import string
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from apps.users.models.user import User


class Affiliate(models.Model):
    """
    Affiliate model - tracks affiliate marketers and their earnings
    """

    LEVEL_BRONZE = "bronze"
    LEVEL_SILVER = "silver"
    LEVEL_GOLD = "gold"
    LEVEL_PLATINUM = "platinum"

    LEVEL_CHOICES = [
        (LEVEL_BRONZE, "Bronze"),
        (LEVEL_SILVER, "Silver"),
        (LEVEL_GOLD, "Gold"),
        (LEVEL_PLATINUM, "Platinum"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="affiliate_profile",
    )

    # Affiliate identification
    referral_code = models.CharField(
        _("referral code"),
        max_length=50,
        unique=True,
        db_index=True,
    )

    # Earnings tracking
    total_earnings = models.DecimalField(
        _("total earnings"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
    )
    
    pending_earnings = models.DecimalField(
        _("pending earnings"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
    )
    
    paid_earnings = models.DecimalField(
        _("paid earnings"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
    )

    # Referral tracking
    total_referrals = models.PositiveIntegerField(
        _("total referrals"),
        default=0,
    )
    
    active_referrals = models.PositiveIntegerField(
        _("active referrals"),
        default=0,
    )

    # Affiliate level
    level = models.CharField(
        _("affiliate level"),
        max_length=20,
        choices=LEVEL_CHOICES,
        default=LEVEL_BRONZE,
    )

    # Commission rate (percentage)
    commission_rate = models.DecimalField(
        _("commission rate"),
        max_digits=5,
        decimal_places=2,
        default=2.00,
        help_text=_("Commission percentage for this affiliate"),
    )

    # Status
    is_active = models.BooleanField(_("active"), default=True)
    is_approved = models.BooleanField(_("approved"), default=False)

    # Timestamps
    joined_at = models.DateTimeField(_("joined at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    last_payout_at = models.DateTimeField(_("last payout at"), null=True, blank=True)

    class Meta:
        db_table = "affiliates"
        verbose_name = _("affiliate")
        verbose_name_plural = _("affiliates")
        ordering = ["-total_earnings"]
        indexes = [
            models.Index(fields=["referral_code"]),
            models.Index(fields=["is_active"]),
            models.Index(fields=["level"]),
            models.Index(fields=["total_earnings"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.level} - ${self.total_earnings}"

    def save(self, *args, **kwargs):
        """Generate referral code if not exists"""
        if not self.referral_code:
            self.referral_code = self._generate_referral_code()
        super().save(*args, **kwargs)

    def _generate_referral_code(self, length=8):
        """Generate a unique referral code"""
        alphabet = string.ascii_uppercase + string.digits
        code = "".join(secrets.choice(alphabet) for _ in range(length))
        
        while Affiliate.objects.filter(referral_code=code).exists():
            code = "".join(secrets.choice(alphabet) for _ in range(length))
        
        return code

    def update_level(self):
        """Update affiliate level based on total earnings"""
        if self.total_earnings >= 10000:
            self.level = self.LEVEL_PLATINUM
        elif self.total_earnings >= 5000:
            self.level = self.LEVEL_GOLD
        elif self.total_earnings >= 1000:
            self.level = self.LEVEL_SILVER
        else:
            self.level = self.LEVEL_BRONZE
        self.save(update_fields=["level"])

    def add_earnings(self, amount):
        """Add earnings (pending)"""
        from decimal import Decimal
        amount = Decimal(str(amount))
        self.pending_earnings += amount
        self.total_earnings += amount
        self.update_level()
        self.save()

    def mark_earnings_paid(self, amount=None):
        """Mark earnings as paid"""
        from decimal import Decimal
        if amount is None:
            amount = self.pending_earnings
        else:
            amount = Decimal(str(amount))
        
        self.paid_earnings += amount
        self.pending_earnings -= amount
        self.last_payout_at = timezone.now()
        self.save()

    def add_referral(self):
        """Increment referral count"""
        self.total_referrals += 1
        self.active_referrals += 1
        self.save()

    def remove_referral(self):
        """Decrement active referral count"""
        self.active_referrals -= 1
        self.save()

    @property
    def display_level(self):
        """Get display name for level"""
        return self.get_level_display()