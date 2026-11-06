import json
from uuid import UUID

from django.contrib.auth import get_user_model
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from apps.ai_assistant.services.order_draft_service import AssistantOrderDraftService
User = get_user_model()


class PrepareOrderInput(BaseModel):
    variant_id: str = Field(description="Verified variant UUID to order.")
    quantity: int = Field(default=1, ge=1, le=10)


@tool(args_schema=PrepareOrderInput)
def prepare_order(variant_id: str, quantity: int, config: RunnableConfig) -> str:
    """Prepare an order review for one verified in-stock variant. Never places an order."""
    user_id = config.get("configurable", {}).get("authenticated_user_id")
    if not user_id:
        return json.dumps({"success": False, "requires_authentication": True, "error": "Sign in to prepare an order."})
    try:
        UUID(str(variant_id))
        user = User.objects.filter(pk=user_id, is_active=True).first()
        if not user:
            return json.dumps({"success": False, "requires_authentication": True, "error": "Sign in to prepare an order."})
        draft, error = AssistantOrderDraftService.prepare(user, variant_id, quantity)
        return json.dumps({"success": not bool(error), "draft": draft} if not error else {"success": False, **error})
    except (ValueError, TypeError):
        return json.dumps({"success": False, "error": "Invalid product variant."})
