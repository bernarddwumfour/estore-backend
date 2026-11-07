"""Cached admin graph builder."""

from functools import lru_cache

from apps.ai_assistant.agents.admin.graph import build_admin_graph


@lru_cache(maxsize=1)
def get_admin_graph():
    return build_admin_graph()
