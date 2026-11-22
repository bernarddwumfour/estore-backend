"""Database-backed sessions for the Next.js BFF. Only a digest is persisted."""
from django.conf import settings
from django.db import models


class BrowserSession(models.Model):
    digest = models.CharField(max_length=64, primary_key=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    password_fingerprint = models.CharField(max_length=64)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
