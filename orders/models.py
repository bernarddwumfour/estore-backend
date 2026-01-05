# models.py
import decimal
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid
from products.models import ProductVariant
from users.models.user import User
from users.models.address import Address
from decimal import Decimal


class Order(models.Model):
    """
    Main order model (simplified - addresses moved to separate model)
    """

    # Order statuses
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_PROCESSING = "processing"
    STATUS_SHIPPED = "shipped"
    STATUS_DELIVERED = "delivered"
    STATUS_CANCELLED = "cancelled"
    STATUS_REFUNDED = "refunded"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_SHIPPED, "Shipped"),
        (STATUS_DELIVERED, "Delivered"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    # Payment statuses
    PAYMENT_PENDING = "pending"
    PAYMENT_PAID = "paid"
    PAYMENT_FAILED = "failed"
    PAYMENT_REFUNDED = "refunded"

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_PENDING, "Pending"),
        (PAYMENT_PAID, "Paid"),
        (PAYMENT_FAILED, "Failed"),
        (PAYMENT_REFUNDED, "Refunded"),
    ]

    # Payment methods
    PAYMENT_CREDIT_CARD = "credit_card"
    PAYMENT_MOBILE_MONEY = "mobile_money"
    PAYMENT_BANK_TRANSFER = "bank_transfer"
    PAYMENT_CASH_ON_DELIVERY = "cash_on_delivery"

    PAYMENT_METHOD_CHOICES = [
        (PAYMENT_CREDIT_CARD, "Credit Card"),
        (PAYMENT_MOBILE_MONEY, "Mobile Money"),
        (PAYMENT_BANK_TRANSFER, "Bank Transfer"),
        (PAYMENT_CASH_ON_DELIVERY, "Cash on Delivery"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Customer relationship
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )

    # Guest checkout information
    guest_email = models.EmailField(_("guest email"), blank=True)
    guest_first_name = models.CharField(
        _("guest first name"), max_length=50, blank=True
    )
    guest_last_name = models.CharField(_("guest last name"), max_length=50, blank=True)
    guest_phone = models.CharField(_("guest phone"), max_length=20, blank=True)

    # Order details
    order_number = models.CharField(
        _("order number"), max_length=20, unique=True, db_index=True, editable=False
    )

    # Status tracking
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )

    payment_status = models.CharField(
        _("payment status"),
        max_length=20,
        choices=PAYMENT_STATUS_CHOICES,
        default=PAYMENT_PENDING,
        db_index=True,
    )

    payment_method = models.CharField(
        _("payment method"), max_length=20, choices=PAYMENT_METHOD_CHOICES
    )

    # Address relationships
    shipping_address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name="shipping_orders",
        verbose_name=_("shipping address"),
    )

    billing_address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name="billing_orders",
        verbose_name=_("billing address"),
    )

    # Pricing
    subtotal = models.DecimalField(
        _("subtotal"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)],
    )

    shipping_cost = models.DecimalField(
        _("shipping cost"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)],
    )

    tax_amount = models.DecimalField(
        _("tax amount"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)],
    )

    tax_rate = models.DecimalField(
        _("tax rate"),
        max_digits=5,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )

    discount_amount = models.DecimalField(
        _("discount amount"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)],
    )

    total = models.DecimalField(
        _("total"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0)],
    )

    currency = models.CharField(_("currency"), max_length=3, default="USD")

    shipping_method = models.CharField(_("shipping method"), max_length=100, blank=True)

    # tracking_number = models.CharField(_("tracking number"), max_length=100, blank=True)

    carrier = models.CharField(_("carrier"), max_length=100, blank=True)

    payment_intent_id = models.CharField(
        _("payment intent id"), max_length=100, blank=True
    )

    payment_receipt_url = models.URLField(
        _("payment receipt url"), max_length=500, blank=True
    )

    customer_note = models.TextField(_("customer note"), blank=True)
    admin_note = models.TextField(_("admin note"), blank=True)

    email_sent = models.BooleanField(_("confirmation email sent"), default=False)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    paid_at = models.DateTimeField(_("paid at"), null=True, blank=True)
    confirmed_at = models.DateTimeField(_("confirmed at"), null=True, blank=True)
    shipped_at = models.DateTimeField(_("shipped at"), null=True, blank=True)
    delivered_at = models.DateTimeField(_("delivered at"), null=True, blank=True)
    cancelled_at = models.DateTimeField(_("cancelled at"), null=True, blank=True)

    class Meta:
        db_table = "orders"
        verbose_name = _("order")
        verbose_name_plural = _("orders")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order_number"]),
            models.Index(fields=["status"]),
            models.Index(fields=["payment_status"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["guest_email"]),
        ]

    def __str__(self):
        return f"Order #{self.order_number}"

    def save(self, *args, **kwargs):
        """Generate order number and set timestamps"""
        from django.utils import timezone
        import random

        if not self.order_number:
            date_str = timezone.now().strftime("%Y%m%d")
            random_str = str(random.randint(1000, 9999))
            self.order_number = f"ORD{date_str}{random_str}"

        self.total = (
            self.subtotal + self.shipping_cost + self.tax_amount - self.discount_amount
        )

        super().save(*args, **kwargs)

    @property
    def customer_name(self):
        """Get customer name"""
        if self.user:
            return self.user.get_full_name() or self.user.email
        return f"{self.guest_first_name} {self.guest_last_name}"

    @property
    def customer_email(self):
        """Get customer email"""
        if self.user:
            return self.user.email
        return self.guest_email

    @property
    def item_count(self):
        """Get total number of items"""
        return sum(item.quantity for item in self.items.all())

    @property
    def can_cancel(self):
        """Check if order can be cancelled"""
        cancellable_statuses = [self.STATUS_PENDING, self.STATUS_CONFIRMED]
        return self.status in cancellable_statuses


