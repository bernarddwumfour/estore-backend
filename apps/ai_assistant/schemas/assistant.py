
from typing import TypedDict


class AssistantProductCard(TypedDict):
    id: str
    title: str
    slug: str
    min_price: float | None
    max_price: float | None
    has_stock: bool
    image: str | None
