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
            from urllib.parse import urlparse
            site = settings.STOREFRONT_BASE_URL.rstrip("/")
            parsed = urlparse(site)
            public_site = parsed.scheme in {"http", "https"} and parsed.hostname not in {None, "localhost", "127.0.0.1", "::1"}
            social_context = (" You are replying to a customer on social media. The customer cannot see website cards. "
                "Answer concisely in plain text; do not claim a card is displayed. When relevant, provide verified product details "
                "and direct the customer to the store. Do not use relative links. " +
                ("Store website: " + site if public_site else "Do not provide a website link because no public storefront URL is configured."))
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
