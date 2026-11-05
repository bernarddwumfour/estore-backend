from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode, tools_condition

from apps.ai_assistant.agents.shopper.state import ShopperState
from apps.ai_assistant.agents.shopper.nodes import (
    create_assistant_node,
)
from apps.ai_assistant.tools.shopper import SHOPPER_TOOLS


def build_shopper_graph():
    """
    Construct and compile the shopper agent graph.
    """

    graph = StateGraph(ShopperState)

    # Nodes
    graph.add_node(
        "assistant",
        create_assistant_node(),
    )

    graph.add_node(
        "tools",
        ToolNode(SHOPPER_TOOLS),
    )

    # Entry point
    graph.add_edge(START, "assistant")

    # Tool routing
    graph.add_conditional_edges(
        "assistant",
        tools_condition,
        {
            "tools": "tools",
            END: END,
        },
    )

    # Return to assistant after tool execution
    graph.add_edge("tools", "assistant")

    return graph.compile()