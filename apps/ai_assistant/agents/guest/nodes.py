import logging
import time

from langchain_core.messages import SystemMessage

from apps.ai_assistant.agents.shopper.nodes import get_shopper_model
from apps.ai_assistant.agents.guest.prompts import GUEST_SYSTEM_PROMPT
from apps.ai_assistant.tools.guest import GUEST_TOOLS

logger = logging.getLogger(__name__)


def create_guest_assistant_node():
    model_with_tools = get_shopper_model().bind_tools(GUEST_TOOLS)

    def assistant_node(state):
        started_at = time.perf_counter()
        response = model_with_tools.invoke([
            SystemMessage(content=GUEST_SYSTEM_PROMPT),
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
