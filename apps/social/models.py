import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class SocialPost(models.Model):
    """A social-media post managed through Zernio.

    Rows are created either by an admin composing a post in the dashboard
    (source=manual) or automatically when a product is published / a
    promotion is activated (source=product/promotion). Auto-created rows
    start in pending_approval and reach Zernio only when an admin approves.
    """

    SOURCE_MANUAL = "manual"
    SOURCE_PRODUCT = "product"
    SOURCE_PROMOTION = "promotion"

    SOURCE_CHOICES = [
        (SOURCE_MANUAL, "Manual"),
        (SOURCE_PRODUCT, "Product"),
        (SOURCE_PROMOTION, "Promotion"),
    ]

    STATUS_PENDING_APPROVAL = "pending_approval"
    STATUS_SENT = "sent"
    STATUS_REJECTED = "rejected"
    STATUS_FAILED = "failed"
    STATUS_SKIPPED = "skipped"

    STATUS_CHOICES = [
        (STATUS_PENDING_APPROVAL, "Pending Approval"),
        (STATUS_SENT, "Sent"),
        (STATUS_REJECTED, "Rejected"),
        (STATUS_FAILED, "Failed"),
        (STATUS_SKIPPED, "Skipped"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    source = models.CharField(
        _("source"),
        max_length=20,
        choices=SOURCE_CHOICES,
        default=SOURCE_MANUAL,
        db_index=True,
    )
    object_id = models.UUIDField(_("source object id"), null=True, blank=True)

    caption = models.TextField(_("caption"))
    image_url = models.URLField(_("image URL"), max_length=500, blank=True)
    # Canonical media payload sent to Zernio: [{"type": "image|video", "url": ..., "title": ...}]
    media_items = models.JSONField(_("media items"), default=list, blank=True)
    # List of {"platform": ..., "accountId": ...} dicts sent to Zernio
    platforms = models.JSONField(_("platforms"), default=list, blank=True)

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING_APPROVAL,
        db_index=True,
    )
    zernio_post_id = models.CharField(
        _("Zernio post id"), max_length=100, blank=True, db_index=True
    )
    scheduled_for = models.DateTimeField(_("scheduled for"), null=True, blank=True)
    # Internal diagnostics only — never returned to API clients verbatim
    error = models.CharField(_("error"), max_length=255, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="social_posts",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_social_posts",
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)

    class Meta:
        db_table = "social_posts"
        verbose_name = _("social post")
        verbose_name_plural = _("social posts")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["source", "object_id"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.get_source_display()} post ({self.get_status_display()})"

class SocialConfig(models.Model):
    """Singleton runtime configuration for the social integration.

    mode=test simulates Zernio locally (sandbox models below) so the whole
    posting/inbox flow can be exercised without a connected account;
    mode=live calls the real Zernio API.
    """

    MODE_LIVE = "live"
    MODE_TEST = "test"

    MODE_CHOICES = [
        (MODE_LIVE, "Live"),
        (MODE_TEST, "Test"),
    ]

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    mode = models.CharField(
        _("mode"), max_length=10, choices=MODE_CHOICES, default=MODE_LIVE
    )
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "social_config"
        verbose_name = _("social config")
        verbose_name_plural = _("social config")

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get(cls) -> "SocialConfig":
        config, _created = cls.objects.get_or_create(pk=1)
        return config

    @classmethod
    def test_mode_active(cls) -> bool:
        return cls.objects.filter(pk=1, mode=cls.MODE_TEST).exists()

    def __str__(self):
        return f"Social config ({self.mode})"


class SandboxComment(models.Model):
    """Simulated comment on a post, used only in test mode."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    zernio_post_id = models.CharField(_("post id"), max_length=100, db_index=True)
    author = models.CharField(_("author"), max_length=100)
    message = models.TextField(_("message"))
    is_reply = models.BooleanField(_("is admin reply"), default=False)
    hidden = models.BooleanField(_("hidden"), default=False)
    liked = models.BooleanField(_("liked"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        db_table = "social_sandbox_comments"
        ordering = ["created_at"]

    def __str__(self):
        return f"Sandbox comment by {self.author}"


class SandboxConversation(models.Model):
    """Simulated DM conversation, used only in test mode."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=100)
    platform = models.CharField(_("platform"), max_length=30)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        db_table = "social_sandbox_conversations"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Sandbox conversation with {self.name}"


class SandboxMessage(models.Model):
    """Simulated DM message, used only in test mode."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.ForeignKey(
        SandboxConversation, on_delete=models.CASCADE, related_name="messages"
    )
    message = models.TextField(_("message"))
    is_outgoing = models.BooleanField(_("outgoing"), default=False)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        db_table = "social_sandbox_messages"
        ordering = ["created_at"]

    def __str__(self):
        return f"Sandbox message in {self.conversation_id}"


class SandboxProfile(models.Model):
    """Simulated Zernio profile (workspace grouping accounts), test mode only."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=100)
    description = models.CharField(_("description"), max_length=255, blank=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "social_sandbox_profiles"
        ordering = ["created_at"]

    def __str__(self):
        return f"Sandbox profile {self.name}"


class SandboxAccount(models.Model):
    """Simulated connected social account, test mode only."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    platform = models.CharField(_("platform"), max_length=30)
    name = models.CharField(_("name"), max_length=100)
    profile = models.ForeignKey(
        SandboxProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="accounts",
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)

    class Meta:
        db_table = "social_sandbox_accounts"
        ordering = ["created_at"]

    def __str__(self):
        return f"Sandbox account {self.platform}/{self.name}"


def _social_media_storage():
    """Raw Cloudinary storage serves both images and videos; falls back to
    the default storage when cloudinary isn't installed (dev/tests)."""
    try:
        from cloudinary_storage.storage import RawMediaCloudinaryStorage
        return RawMediaCloudinaryStorage()
    except ImportError:
        from django.core.files.storage import default_storage
        return default_storage


class SocialMedia(models.Model):
    """Uploaded media library for social posts (images and videos)."""

    TYPE_IMAGE = "image"
    TYPE_VIDEO = "video"

    TYPE_CHOICES = [
        (TYPE_IMAGE, "Image"),
        (TYPE_VIDEO, "Video"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(
        _("file"),
        upload_to="social/%Y/%m/",
        max_length=500,
        storage=_social_media_storage,
    )
    media_type = models.CharField(
        _("media type"), max_length=10, choices=TYPE_CHOICES, default=TYPE_IMAGE, db_index=True
    )
    name = models.CharField(_("name"), max_length=200)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="social_media_uploads",
    )
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)

    class Meta:
        db_table = "social_media_library"
        verbose_name = _("social media file")
        verbose_name_plural = _("social media files")
        ordering = ["-created_at"]

    @property
    def url(self) -> str:
        try:
            return self.file.url
        except Exception:
            return ""

    def __str__(self):
        return f"{self.get_media_type_display()}: {self.name}"
