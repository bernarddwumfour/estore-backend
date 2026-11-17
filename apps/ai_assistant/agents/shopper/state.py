from typing import Annotated

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict, NotRequired


class ShopperState(TypedDict):
    """
    State shared across the shopper agent graph.
    """

    messages: Annotated[list[AnyMessage], add_messages]
    social_channel: NotRequired[bool]
    social_comment: NotRequired[bool]
