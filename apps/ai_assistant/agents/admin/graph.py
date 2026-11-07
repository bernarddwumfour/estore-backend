"""Admin agent graph, separate from the shopper graph."""

from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode, tools_condition

from apps.ai_assistant.agents.admin.nodes import create_assistant_node
from apps.ai_assistant.agents.admin.state import AdminState
from apps.ai_assistant.tools.admin import ADMIN_TOOLS


def build_admin_graph():
    graph = StateGraph(AdminState)
    graph.add_node("assistant", create_assistant_node())
    graph.add_node("tools", ToolNode(ADMIN_TOOLS))
    graph.add_edge(START, "assistant")
    graph.add_conditional_edges("assistant", tools_condition, {"tools": "tools", END: END})
    graph.add_edge("tools", "assistant")
    return graph.compile()
