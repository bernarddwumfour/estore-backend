from apps.ai_assistant.features import available_tools
import logging
import time

from langchain_core.messages import SystemMessage

from apps.ai_assistant.agents.shopper.nodes import get_shopper_model
from apps.ai_assistant.agents.guest.prompts import GUEST_SYSTEM_PROMPT
from apps.ai_assistant.tools.guest import GUEST_TOOLS

logger = logging.getLogger(__name__)


def create_guest_assistant_node():
    model = get_shopper_model()

    def assistant_node(state):
        tools = available_tools(GUEST_TOOLS, "guest")
        model_with_tools = model.bind_tools(tools) if tools else model
        started_at = time.perf_counter()
        social_context = ""
        if state.get("social_channel"):
            from django.conf import settings
            social_context = (" You are replying to a customer on social media. The customer cannot see website cards. "
                "Answer concisely in plain text; do not claim a card is displayed. When relevant, provide verified product details "
                "and direct the customer to the store. Do not use relative links. Store website: " + settings.STOREFRONT_BASE_URL)
        response = model_with_tools.invoke([
            SystemMessage(content=GUEST_SYSTEM_PROMPT + social_context),
            *state["messages"],
        ])
        usage = response.usage_metadata or {}
        logger.info(
            "GUEST LLM | duration_ms=%.2f | input_tokens=%s | output_tokens=%s | tool_calls=%s",
            (time.perf_counter() - started_at) * 1000,
            usage.get("input_tokens"), usage.get("output_tokens"), len(response.tool_calls or []),
        )
        return {"messages": [response]}

    return assistant_node
