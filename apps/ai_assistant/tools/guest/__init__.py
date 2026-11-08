from apps.ai_assistant.tools.shopper.category_tools import list_product_categories
from apps.ai_assistant.tools.shopper.product_comparison_tools import compare_products
from apps.ai_assistant.tools.shopper.product_detail_tools import get_product_details
from apps.ai_assistant.tools.shopper.product_tools import search_products

from .promotion_tools import get_public_promotion_details, search_active_promotions

GUEST_TOOLS = [
    search_products,
    get_product_details,
    list_product_categories,
    compare_products,
    search_active_promotions,
    get_public_promotion_details,
]
