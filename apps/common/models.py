"""
Common models for system-wide features
"""

import uuid
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
    path = models.CharField(_("request path"), max_length=500, blank=True)
    method = models.CharField(_("HTTP method"), max_length=10, blank=True)
    
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