"""
Marketing services — campaign write logic.
"""

import logging
from typing import Dict, Optional, Tuple

from django.db import transaction
from django.utils import timezone

from apps.marketing.models import EmailCampaign
from apps.marketing.selectors import get_segment_queryset
from estore.utils.email_service import email_service

logger = logging.getLogger(__name__)


class CampaignService:
    """Campaign business logic - all writes go through here."""

    @staticmethod
    def create_campaign(data: Dict, user) -> Tuple[Optional[EmailCampaign], Optional[Dict]]:
        try:
            campaign = EmailCampaign.objects.create(
                name=data["name"],
                subject=data["subject"],
                preheader=data.get("preheader", ""),
                html_body=data["html_body"],
                text_body=data.get("text_body", ""),
                campaign_type=data.get("campaign_type", EmailCampaign.TYPE_CUSTOM),
                segment=data.get("segment", EmailCampaign.SEGMENT_ALL_USERS),
                created_by=user,
            )
            return campaign, None
        except Exception:
            logger.exception("Campaign create error")
            return None, {"general": "Failed to create campaign"}

    @staticmethod
    def update_campaign(
        campaign: EmailCampaign, data: Dict
    ) -> Tuple[Optional[EmailCampaign], Optional[Dict]]:
        if campaign.status != EmailCampaign.STATUS_DRAFT:
            return None, {"status": "Only draft campaigns can be edited"}

        try:
            for field in (
                "name",
                "subject",
                "preheader",
                "html_body",
                "text_body",
                "campaign_type",
                "segment",
            ):
                if field in data:
                    setattr(campaign, field, data[field])
            campaign.save()
            return campaign, None
        except Exception:
            logger.exception("Campaign update error")
            return None, {"general": "Failed to update campaign"}

    @staticmethod
    def send_test(campaign: EmailCampaign, email: str) -> Tuple[bool, Optional[Dict]]:
        """Send the campaign to a single address for review. Synchronous."""
        sent = email_service.send(
            recipient_email=email,
            subject=f"[TEST] {campaign.subject}",
            message_text=campaign.text_body or campaign.subject,
            html_message=campaign.html_body,
        )
        if not sent:
            return False, {"email": "Failed to send test email"}
        return True, None

    @staticmethod
    def initiate_send(campaign_id: str) -> Tuple[Optional[EmailCampaign], Optional[Dict]]:
        """
        Move a campaign to 'sending' and enqueue the bulk send task.

        Row-locked so two concurrent send requests cannot both enqueue; the
        task itself re-checks status as a second guard.
        """
        from apps.marketing.tasks import send_campaign_task

        try:
            with transaction.atomic():
                campaign = (
                    EmailCampaign.objects.select_for_update().get(id=campaign_id)
                )

                if campaign.status not in (
                    EmailCampaign.STATUS_DRAFT,
                    EmailCampaign.STATUS_FAILED,
                ):
                    return None, {
                        "status": f"Campaign cannot be sent from status '{campaign.status}'"
                    }

                recipients = get_segment_queryset(
                    campaign.segment, campaign.campaign_type
                )
                total = recipients.count()
                if total == 0:
                    return None, {"segment": "The selected segment has no recipients"}

                campaign.status = EmailCampaign.STATUS_SENDING
                campaign.total_recipients = total
                campaign.sent_count = 0
                campaign.failed_count = 0
                campaign.error_sample = []
                campaign.save(
                    update_fields=[
                        "status",
                        "total_recipients",
                        "sent_count",
                        "failed_count",
                        "error_sample",
                        "updated_at",
                    ]
                )

                # Enqueue only after the 'sending' row is committed so the
                # worker (or eager execution) never sees a stale status.
                transaction.on_commit(
                    lambda: send_campaign_task.delay(str(campaign.id))
                )

            campaign.refresh_from_db()
            return campaign, None
        except EmailCampaign.DoesNotExist:
            return None, {"campaign": "Campaign not found"}
        except Exception:
            logger.exception("Campaign send initiation error")
            return None, {"general": "Failed to start campaign send"}
