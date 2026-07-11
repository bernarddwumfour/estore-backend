"""
Marketing background tasks (Celery). Runs eagerly (inline) when no broker
is configured — see the CELERY_TASK_ALWAYS_EAGER fallback in settings.
"""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from estore.utils.email_service import email_service

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=0)
def send_campaign_task(self, campaign_id: str):
    """Bulk-send a campaign to its snapshotted segment."""
    from apps.marketing.models import EmailCampaign
    from apps.marketing.selectors import get_segment_queryset

    # Claim the campaign: only proceed if it is in 'sending' (double-send guard).
    with transaction.atomic():
        try:
            campaign = EmailCampaign.objects.select_for_update().get(id=campaign_id)
        except EmailCampaign.DoesNotExist:
            logger.error(f"send_campaign_task: campaign {campaign_id} not found")
            return

        if campaign.status != EmailCampaign.STATUS_SENDING:
            logger.warning(
                f"send_campaign_task: campaign {campaign_id} in status "
                f"'{campaign.status}', expected 'sending' — skipping"
            )
            return

    recipients = get_segment_queryset(campaign.segment, campaign.campaign_type)

    messages = []
    for user in recipients.iterator():
        messages.append(
            {
                "to": user.email,
                "subject": campaign.subject,
                "html": campaign.html_body,
                "text": campaign.text_body or None,
            }
        )

    sent_count, failed_count, error_sample = email_service.send_batch(messages)

    if failed_count == 0:
        status = EmailCampaign.STATUS_SENT
    elif sent_count == 0:
        status = EmailCampaign.STATUS_FAILED
    else:
        status = EmailCampaign.STATUS_PARTIALLY_SENT

    EmailCampaign.objects.filter(id=campaign.id).update(
        status=status,
        sent_count=sent_count,
        failed_count=failed_count,
        error_sample=error_sample,
        sent_at=timezone.now(),
        updated_at=timezone.now(),
    )
    logger.info(
        f"Campaign {campaign.id} finished: {status} "
        f"(sent={sent_count}, failed={failed_count})"
    )
