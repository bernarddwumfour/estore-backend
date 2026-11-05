import os

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage

from apps.ai_assistant.agents.shopper.prompts import (
    SHOPPER_SYSTEM_PROMPT,
)

from apps.ai_assistant.tools.shopper import SHOPPER_TOOLS
import logging
import time

logger = logging.getLogger(__name__)

def get_shopper_model():
    """
    Create the configured language model.

    OPENAI_API_KEY must be supplied through the environment.
    SHOPPER_ASSISTANT_MODEL controls the model selection.
    """

    model_name = os.getenv(
        "SHOPPER_ASSISTANT_MODEL",
        "gpt-4.1-mini",
    )

    return ChatOpenAI(
        model=model_name,
        temperature=0.2,
    )



def create_assistant_node():
    """
    Create the shopper assistant node with tool binding
    and per-invocation usage monitoring.
    """

    model = get_shopper_model()
    model_with_tools = model.bind_tools(SHOPPER_TOOLS)

    def assistant_node(state):
        messages = [
            SystemMessage(content=SHOPPER_SYSTEM_PROMPT),
            *state["messages"],
        ]

        started_at = time.perf_counter()

        response = model_with_tools.invoke(messages)

        duration_ms = (
            time.perf_counter() - started_at
        ) * 1000

        usage = response.usage_metadata or {}

        logger.info(
            "SHOPPER LLM | "
            "duration_ms=%.2f | "
            "input_tokens=%s | "
            "output_tokens=%s | "
            "total_tokens=%s | "
            "tool_calls=%s",
            duration_ms,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            usage.get("total_tokens"),
            len(response.tool_calls or []),
        )

        for tool_call in response.tool_calls or []:
            logger.info(
                "SHOPPER TOOL CALL | name=%s",
                tool_call.get("name"),
            )

        return {
            "messages": [response],
        }

    return assistant_node
