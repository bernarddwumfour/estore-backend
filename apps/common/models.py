"""
Common models for system-wide features
"""

import uuid
from decimal import Decimal
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MaxLengthValidator


class SystemLog(models.Model):
    """
    Store structured logs for UI filtering and analysis.
    """
    
    SEVERITY_CHOICES = [
        ("DEBUG", "Debug"),
        ("INFO", "Info"),
        ("WARNING", "Warning"),
        ("ERROR", "Error"),
        ("CRITICAL", "Critical"),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Core fields with length limits
    app_name = models.CharField(_("app name"), max_length=50, db_index=True)
    action = models.CharField(_("action"), max_length=100, db_index=True)
    severity = models.CharField(_("severity"), max_length=20, choices=SEVERITY_CHOICES, db_index=True)
    description = models.TextField(_("description"), validators=[MaxLengthValidator(1000)])
    status_code = models.IntegerField(_("status code"), db_index=True)
    
    # User context
    user_id = models.CharField(_("user id"), max_length=100, blank=True, null=True, db_index=True)
    user_email = models.CharField(_("user email"), max_length=255, blank=True, null=True)
    
    # Request context
    ip_address = models.GenericIPAddressField(_("IP address"), blank=True, null=True)
    path = models.CharField(_("request path"), max_length=500, blank=True,null=True)
    method = models.CharField(_("HTTP method"), max_length=10, blank=True,null=True)
    
    # Additional data (limited size)
    extra_data = models.JSONField(_("extra data"), default=dict, blank=True)
    
    # Timestamp
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    
    class Meta:
        db_table = "system_logs"
        verbose_name = _("system log")
        verbose_name_plural = _("system logs")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["app_name", "created_at"]),
            models.Index(fields=["severity", "created_at"]),
            models.Index(fields=["user_id", "created_at"]),
            models.Index(fields=["action", "created_at"]),
            models.Index(fields=["status_code", "created_at"]),
            models.Index(fields=["app_name", "action", "severity"]),
            models.Index(fields=["created_at"]),  # For time-based queries
        ]
    
    def __str__(self):
        return f"[{self.severity}] {self.app_name}.{self.action} - {self.created_at.strftime('%Y-%m-%d %H:%M:%S')}"


def default_notifications():
    """Per-event notification channel switches. Email is live; sms/whatsapp
    are stored for future providers and stay inert until one is integrated."""
    return {
        "order_confirmation": {"email": True, "sms": False, "whatsapp": False},
        "order_shipped": {"email": True, "sms": False, "whatsapp": False},
        "order_delivered": {"email": True, "sms": False, "whatsapp": False},
    }


GENERAL_CONFIG_CACHE_KEY = "general_config_v1"


class GeneralConfig(models.Model):
    """Singleton store-wide runtime configuration.

    Consumed across apps (orders payments/emails/rules, products inventory,
    email utils). Hot-path readers must fail open — a config problem can
    never be allowed to break an order or an email.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    # Payments
    paystack_enabled = models.BooleanField(_("Paystack enabled"), default=True)
    pod_enabled = models.BooleanField(_("Pay on Delivery enabled"), default=True)
    default_payment_method = models.CharField(
        _("default payment method"), max_length=20, default="paystack"
    )
    pod_max_order_value = models.DecimalField(
        _("POD max order value"), max_digits=10, decimal_places=2, default=Decimal("500.00")
    )
    pod_max_quantity = models.PositiveIntegerField(_("POD max quantity"), default=10)
    paystack_min_amount = models.DecimalField(
        _("Paystack min amount"), max_digits=10, decimal_places=2, default=Decimal("1.00")
    )
    paystack_max_amount = models.DecimalField(
        _("Paystack max amount"), max_digits=10, decimal_places=2, default=Decimal("999999.99")
    )

    # Notifications: {event: {email/sms/whatsapp: bool}}
    notifications = models.JSONField(_("notifications"), default=default_notifications)

    # Order rules
    guest_checkout_enabled = models.BooleanField(_("guest checkout enabled"), default=True)
    min_order_value = models.DecimalField(
        _("minimum order value"), max_digits=10, decimal_places=2, default=Decimal("0.00")
    )
    order_number_prefix = models.CharField(
        _("order number prefix"), max_length=10, default="ORD"
    )
    auto_cancel_unpaid_hours = models.PositiveIntegerField(
        _("auto-cancel unpaid after (hours)"), default=0
    )

    # Store identity (blank = fall back to settings)
    store_name = models.CharField(_("store name"), max_length=100, blank=True)
    support_email = models.CharField(_("support email"), max_length=255, blank=True)
    support_phone = models.CharField(_("support phone"), max_length=30, blank=True)
    currency = models.CharField(_("currency"), max_length=3, default="GHS")
    store_country = models.CharField(_("store country"), max_length=2, blank=True)
    store_state = models.CharField(_("store state/region"), max_length=80, blank=True)
    store_city = models.CharField(_("store city"), max_length=80, blank=True)
    store_postal_code = models.CharField(_("store postal code"), max_length=20, blank=True)
    store_address = models.CharField(_("store address"), max_length=255, blank=True)

    # Inventory
    default_low_stock_threshold = models.PositiveIntegerField(
        _("default low-stock threshold"), default=5
    )
    hide_out_of_stock = models.BooleanField(_("hide out-of-stock products"), default=False)
    tax_rate = models.DecimalField(
        _("tax rate (%)"), max_digits=5, decimal_places=2, default=Decimal("0.00")
    )
    # When on, prices already contain tax: nothing is added at checkout and
    # the storefront shows "included in prices" instead of a tax line
    tax_inclusive = models.BooleanField(_("tax included in product prices"), default=False)

    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "general_config"
        verbose_name = _("general config")
        verbose_name_plural = _("general config")

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)
        from django.core.cache import cache
        cache.delete(GENERAL_CONFIG_CACHE_KEY)

    @classmethod
    def get(cls) -> "GeneralConfig":
        config, _created = cls.objects.get_or_create(pk=1)
        return config

    @classmethod
    def get_cached(cls) -> "GeneralConfig":
        from django.core.cache import cache
        config = cache.get(GENERAL_CONFIG_CACHE_KEY)
        if config is None:
            config = cls.get()
            cache.set(GENERAL_CONFIG_CACHE_KEY, config, 60)
        return config

    def notification_enabled(self, event: str, channel: str) -> bool:
        """Email fails open (a broken config must never kill receipts);
        sms/whatsapp fail closed (no provider is integrated yet)."""
        try:
            return bool(self.notifications[event][channel])
        except (KeyError, TypeError):
            return channel == "email"

    def __str__(self):
        return "General configuration"