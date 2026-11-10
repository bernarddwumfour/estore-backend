"""Runtime controls shared by search, agents, and their tool execution."""
from functools import wraps
from langchain_core.runnables import RunnableConfig
from apps.common.models import GeneralConfig
from estore.utils.responses import APIResponse

DISCOVERY_TOOLS = {"search_products", "get_product_details", "list_product_categories", "compare_products"}


def enabled(feature: str) -> bool:
    # Read authoritative settings so changes affect all API/worker processes.
    config = GeneralConfig.get()
    return config.ai_enabled and getattr(config, "ai_" + feature + "_enabled", False)


def require_agent(agent: str):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not enabled(agent):
                return APIResponse.forbidden("This AI assistant is disabled by the store.")
            return view(*args, **kwargs)
        return wrapped
    return decorate


def available_tools(tools, agent: str):
    if not enabled(agent):
        raise ValueError("This AI assistant is disabled by the store.")
    discovery = enabled("discovery")
    return [tool for tool in tools if discovery or tool.name not in DISCOVERY_TOOLS]


def tool_node(tools, agent: str):
    from langgraph.prebuilt import ToolNode
    def run(state, config: RunnableConfig):
        return ToolNode(available_tools(tools, agent)).invoke(state, config=config)
    return run
