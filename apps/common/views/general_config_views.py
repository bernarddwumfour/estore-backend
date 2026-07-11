"""
General config views — admin endpoint for store-wide settings.
"""

import json
import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.common.logging import log_action, LogSeverity
from apps.common.models import GeneralConfig
from apps.common.schemas import (
    serialize_general_config,
    validate_general_config_update,
)
from apps.users.decorators.auth import jwt_required, role_required
from estore.utils.responses import APIResponse

logger = logging.getLogger(__name__)
APP_NAME = "common"


@csrf_exempt
@require_http_methods(["GET", "POST"])
@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_general_config(request):
    """Admin: read or update the store-wide general configuration."""
    try:
        config = GeneralConfig.get()

        if request.method == "POST":
            try:
                payload = json.loads(request.body or b"{}")
            except ValueError:
                return APIResponse.bad_request("Invalid JSON body")

            cleaned, errors = validate_general_config_update(payload)
            if errors:
                return APIResponse.validation_error(errors)

            for field, value in cleaned.items():
                setattr(config, field, value)
            config.save()

            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action="general_config_update",
                description="General store configuration updated",
                status_code=200,
                user=request.user,
                request=request,
                app_name=APP_NAME,
                extra={"updated_fields": sorted(cleaned.keys())},
            )

        return APIResponse.success(
            data=serialize_general_config(config),
            message="General configuration retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin general config error: {str(e)}")
        return APIResponse.server_error()
