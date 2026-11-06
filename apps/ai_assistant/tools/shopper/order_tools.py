import json
from uuid import UUID

from django.contrib.auth import get_user_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.ai_assistant.services.order_draft_service import AssistantOrderDraftService
User = get_user_model()


class PrepareOrderInput(BaseModel):
    items: list[dict] = Field(
        description="One or more verified product variants. Each item has variant_id (UUID) and quantity (1-10).",
        min_length=1,
        max_length=10,
    )


@tool(args_schema=PrepareOrderInput)
def prepare_order(items: list[dict], config: RunnableConfig) -> str:
    """Prepare an order review for one or more verified in-stock variants. Never places an order."""
    user_id = config.get("configurable", {}).get("authenticated_user_id")
    if not user_id:
        return json.dumps({"success": False, "requires_authentication": True, "error": "Sign in to prepare an order."})
    try:
        for item in items:
            UUID(str(item.get("variant_id", "")))
            if not isinstance(item.get("quantity", 1), int) or not 1 <= item.get("quantity", 1) <= 10:
                raise ValueError("Invalid quantity")
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if not user:
            return json.dumps({"success": False, "requires_authentication": True, "error": "Sign in to prepare an order."})
        draft, error = AssistantOrderDraftService.prepare(user, items)
        return json.dumps({"success": not bool(error), "draft": draft} if not error else {"success": False, **error})
    except (ValueError, TypeError):
        return json.dumps({"success": False, "error": "Invalid product variant."})
