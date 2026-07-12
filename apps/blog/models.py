"""Blog models — categories and posts with flexible authorship."""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class BlogCategory(models.Model):
    """Taxonomy for blog posts.  Categories only — no tags (per agreed plan)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(_("name"), max_length=120, unique=True)
    slug = models.SlugField(_("slug"), max_length=140, unique=True)
    description = models.TextField(_("description"), blank=True)
    is_active = models.BooleanField(_("active"), default=True, db_index=True)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "blog_categories"
        verbose_name = _("blog category")
        verbose_name_plural = _("blog categories")
        ordering = ["name"]
        indexes = [models.Index(fields=["slug"])]

    def __str__(self):
        return self.name


class BlogPost(models.Model):
    """A blog post with flexible authorship and draft/published/archived states."""

    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_ARCHIVED = "archived"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_PUBLISHED, "Published"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(_("title"), max_length=200)
    slug = models.SlugField(_("slug"), max_length=220, unique=True)
    excerpt = models.CharField(_("excerpt"), max_length=300, blank=True)
    content = models.TextField(_("content"))  # HTML produced by the admin editor

    # Cover image — stores a URL picked via the social MediaPicker component.
    cover_image_url = models.URLField(_("cover image URL"), max_length=500, blank=True)

    category = models.ForeignKey(
        BlogCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="posts",
        verbose_name=_("category"),
    )

    # Flexible authorship: a registered user OR a free-text display name.
    # At least one must be set (enforced in the schema, not the DB).
    author_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="blog_posts",
        verbose_name=_("author user"),
    )
    author_name = models.CharField(
        _("author name"), max_length=120, blank=True,
        help_text=_("Used when the author is not a registered user."),
    )

    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField(_("published at"), null=True, blank=True)
    is_featured = models.BooleanField(_("featured"), default=False, db_index=True)

    # SEO metadata
    meta_title = models.CharField(_("meta title"), max_length=200, blank=True)
    meta_description = models.TextField(_("meta description"), blank=True)

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)

    class Meta:
        db_table = "blog_posts"
        verbose_name = _("blog post")
        verbose_name_plural = _("blog posts")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status", "-published_at"]),
            models.Index(fields=["is_featured", "-published_at"]),
        ]

    def save(self, *args, **kwargs):
        # Auto-set published_at the first time status transitions to published.
        # The service layer also handles this explicitly — this is a safety net.
        if self.status == self.STATUS_PUBLISHED and not self.published_at:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def author_display_name(self) -> str:
        """Human-readable author name for public display.

        The selector MUST use select_related('author_user') to avoid N+1 queries
        when calling this on a list of posts.
        """
        if self.author_user_id:
            full = f"{self.author_user.first_name} {self.author_user.last_name}".strip()
            return full or self.author_user.email
        return self.author_name or "Unknown"

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"