class OrderItem(models.Model):
    """
    Individual items within an order
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")

    variant = models.ForeignKey(
        ProductVariant, on_delete=models.SET_NULL, null=True, related_name="order_items"
    )

    product_title = models.CharField(_("product title"), max_length=200)
    product_slug = models.SlugField(_("product slug"), max_length=200)
    variant_attributes = models.JSONField(_("variant attributes"), default=dict)
    sku = models.CharField(_("SKU"), max_length=100)

    unit_price = models.DecimalField(
        _("unit price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )

    discount_amount = models.DecimalField(
        _("discount amount"), max_digits=10, decimal_places=2, default=0.00
    )

    quantity = models.PositiveIntegerField(
        _("quantity"), default=1, validators=[MinValueValidator(1)]
    )

    total_price = models.DecimalField(
        _("total price"), max_digits=10, decimal_places=2, default=0.00
    )

    class Meta:
        db_table = "order_items"
        verbose_name = _("order item")
        verbose_name_plural = _("order items")
        ordering = ["id"]
        indexes = [
            models.Index(fields=["order", "sku"]),
        ]

    def __str__(self):
        return f"{self.product_title} x {self.quantity}"

    def save(self, *args, **kwargs):
        """Calculate total price and save product info"""
        if self.variant and not self.product_title:
            self.product_title = self.variant.product.title
            self.product_slug = self.variant.product.slug
            self.variant_attributes = self.variant.attributes
            self.sku = self.variant.sku

        # FIX: Ensure all values are Decimal before arithmetic
        unit_price = (
            Decimal(str(self.unit_price))
            if not isinstance(self.unit_price, Decimal)
            else self.unit_price
        )
        discount = (
            Decimal(str(self.discount_amount))
            if not isinstance(self.discount_amount, Decimal)
            else self.discount_amount
        )
        quantity = (
            Decimal(str(self.quantity))
            if not isinstance(self.quantity, (Decimal, int))
            else Decimal(str(self.quantity))
        )

        self.total_price = (unit_price - discount) * quantity

        super().save(*args, **kwargs)

    @property
    def discounted_unit_price(self):
        """Get discounted unit price"""
        # Ensure Decimal types
        unit_price = (
            Decimal(str(self.unit_price))
            if not isinstance(self.unit_price, Decimal)
            else self.unit_price
        )
        discount = (
            Decimal(str(self.discount_amount))
            if not isinstance(self.discount_amount, Decimal)
            else self.discount_amount
        )
        return unit_price - discount
