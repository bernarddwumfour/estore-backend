"""Shared rules for AI and staff control of social conversations."""
from django.conf import settings

from apps.ai_assistant.features import enabled
from apps.social.models import SocialAgentAccount


def ai_available(account_id):
    account = SocialAgentAccount.objects.filter(account_id=account_id).first()
    return bool(settings.ZERNIO_WEBHOOK_SECRET and enabled("guest") and (account.enabled if account else True))
