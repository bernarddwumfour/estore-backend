
import logging
import time

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from estore.utils.responses import APIResponse

from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
    jwt_optional,
    role_required,
)
from apps.ai_assistant.services.admin_assistant_service import AdminAssistantService
from apps.ai_assistant.services.admin_product_action_service import AdminProductActionService
from apps.ai_assistant.services.admin_user_action_service import AdminUserActionService
from apps.ai_assistant.services.admin_marketing_action_service import AdminMarketingActionService

from apps.common.logging import (
    log_action,
    LogSeverity,
    get_user_info,
)

from apps.ai_assistant.services.assistant_service import (
    AssistantService,
)
from apps.ai_assistant.services.order_draft_service import AssistantOrderDraftService
from apps.orders.schemas import serialize_order
from apps.orders.paystack_service import PaystackService

logger = logging.getLogger(__name__)


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def confirm_admin_marketing_action(request, action_id):
    try:
        result, errors = AdminMarketingActionService.confirm(request.user, action_id)
        if errors:
            return APIResponse.bad_request("Marketing action could not be confirmed", errors)
        return APIResponse.success(data={"result": result}, message="Marketing action completed")
    except Exception:
        logger.exception("Admin marketing action failed for user %s", request.user.pk)
        return APIResponse.server_error("Marketing action failed")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def prepare_admin_marketing_action(request):
    data = request.json_data
    try:
        pending, errors = AdminMarketingActionService.prepare(
            request.user,
            entity=data.get("entity"),
            action=data.get("action"),
            ids=data.get("ids"),
            review_type=data.get("review_type"),
        )
        if errors:
            return APIResponse.bad_request("Marketing action could not be prepared", errors)
        return APIResponse.success(data={"pending_action": pending}, message="Review the marketing action")
    except Exception:
        logger.exception("Admin marketing action preparation failed for user %s", request.user.pk)
        return APIResponse.server_error("Marketing action could not be prepared")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def prepare_admin_product_bulk_action(request):
    """Prepare a selected-product action for a separate confirmation request."""
    ids = request.json_data.get("ids")
    action = request.json_data.get("action")
    if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
        return APIResponse.bad_request("A list of product IDs is required.")
    if not isinstance(action, str):
        return APIResponse.bad_request("A product action is required.")
    try:
        pending, errors = AdminProductActionService.prepare(
            request.user, "bulk_products", {"ids": ids, "bulk_action": action}
        )
        if errors:
            return APIResponse.bad_request("Product action could not be prepared", errors)
        return APIResponse.success(data={"pending_action": pending}, message="Review the selected product action")
    except Exception:
        logger.exception("Admin product action preparation failed for user %s", request.user.pk)
        return APIResponse.server_error("Product action could not be prepared")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def confirm_admin_product_action(request, action_id):
    """Execute one pending product action after an explicit staff request."""
    try:
        result, errors = AdminProductActionService.confirm(request.user, action_id)
        if errors:
            return APIResponse.bad_request("Product action could not be confirmed", errors)
        return APIResponse.success(data={"result": result}, message="Product action completed")
    except Exception:
        logger.exception("Admin product action failed for user %s", request.user.pk)
        return APIResponse.server_error("Product action failed")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin")
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def confirm_admin_user_action(request, action_id):
    """Confirm a pending user management action as an administrator."""
    try:
        result, errors = AdminUserActionService.confirm(request.user, action_id)
        if errors:
            return APIResponse.bad_request("User action could not be confirmed", errors)
        return APIResponse.success(data={"result": result}, message="User action completed")
    except Exception:
        logger.exception("Admin user action failed for user %s", request.user.pk)
        return APIResponse.server_error("User action failed")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@json_request_required
@ratelimit(key="user", rate="30/h", method="POST", block=True)
def admin_assistant_chat(request):
    """Answer a staff catalog question using only read-only admin tools."""
    message = request.json_data.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        return APIResponse.bad_request("A message of 1 to 4000 characters is required.")
    history = request.json_data.get("history", [])
    if (not isinstance(history, list) or len(history) > 12 or
            any(not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}
                or not isinstance(item.get("text"), str) or len(item["text"]) > 4000
                for item in history)):
        return APIResponse.bad_request("Invalid conversation history.")
    media_ids = request.json_data.get("media_ids", [])
    if (not isinstance(media_ids, list) or len(media_ids) > 10 or
            any(not isinstance(value, str) or not value for value in media_ids) or
            len(set(media_ids)) != len(media_ids)):
        return APIResponse.bad_request("Choose up to 10 distinct attached images.")
    try:
        result = AdminAssistantService.send_message(request.user, message, history, media_ids)
        return APIResponse.success(data=result)
    except ValueError as exc:
        return APIResponse.bad_request(str(exc))
    except Exception:
        logger.exception("Admin assistant failed for user %s", request.user.pk)
        return APIResponse.server_error("The admin assistant is temporarily unavailable.")


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


@csrf_exempt
@require_http_methods(["POST"])
@jwt_optional
@json_request_required
@ratelimit(key="ip", rate="20/h", method="POST", block=True)
def guest_assistant_chat(request):
    """Public, read-only shopping chat. Guest history is supplied by the client and not persisted."""
    data = request.json_data
    message = data.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        return APIResponse.bad_request("A message of 1 to 4000 characters is required.")
    history = data.get("history", [])
    if (not isinstance(history, list) or len(history) > 12 or
            any(not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}
                or not isinstance(item.get("content"), str) or len(item["content"]) > 4000
                for item in history)):
        return APIResponse.bad_request("Invalid guest conversation history.")
    try:
        result = AssistantService.send_guest_message(message, history)
        return APIResponse.success(data=result)
    except ValueError as exc:
        return APIResponse.bad_request(str(exc))
    except Exception:
        logger.exception("Guest assistant request failed")
        return APIResponse.server_error("The shopping assistant is temporarily unavailable.")


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@json_request_required
@ratelimit(key="user", rate="10/h", method="POST", block=True)
def confirm_assistant_order(request, draft_id):
    """Create an order only after the customer confirms a prepared draft."""
    data = request.json_data
    token = data.get("confirmation_token")
    payment_method = data.get("payment_method")
    shipping_method = data.get("shipping_method", "")
    if not isinstance(token, str) or payment_method not in {"pod", "paystack"}:
        return APIResponse.bad_request("A valid confirmation and payment method are required.")

    order, error = AssistantOrderDraftService.confirm(
        request.user, draft_id, token, payment_method, shipping_method
    )
    if error:
        return APIResponse.validation_error(error)

    data = {"order": serialize_order(order, is_admin=False), "payment_method": payment_method}
    if payment_method == "paystack":
        payment, pay_error = PaystackService.initialize_transaction(order)
        if pay_error:
            return APIResponse.validation_error({"payment": pay_error})
        data["payment"] = payment
    return APIResponse.created(data=data, message="Order created. Complete payment to finish checkout." if payment_method == "paystack" else "Order confirmed successfully.")
