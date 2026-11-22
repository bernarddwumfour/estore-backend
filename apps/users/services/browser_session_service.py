"""Opaque sessions shared across BFF instances without a Redis dependency."""
import hashlib
import secrets
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from apps.users.models.browser_session import BrowserSession


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@transaction.atomic
def create_session(user) -> str:
    # Opportunistically clean this user's expired sessions; no global table scan.
    BrowserSession.objects.filter(user=user, expires_at__lte=timezone.now()).delete()
    token = secrets.token_urlsafe(32)
    BrowserSession.objects.create(digest=digest(token), user=user,
        password_fingerprint=digest(user.password),
        expires_at=timezone.now() + timedelta(days=7))
    return token


def resolve_session(token: str):
    if not isinstance(token, str) or len(token) != 43:
        return None
    session = BrowserSession.objects.select_related("user").filter(
        digest=digest(token), expires_at__gt=timezone.now(), user__is_active=True).first()
    if not session or not constant_time_compare(
        session.password_fingerprint, digest(session.user.password)
    ):
        return None
    return session


def delete_session(token: str) -> None:
    if isinstance(token, str) and len(token) == 43:
        BrowserSession.objects.filter(digest=digest(token)).delete()


def clear_expired_sessions() -> int:
    count, _ = BrowserSession.objects.filter(expires_at__lte=timezone.now()).delete()
    return count
