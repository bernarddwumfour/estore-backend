import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class EmailCampaign(models.Model):
    """An admin-composed email sent in bulk to a user segment."""

    TYPE_NEWSLETTER = "newsletter"
    TYPE_PROMOTION = "promotion"
    TYPE_ANNOUNCEMENT = "announcement"
    TYPE_CUSTOM = "custom"

    TYPE_CHOICES = [
        (TYPE_NEWSLETTER, "Newsletter"),
        (TYPE_PROMOTION, "Promotion"),
        (TYPE_ANNOUNCEMENT, "Announcement"),
        (TYPE_CUSTOM, "Custom"),
    ]

    SEGMENT_ALL_USERS = "all_users"
    SEGMENT_CUSTOMERS = "customers"
    SEGMENT_VERIFIED_CUSTOMERS = "verified_customers"
    SEGMENT_AFFILIATES = "affiliates"
    SEGMENT_NEWSLETTER_SUBSCRIBERS = "newsletter_subscribers"
    SEGMENT_MARKETING_OPTIN = "marketing_optin"

    SEGMENT_CHOICES = [
        (SEGMENT_ALL_USERS, "All Users"),
        (SEGMENT_CUSTOMERS, "Customers"),
        (SEGMENT_VERIFIED_CUSTOMERS, "Verified Customers"),
        (SEGMENT_AFFILIATES, "Affiliates"),
        (SEGMENT_NEWSLETTER_SUBSCRIBERS, "Newsletter Subscribers"),
        (SEGMENT_MARKETING_OPTIN, "Marketing Opt-in"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_SENDING = "sending"
    STATUS_SENT = "sent"
    STATUS_PARTIALLY_SENT = "partially_sent"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENDING, "Sending"),
        (STATUS_SENT, "Sent"),
        (STATUS_PARTIALLY_SENT, "Partially Sent"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    name = models.CharField(_("name"), max_length=200)
    subject = models.CharField(_("subject"), max_length=255)
    preheader = models.CharField(_("preheader"), max_length=255, blank=True)
    html_body = models.TextField(_("HTML body"))
    text_body = models.TextField(_("text body"), blank=True)

    campaign_type = models.CharField(
        _("campaign type"),
        max_length=20,
        choices=TYPE_CHOICES,
        default=TYPE_CUSTOM,
        db_index=True,
    )
    segment = models.CharField(
        _("segment"),
        max_length=30,
        choices=SEGMENT_CHOICES,
        default=SEGMENT_ALL_USERS,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_DRAFT,
        db_index=True,
    )

    total_recipients = models.PositiveIntegerField(_("total recipients"), default=0)
    sent_count = models.PositiveIntegerField(_("sent count"), default=0)
    failed_count = models.PositiveIntegerField(_("failed count"), default=0)
    error_sample = models.JSONField(_("error sample"), default=list, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="email_campaigns",
    )

    created_at = models.DateTimeField(_("created at"), auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(_("updated at"), auto_now=True)
    sent_at = models.DateTimeField(_("sent at"), null=True, blank=True)

    class Meta:
        db_table = "email_campaigns"
        verbose_name = _("email campaign")
        verbose_name_plural = _("email campaigns")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"]),
            models.Index(fields=["campaign_type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.get_status_display()})"
