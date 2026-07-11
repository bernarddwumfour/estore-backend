"""
Marketing views — admin API endpoints for email campaigns.
"""

import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.common.logging import log_action, LogSeverity
from apps.marketing.models import EmailCampaign
from apps.marketing.schemas import (
    serialize_campaign,
    serialize_campaign_list,
    validate_campaign_upsert,
    validate_test_send,
)
from apps.marketing.selectors import (
    get_admin_campaigns,
    get_campaign_by_id,
    get_segment_counts,
)
from apps.marketing.services import CampaignService
from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
    role_required,
)
from estore.utils.responses import APIResponse

logger = logging.getLogger(__name__)
APP_NAME = "marketing"


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_campaign_list(request):
    """Admin: list campaigns with filters and pagination."""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        status = request.GET.get("status") or None
        campaign_type = request.GET.get("campaign_type") or None
        search = request.GET.get("search") or None

        campaigns, total, pagination_meta = get_admin_campaigns(
            page=page,
            limit=limit,
            status=status,
            campaign_type=campaign_type,
            search=search,
        )

        return APIResponse.success(
            data={
                "campaigns": serialize_campaign_list(campaigns),
                "total": total,
                "pagination": pagination_meta,
            },
            message="Campaigns retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin campaign list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='60/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_campaign_create(request):
    """Admin: create a draft campaign."""
    try:
        cleaned, errors = validate_campaign_upsert(request.json_data, partial=False)
        if errors:
            return APIResponse.validation_error(errors)

        campaign, error = CampaignService.create_campaign(cleaned, request.user)
        if error:
            return APIResponse.validation_error(error)

        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action="campaign_create",
            description=f"Campaign '{campaign.name}' created",
            status_code=201,
            user=request.user,
            request=request,
            app_name=APP_NAME,
            extra={"campaign_id": str(campaign.id)},
        )
        return APIResponse.created(
            data=serialize_campaign(campaign),
            message="Campaign created successfully",
        )
    except Exception as e:
        logger.error(f"Admin campaign create error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_campaign_segments(request):
    """Admin: segment keys, labels and live recipient counts."""
    try:
        campaign_type = request.GET.get("campaign_type") or None
        counts = get_segment_counts(campaign_type)
        segments = [
            {"value": value, "label": label, "recipients": counts.get(value, 0)}
            for value, label in EmailCampaign.SEGMENT_CHOICES
        ]
        return APIResponse.success(
            data={"segments": segments},
            message="Segments retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin campaign segments error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_campaign_detail(request, campaign_id):
    """Admin: full campaign detail including body."""
    try:
        campaign = get_campaign_by_id(campaign_id)
        if not campaign:
            return APIResponse.not_found("Campaign not found")
        return APIResponse.success(
            data=serialize_campaign(campaign),
            message="Campaign retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin campaign detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PUT", "PATCH"])
@ratelimit(key='ip', rate='60/h', method='PUT', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_campaign_update(request, campaign_id):
    """Admin: update a draft campaign."""
    try:
        campaign = get_campaign_by_id(campaign_id)
        if not campaign:
            return APIResponse.not_found("Campaign not found")

        cleaned, errors = validate_campaign_upsert(request.json_data, partial=True)
        if errors:
            return APIResponse.validation_error(errors)

        campaign, error = CampaignService.update_campaign(campaign, cleaned)
        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data=serialize_campaign(campaign),
            message="Campaign updated successfully",
        )
    except Exception as e:
        logger.error(f"Admin campaign update error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='30/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_campaign_test_send(request, campaign_id):
    """Admin: send the campaign to a single email for review."""
    try:
        campaign = get_campaign_by_id(campaign_id)
        if not campaign:
            return APIResponse.not_found("Campaign not found")

        cleaned, errors = validate_test_send(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)

        sent, error = CampaignService.send_test(campaign, cleaned["email"])
        if error:
            return APIResponse.validation_error(error)

        return APIResponse.success(
            data={"email": cleaned["email"]},
            message="Test email sent",
        )
    except Exception as e:
        logger.error(f"Admin campaign test send error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='30/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_campaign_send(request, campaign_id):
    """Admin: send the campaign to its segment now."""
    try:
        campaign, error = CampaignService.initiate_send(campaign_id)
        if error:
            if "campaign" in error:
                return APIResponse.not_found("Campaign not found")
            return APIResponse.validation_error(error)

        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action="campaign_send",
            description=(
                f"Campaign '{campaign.name}' send started "
                f"({campaign.total_recipients} recipients)"
            ),
            status_code=200,
            user=request.user,
            request=request,
            app_name=APP_NAME,
            extra={
                "campaign_id": str(campaign.id),
                "segment": campaign.segment,
                "total_recipients": campaign.total_recipients,
            },
        )
        return APIResponse.success(
            data=serialize_campaign(campaign),
            message="Campaign send started",
        )
    except Exception as e:
        logger.error(f"Admin campaign send error: {str(e)}")
        return APIResponse.server_error()
