from functools import lru_cache

from apps.ai_assistant.agents.guest.graph import build_guest_graph


@lru_cache(maxsize=1)
def get_guest_graph():
    return build_guest_graph()
