from django.db import models

# Create your models here.
"""
Promotions models - Bundle deals and offers
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone

from apps.products.models import ProductVariant
from apps.users.models import User


class Promotion(models.Model):
    """Bundle promotion - group of variants sold together at a discounted price"""
    
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_ENDED = "ended"
    
    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_ENDED, "Ended"),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Basic information
    name = models.CharField(_("name"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=200, unique=True)
    description = models.TextField(_("description"), blank=True)
    
    # Pricing
    bundle_price = models.DecimalField(
        _("bundle price"),
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text=_("Discounted price for the entire bundle")
    )
    
    # Status
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True
    )
    
    # Date range
    starts_at = models.DateTimeField(_("starts at"), db_index=True)
    ends_at = models.DateTimeField(_("ends at"), null=True, blank=True, db_index=True)
    
    # SEO
    meta_title = models.CharField(_("meta title"), max_length=200, blank=True)
    meta_description = models.TextField(_("meta description"), blank=True)
    
    # Audit
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_promotions"
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    
    class Meta:
        db_table = "promotions"
        verbose_name = _("promotion")
        verbose_name_plural = _("promotions")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status", "starts_at", "ends_at"]),
            models.Index(fields=["created_at"]),
        ]
    
    def __str__(self):
        return self.name
    
    @property
    def is_currently_active(self) -> bool:
        """Check if promotion is currently active"""
        if self.status != self.STATUS_ACTIVE:
            return False
        now = timezone.now()
        if self.starts_at > now:
            return False
        if self.ends_at and self.ends_at < now:
            return False
        return True
    
    @property
    def has_stock(self) -> bool:
        """Check if all items have sufficient stock"""
        for item in self.items.all():
            if not item.has_sufficient_stock:
                return False
        return True
    
    @property
    def original_total(self) -> float:
        """Calculate original total price of all items"""
        total = sum(
            float(item.original_price * item.quantity) 
            for item in self.items.select_related('variant').all()
        )
        return round(total, 2)

    @property
    def savings_amount(self) -> float:
        """Calculate total savings"""
        return round(self.original_total - float(self.bundle_price), 2)

    @property
    def unavailable_items(self) -> list:
        """Get list of items that are out of stock or have insufficient stock"""
        unavailable = []
        for item in self.items.all():
            if not item.has_sufficient_stock:
                unavailable.append({
                    "sku": item.variant.sku,
                    "product_title": item.variant.product.title,
                    "required": item.quantity,
                    "available": item.variant.stock
                })
        return unavailable


class PromotionItem(models.Model):
    """Individual item within a promotion bundle"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    promotion = models.ForeignKey(
        Promotion,
        on_delete=models.CASCADE,
        related_name="items"
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="promotion_items"
    )
    
    # Quantity and pricing snapshots
    quantity = models.PositiveIntegerField(_("quantity"), default=1)
    original_price = models.DecimalField(
        _("original price"),
        max_digits=10,
        decimal_places=2,
        help_text=_("Price at promotion creation time")
    )
    cost_price_snapshot = models.DecimalField(
        _("cost price snapshot"),
        max_digits=10,
        decimal_places=2,
        default=0.00,
        help_text=_("Cost price at promotion creation time for profit calculation")
    )
    
    # Flags
    is_free = models.BooleanField(
        _("free item"),
        default=False,
        help_text=_("Item is given for free (counts toward bundle but no cost)")
    )
    is_available = models.BooleanField(_("available"), default=True)
    
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    
    class Meta:
        db_table = "promotion_items"
        verbose_name = _("promotion item")
        verbose_name_plural = _("promotion items")
        unique_together = [("promotion", "variant")]
        indexes = [
            models.Index(fields=["promotion", "variant"]),
            models.Index(fields=["is_available"]),
        ]
    
    def __str__(self):
        return f"{self.promotion.name} - {self.variant.sku} x{self.quantity}"
    
    @property
    def has_sufficient_stock(self) -> bool:
        """Check if variant has enough stock for this item"""
        return self.variant.stock >= self.quantity
    
    @property
    def item_gross_profit(self) -> float:
        """Calculate gross profit for this item at snapshot prices"""
        if self.is_free:
            return round(0 - float(self.cost_price_snapshot * self.quantity), 2)
        return round(float((self.original_price - self.cost_price_snapshot) * self.quantity), 2)

    @property
    def item_margin_percentage(self) -> float:
        """Calculate margin percentage for this item"""
        if self.is_free or self.original_price == 0:
            return 0
        total_revenue = float(self.original_price * self.quantity)
        if total_revenue == 0:
            return 0
        return round((self.item_gross_profit / total_revenue) * 100, 2)
    
    def refresh_availability(self) -> None:
        """Update availability based on current stock"""
        self.is_available = self.has_sufficient_stock
        self.save(update_fields=["is_available"])


class PromotionImage(models.Model):
    """Images for promotions (banners, thumbnails)"""
    
    IMAGE_TYPE_BANNER = "banner"
    IMAGE_TYPE_THUMBNAIL = "thumbnail"
    IMAGE_TYPE_GALLERY = "gallery"
    
    IMAGE_TYPES = [
        (IMAGE_TYPE_BANNER, "Banner"),
        (IMAGE_TYPE_THUMBNAIL, "Thumbnail"),
        (IMAGE_TYPE_GALLERY, "Gallery"),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    promotion = models.ForeignKey(
        Promotion,
        on_delete=models.CASCADE,
        related_name="images"
    )
    
    image = models.ImageField(_("image"), upload_to="promotions/%Y/%m/")
    image_type = models.CharField(
        _("image type"),
        max_length=20,
        choices=IMAGE_TYPES,
        default=IMAGE_TYPE_GALLERY
    )
    alt_text = models.CharField(_("alt text"), max_length=200, blank=True)
    order = models.PositiveIntegerField(_("display order"), default=0)
    is_active = models.BooleanField(_("active"), default=True)
    
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    
    class Meta:
        db_table = "promotion_images"
        verbose_name = _("promotion image")
        verbose_name_plural = _("promotion images")
        ordering = ["order", "created_at"]
    
    def __str__(self):
        return f"Image for {self.promotion.name}"