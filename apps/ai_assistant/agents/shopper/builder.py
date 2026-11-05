from functools import lru_cache

from apps.ai_assistant.agents.shopper.graph import (
    build_shopper_graph,
)


@lru_cache(maxsize=1)
def get_shopper_graph():
    """
    Return a cached compiled shopper graph.
    """

    return build_shopper_graph()