from apps.ai_assistant.features import tool_node
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from apps.ai_assistant.agents.guest.nodes import create_guest_assistant_node
from apps.ai_assistant.agents.shopper.state import ShopperState
from apps.ai_assistant.tools.guest import GUEST_TOOLS


def build_guest_graph():
    graph = StateGraph(ShopperState)
    graph.add_node("assistant", create_guest_assistant_node())
    graph.add_node("tools", tool_node(GUEST_TOOLS, "guest"))
    graph.add_edge(START, "assistant")
    graph.add_conditional_edges("assistant", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "assistant")
    return graph.compile()
