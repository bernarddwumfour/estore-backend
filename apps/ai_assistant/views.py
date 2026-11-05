
import logging
import time

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from estore.utils.responses import APIResponse

from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
)

from apps.common.logging import (
    log_action,
    LogSeverity,
    get_user_info,
)

from apps.ai_assistant.services.assistant_service import (
    AssistantService,
)

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def assistant_chat(request):
    """
    Send a message to the AI shopping assistant.

    Request body:
    {
        "message": "Find me a laptop under 5000",
        "conversation_id": "optional-uuid"
    }
    """

    start_time = time.time()
    action = "assistant_chat"
    user = request.user

    try:
        data = request.json_data

        message = data.get("message")
        conversation_id = data.get("conversation_id")

        # Validate the message.
        if not isinstance(message, str) or not message.strip():
            return APIResponse.bad_request(
                message="A valid message is required."
            )

        message = message.strip()

        if len(message) > 4000:
            return APIResponse.bad_request(
                message="Message cannot exceed 4000 characters."
            )

        # Process the message through the assistant service.
        result = AssistantService.send_message(
            user=user,
            message=message,
            conversation_id=conversation_id,
        )

        duration = round(time.time() - start_time, 3)

        logger.info(
            "%s completed in %s seconds for user %s",
            action,
            duration,
            user.id,
        )

        return APIResponse.success(
            data=result,
            message="Assistant response generated successfully.",
        )

    except ValueError as exc:
        logger.warning(
            "%s validation error for user %s: %s",
            action,
            user.id,
            str(exc),
        )

        return APIResponse.bad_request(
            message=str(exc)
        )

    except Exception:
        duration = round(time.time() - start_time, 3)

        logger.exception(
            "%s failed for user %s after %s seconds",
            action,
            user.id,
            duration,
        )

        return APIResponse.server_error(
            message="The shopping assistant is temporarily unavailable."
        )
