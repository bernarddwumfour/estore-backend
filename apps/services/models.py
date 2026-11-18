import uuid

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils.text import slugify
from django.conf import settings


class ServiceCategory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL, related_name="children")
    image = models.ImageField(upload_to="service-categories/%Y/%m/", null=True, blank=True)
    is_hidden = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        indexes = [models.Index(fields=["is_active", "is_hidden"])]

    def __str__(self):
        return self.name


class Service(models.Model):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    STATUS_CHOICES = [(DRAFT, "Draft"), (PUBLISHED, "Published"), (ARCHIVED, "Archived")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    short_description = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    category = models.ForeignKey(ServiceCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="services")
    features = models.JSONField(default=list, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DRAFT, db_index=True)
    is_featured = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    meta_title = models.CharField(max_length=200, blank=True)
    meta_description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["sort_order", "-created_at"]
        indexes = [models.Index(fields=["status", "is_featured"]), models.Index(fields=["category", "status"])]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)


class ServiceOption(models.Model):
    FIXED = "fixed"
    FROM = "from"
    QUOTE = "quote"
    PRICING_CHOICES = [(FIXED, "Fixed price"), (FROM, "Starting from"), (QUOTE, "Quote required")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="options")
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140)
    description = models.CharField(max_length=300, blank=True)
    pricing_type = models.CharField(max_length=8, choices=PRICING_CHOICES, default=FIXED)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)])
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(fields=["service", "slug"], name="svc_option_service_slug_uniq"),
            models.UniqueConstraint(fields=["service"], condition=Q(is_default=True), name="svc_one_default_option"),
            models.CheckConstraint(check=Q(price__gte=0) | Q(price__isnull=True), name="svc_option_price_nonnegative"),
            models.CheckConstraint(check=Q(duration_minutes__gt=0) | Q(duration_minutes__isnull=True), name="svc_option_duration_positive"),
        ]

    def __str__(self):
        return f"{self.service}: {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class ServiceImage(models.Model):
    MAIN = "main"
    GALLERY = "gallery"
    THUMBNAIL = "thumbnail"
    IMAGE_TYPES = [(MAIN, "Main"), (GALLERY, "Gallery"), (THUMBNAIL, "Thumbnail")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service = models.ForeignKey(Service, on_delete=models.CASCADE, related_name="images")
    image = models.ImageField(upload_to="services/%Y/%m/")
    image_type = models.CharField(max_length=12, choices=IMAGE_TYPES, default=GALLERY)
    alt_text = models.CharField(max_length=250, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "created_at"]


class ServiceRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    service = models.ForeignKey(Service, null=True, blank=True, on_delete=models.SET_NULL, related_name="requests")
    custom_service_type = models.CharField(max_length=200, blank=True)
    device_model = models.CharField(max_length=200)
    customer_name = models.CharField(max_length=200)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=40)
    issue_description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class BookingSettings(models.Model):
    """The single store schedule and lock used when allocating appointments."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    timezone = models.CharField(max_length=64, default="Africa/Accra")
    slot_interval_minutes = models.PositiveIntegerField(default=30)
    enabled = models.BooleanField(default=False)


class BookingHours(models.Model):
    weekday = models.PositiveSmallIntegerField(unique=True)
    opens_at = models.TimeField()
    closes_at = models.TimeField()
    is_open = models.BooleanField(default=True)


class BookingException(models.Model):
    date = models.DateField(unique=True)
    is_closed = models.BooleanField(default=True)
    opens_at = models.TimeField(null=True, blank=True)
    closes_at = models.TimeField(null=True, blank=True)


class Appointment(models.Model):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    STATUS_CHOICES = [(PENDING, "Pending"), (CONFIRMED, "Confirmed"), (CANCELLED, "Cancelled"), (COMPLETED, "Completed")]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="appointments")
    option = models.ForeignKey(ServiceOption, on_delete=models.PROTECT, related_name="appointments")
    service_title = models.CharField(max_length=200)
    option_name = models.CharField(max_length=120)
    pricing_type = models.CharField(max_length=8)
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    customer_name = models.CharField(max_length=200)
    customer_phone = models.CharField(max_length=40)
    starts_at = models.DateTimeField(db_index=True)
    ends_at = models.DateTimeField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-starts_at"]

