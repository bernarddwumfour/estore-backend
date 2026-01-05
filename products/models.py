"""
products/models.py

E-commerce Product System with Variants
"""

import uuid
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.core.validators import MinValueValidator, MaxValueValidator
from django.contrib.auth import get_user_model

User = get_user_model()


class Category(models.Model):
    """Product categories"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=100, unique=True)
    slug = models.SlugField(_("slug"), max_length=100, unique=True)
    description = models.TextField(_("description"), blank=True)
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="children"
    )
    image = models.ImageField(
        _("category image"), upload_to="categories/%Y/%m/", null=True, blank=True
    )

    # SEO fields
    meta_title = models.CharField(_("meta title"), max_length=200, blank=True)
    meta_description = models.TextField(_("meta description"), blank=True)

    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "categories"
        verbose_name = _("category")
        verbose_name_plural = _("categories")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return self.name

    @property
    def full_path(self):
        """Get full category path (e.g., Electronics > Audio > Headphones)"""
        path = [self.name]
        parent = self.parent
        while parent:
            path.insert(0, parent.name)
            parent = parent.parent
        return " > ".join(path)


class Brand(models.Model):
    """Product brands"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=100, unique=True)
    slug = models.SlugField(_("slug"), max_length=100, unique=True)
    description = models.TextField(_("description"), blank=True)
    logo = models.ImageField(
        _("brand logo"), upload_to="brands/%Y/%m/", null=True, blank=True
    )

    # Considering
    website = models.URLField(_("website"), blank=True)

    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "brands"
        verbose_name = _("brand")
        verbose_name_plural = _("brands")
        ordering = ["name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    """
    Main product model (represents a product group with variants)
    Example: "Wireless Over-Ear Headphones" has variants for different brands/colors
    """

    # Product status
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Basic information
    title = models.CharField(_("title"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=200, unique=True)
    description = models.TextField(_("description"))

    # SEO
    meta_title = models.CharField(_("meta title"), max_length=200, blank=True)
    meta_description = models.TextField(_("meta description"), blank=True)

    # Categorization
    category = models.ForeignKey(
        Category, on_delete=models.SET_NULL, null=True, related_name="products"
    )

    # Features (stored as JSON for flexibility)
    features = models.JSONField(
        _("features"), default=list, blank=True, help_text=_("List of product features")
    )

    # Available options for variants (e.g., {"brand": ["Generic", "Sony"], "color": ["Black", "White"]})
    options = models.JSONField(
        _("variant options"),
        default=dict,
        blank=True,
        help_text=_("Available options for product variants"),
    )

    # Product status
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )

    # Flags
    is_featured = models.BooleanField(_("featured"), default=False)
    is_bestseller = models.BooleanField(_("bestseller"), default=False)
    is_new = models.BooleanField(_("new arrival"), default=False)

    # Ratings (cached for performance)
    average_rating = models.DecimalField(
        _("average rating"),
        max_digits=3,
        decimal_places=2,
        default=0.00,
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    total_reviews = models.PositiveIntegerField(_("total reviews"), default=0)

    # Timestamps
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)

    class Meta:
        db_table = "products"
        verbose_name = _("product")
        verbose_name_plural = _("products")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status"]),
            models.Index(fields=["is_featured"]),
            models.Index(fields=["is_bestseller"]),
            models.Index(fields=["average_rating"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        """Set published_at when status changes to published"""
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            from django.utils import timezone

            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def default_variant(self):
        """Get the default variant (first variant or marked as default)"""
        try:
            return (
                self.variants.filter(is_default=True).first() or self.variants.first()
            )
        except AttributeError:
            return None

    @property
    def min_price(self):
        """Get minimum price among all variants"""
        variants = self.variants.all()
        if variants:
            return min(variant.price for variant in variants)
        return 0

    @property
    def max_price(self):
        """Get maximum price among all variants"""
        variants = self.variants.all()
        if variants:
            return max(variant.price for variant in variants)
        return 0

    @property
    def total_stock(self):
        """Get total stock across all variants"""
        return sum(variant.stock for variant in self.variants.all())

    @property
    def has_stock(self):
        """Check if any variant has stock"""
        return any(variant.stock > 0 for variant in self.variants.all())


class ProductVariant(models.Model):
    """
    Product variant - different SKUs with specific attributes
    Example: "GEN-BLK-NEW" (Generic, Black, New) for headphones
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="variants"
    )

    # SKU and identifier
    sku = models.CharField(
        _("SKU"),
        max_length=100,
        unique=True,
        db_index=True,
        help_text=_("Stock Keeping Unit"),
    )

    # Variant-specific attributes (e.g., {"brand": "Generic", "color": "Black", "condition": "New"})
    attributes = models.JSONField(
        _("attributes"),
        default=dict,
        help_text=_("Specific attributes for this variant"),
    )

    # Pricing
    price = models.DecimalField(
        _("price"), max_digits=10, decimal_places=2, validators=[MinValueValidator(0)]
    )

    discount_amount = models.DecimalField(
        _("discount amount"),
        max_digits=10,
        decimal_places=2,
        default=0,
        help_text=_("Amount discounted from base price"),
    )

    # Inventory
    stock = models.PositiveIntegerField(_("stock quantity"), default=0)
    low_stock_threshold = models.PositiveIntegerField(
        _("low stock threshold"),
        default=5,
        help_text=_("Alert when stock falls below this"),
    )

    # Flags
    is_default = models.BooleanField(
        _("default variant"),
        default=False,
        help_text=_("Default variant for this product"),
    )
    is_active = models.BooleanField(_("active"), default=True)

    # Dimensions/weight (for shipping calculations)
    weight = models.DecimalField(
        _("weight (kg)"), max_digits=8, decimal_places=3, null=True, blank=True
    )
    height = models.DecimalField(
        _("height (cm)"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    width = models.DecimalField(
        _("width (cm)"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    depth = models.DecimalField(
        _("depth (cm)"), max_digits=8, decimal_places=2, null=True, blank=True
    )

    # Timestamps
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "product_variants"
        verbose_name = _("product variant")
        verbose_name_plural = _("product variants")
        ordering = ["-is_default", "sku"]
        indexes = [
            models.Index(fields=["sku"]),
            models.Index(fields=["product", "is_active"]),
            models.Index(fields=["stock"]),
        ]
        constraints = [
            # Ensure only one default variant per product
            models.UniqueConstraint(
                fields=["product"],
                condition=models.Q(is_default=True),
                name="unique_default_variant",
            ),
        ]

    def __str__(self):
        return f"{self.sku} - {self.product.title}"

    def save(self, *args, **kwargs):
        """Ensure only one default variant per product"""
        if self.is_default:
            ProductVariant.objects.filter(
                product=self.product, is_default=True
            ).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def discounted_price(self):
        """Calculate discounted price"""
        return self.price - self.discount_amount

    @property
    def discount_percentage(self):
        """Calculate discount percentage"""
        if self.price > 0 and self.discount_amount > 0:
            return (self.discount_amount / self.price) * 100
        return 0

    @property
    def is_in_stock(self):
        """Check if variant is in stock"""
        return self.stock > 0

    @property
    def is_low_stock(self):
        """Check if stock is low"""
        return 0 < self.stock <= self.low_stock_threshold

    def reduce_stock(self, quantity):
        """Reduce stock by quantity"""
        if quantity > self.stock:
            raise ValueError(
                f"Insufficient stock. Available: {self.stock}, Requested: {quantity}"
            )
        self.stock -= quantity
        self.save(update_fields=["stock"])

    def increase_stock(self, quantity):
        """Increase stock by quantity"""
        self.stock += quantity
        self.save(update_fields=["stock"])


class VariantImage(models.Model):
    """Images for product variants"""

    IMAGE_TYPE_MAIN = "main"
    IMAGE_TYPE_GALLERY = "gallery"
    IMAGE_TYPE_THUMBNAIL = "thumbnail"

    IMAGE_TYPES = [
        (IMAGE_TYPE_MAIN, "Main Image"),
        (IMAGE_TYPE_GALLERY, "Gallery Image"),
        (IMAGE_TYPE_THUMBNAIL, "Thumbnail Image"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name="images"
    )

    image = models.ImageField(_("image"), upload_to="products/%Y/%m/", max_length=500)

    image_type = models.CharField(
        _("image type"), max_length=20, choices=IMAGE_TYPES, default=IMAGE_TYPE_GALLERY
    )

    alt_text = models.CharField(
        _("alt text"),
        max_length=200,
        blank=True,
        help_text=_("Alternative text for accessibility"),
    )

    order = models.PositiveIntegerField(
        _("display order"), default=0, help_text=_("Order in which images appear")
    )

    is_active = models.BooleanField(_("active"), default=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        db_table = "variant_images"
        verbose_name = _("variant image")
        verbose_name_plural = _("variant images")
        ordering = ["order", "created_at"]
        indexes = [
            models.Index(fields=["variant", "image_type"]),
            models.Index(fields=["order"]),
        ]

    def __str__(self):
        return f"Image for {self.variant.sku}"


class ProductReview(models.Model):
    """Customer reviews for products"""

    RATING_CHOICES = [
        (1, "1 Star"),
        (2, "2 Stars"),
        (3, "3 Stars"),
        (4, "4 Stars"),
        (5, "5 Stars"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="product_reviews"
    )

    rating = models.PositiveIntegerField(
        _("rating"),
        choices=RATING_CHOICES,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )

    title = models.CharField(_("review title"), max_length=200, blank=True)
    comment = models.TextField(_("comment"))

    # Verified purchase
    is_verified_purchase = models.BooleanField(
        _("verified purchase"),
        default=False,
        help_text=_("User purchased this product"),
    )

    # Helpful votes
    helpful_yes = models.PositiveIntegerField(_("helpful yes votes"), default=0)
    helpful_no = models.PositiveIntegerField(_("helpful no votes"), default=0)

    # Moderation
    is_approved = models.BooleanField(_("approved"), default=True)
    is_edited = models.BooleanField(_("edited"), default=False)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "product_reviews"
        verbose_name = _("product review")
        verbose_name_plural = _("product reviews")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["product", "is_approved"]),
            models.Index(fields=["user", "created_at"]),
            models.Index(fields=["rating"]),
        ]
        constraints = [
            # Users can only review a product once
            models.UniqueConstraint(
                fields=["product", "user"], name="unique_product_review"
            ),
        ]

    def __str__(self):
        return f"Review by {self.user.email} for {self.product.title}"

    def save(self, *args, **kwargs):
        """Update product rating cache"""
        is_new = self._state.adding
        super().save(*args, **kwargs)

        # Update product rating cache
        if is_new or not self.is_approved:
            self.update_product_rating()

    def update_product_rating(self):
        """Update product's cached rating"""
        reviews = ProductReview.objects.filter(product=self.product, is_approved=True)

        if reviews.exists():
            avg_rating = reviews.aggregate(avg=models.Avg("rating"))["avg"]
            total = reviews.count()

            self.product.average_rating = round(avg_rating, 2)
            self.product.total_reviews = total
            self.product.save(update_fields=["average_rating", "total_reviews"])


class Wishlist(models.Model):
    """Customer wishlist"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="wishlists")
    variant = models.ForeignKey(
        ProductVariant, on_delete=models.CASCADE, related_name="wishlisted_by"
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        db_table = "wishlists"
        verbose_name = _("wishlist")
        verbose_name_plural = _("wishlists")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "created_at"]),
        ]
        constraints = [
            # Users can only add a variant to wishlist once
            models.UniqueConstraint(
                fields=["user", "variant"], name="unique_wishlist_item"
            ),
        ]

    def __str__(self):
        return f"Wishlist: {self.user.email} - {self.variant.sku}"
