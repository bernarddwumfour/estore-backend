"""Cross-process inbox change notifications backed by the store database."""
import logging
from django.db import transaction
from django.db.models import F

from apps.social.models import SocialInboxRevision

logger = logging.getLogger(__name__)


def publish_inbox_change():
    try:
        with transaction.atomic():
            SocialInboxRevision.objects.get_or_create(pk=1)
            SocialInboxRevision.objects.filter(pk=1).update(revision=F("revision") + 1)
    except Exception:
        logger.exception("Unable to notify social inbox subscribers")
