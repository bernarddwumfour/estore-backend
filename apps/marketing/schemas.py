"""
Marketing schemas — request validation and serialization for campaigns.
"""

import re
from typing import Dict, Tuple

from apps.marketing.models import EmailCampaign

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

VALID_TYPES = {choice for choice, _ in EmailCampaign.TYPE_CHOICES}
VALID_SEGMENTS = {choice for choice, _ in EmailCampaign.SEGMENT_CHOICES}


def validate_campaign_upsert(data: Dict, partial: bool = False) -> Tuple[Dict, Dict]:
    errors = {}
    cleaned = {}

    def require(field, max_length=None):
        value = data.get(field)
        if value is None or (isinstance(value, str) and not value.strip()):
            if not partial:
                errors[field] = f"{field.replace('_', ' ').capitalize()} is required"
            elif field in data:
                errors[field] = f"{field.replace('_', ' ').capitalize()} cannot be empty"
            return
        if not isinstance(value, str):
            errors[field] = f"{field.replace('_', ' ').capitalize()} must be a string"
            return
        value = value.strip()
        if max_length and len(value) > max_length:
            value = value[:max_length]
        cleaned[field] = value

    require("name", max_length=200)
    require("subject", max_length=255)
    require("html_body")

    if "preheader" in data:
        preheader = data.get("preheader") or ""
        if not isinstance(preheader, str):
            errors["preheader"] = "Preheader must be a string"
        else:
            cleaned["preheader"] = preheader.strip()[:255]

    if "text_body" in data:
        text_body = data.get("text_body") or ""
        if not isinstance(text_body, str):
            errors["text_body"] = "Text body must be a string"
        else:
            cleaned["text_body"] = text_body

    campaign_type = data.get("campaign_type")
    if campaign_type is not None:
        if campaign_type not in VALID_TYPES:
            errors["campaign_type"] = (
                f"Invalid campaign type. Must be one of: {', '.join(sorted(VALID_TYPES))}"
            )
        else:
            cleaned["campaign_type"] = campaign_type
    elif not partial:
        cleaned["campaign_type"] = EmailCampaign.TYPE_CUSTOM

    segment = data.get("segment")
    if segment is not None:
        if segment not in VALID_SEGMENTS:
            errors["segment"] = (
                f"Invalid segment. Must be one of: {', '.join(sorted(VALID_SEGMENTS))}"
            )
        else:
            cleaned["segment"] = segment
    elif not partial:
        cleaned["segment"] = EmailCampaign.SEGMENT_ALL_USERS

    return cleaned, errors


def validate_test_send(data: Dict) -> Tuple[Dict, Dict]:
    errors = {}
    cleaned = {}

    email = data.get("email")
    if not email or not isinstance(email, str) or not EMAIL_RE.match(email.strip()):
        errors["email"] = "A valid email address is required"
    else:
        cleaned["email"] = email.strip()

    return cleaned, errors


def serialize_campaign(campaign: EmailCampaign, include_body: bool = True) -> Dict:
    data = {
        "id": str(campaign.id),
        "name": campaign.name,
        "subject": campaign.subject,
        "preheader": campaign.preheader,
        "campaign_type": campaign.campaign_type,
        "segment": campaign.segment,
        "status": campaign.status,
        "total_recipients": campaign.total_recipients,
        "sent_count": campaign.sent_count,
        "failed_count": campaign.failed_count,
        "error_sample": campaign.error_sample,
        "created_by": campaign.created_by.email if campaign.created_by else None,
        "created_at": campaign.created_at.isoformat() if campaign.created_at else None,
        "updated_at": campaign.updated_at.isoformat() if campaign.updated_at else None,
        "sent_at": campaign.sent_at.isoformat() if campaign.sent_at else None,
    }
    if include_body:
        data["html_body"] = campaign.html_body
        data["text_body"] = campaign.text_body
    return data


def serialize_campaign_list(campaigns) -> list:
    return [serialize_campaign(c, include_body=False) for c in campaigns]
