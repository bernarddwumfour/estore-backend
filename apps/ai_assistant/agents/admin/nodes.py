from apps.ai_assistant.features import available_tools
"""Model and assistant node for the admin agent."""

import logging
import os
import time

from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI

from apps.ai_assistant.agents.admin.prompts import ADMIN_SYSTEM_PROMPT
from apps.ai_assistant.tools.admin import ADMIN_TOOLS

logger = logging.getLogger(__name__)


def get_admin_model():
    return ChatOpenAI(
        model=os.getenv("ADMIN_ASSISTANT_MODEL", "gpt-4.1-mini"),
        temperature=0.2,
    )


def create_assistant_node():
    model = get_admin_model()

    def assistant_node(state):
        tools = available_tools(ADMIN_TOOLS, "admin")
        model_with_tools = model.bind_tools(tools) if tools else model
        started_at = time.perf_counter()
        response = model_with_tools.invoke([
            SystemMessage(content=ADMIN_SYSTEM_PROMPT),
            *state["messages"],
        ])
        usage = response.usage_metadata or {}
        logger.info(
            "ADMIN LLM | duration_ms=%.2f | input_tokens=%s | output_tokens=%s | tool_calls=%s",
            (time.perf_counter() - started_at) * 1000,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            len(response.tool_calls or []),
        )
        return {"messages": [response]}

    return assistant_node
