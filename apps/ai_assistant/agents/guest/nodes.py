from apps.ai_assistant.features import available_tools
import logging
import time

from langchain_core.messages import SystemMessage

from apps.ai_assistant.agents.shopper.nodes import get_shopper_model
from apps.ai_assistant.agents.guest.prompts import GUEST_SYSTEM_PROMPT, GUEST_SOCIAL_CONTEXT, GUEST_WEBSITE_CONTEXT
from apps.ai_assistant.tools.guest import GUEST_TOOLS

logger = logging.getLogger(__name__)


def create_guest_assistant_node():
    model = get_shopper_model()

    def assistant_node(state):
        tools = available_tools(GUEST_TOOLS, "guest")
        model_with_tools = model.bind_tools(tools) if tools else model
        started_at = time.perf_counter()
        channel_context = GUEST_WEBSITE_CONTEXT
        if state.get("social_channel"):
            from django.conf import settings
            from urllib.parse import urlparse
            site = settings.STOREFRONT_BASE_URL.rstrip("/")
            parsed = urlparse(site)
            public_site = parsed.scheme in {"http", "https"} and parsed.hostname not in {None, "localhost", "127.0.0.1", "::1"}
            channel_context = GUEST_SOCIAL_CONTEXT + " " + (
                "Store website: " + site if public_site else
                "No public storefront URL is configured, so do not claim a product link is provided."
            )
        response = model_with_tools.invoke([
            SystemMessage(content=GUEST_SYSTEM_PROMPT + "\n" + channel_context),
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
