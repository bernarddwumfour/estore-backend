from apps.ai_assistant.tools.shopper.product_tools import search_products
from apps.ai_assistant.tools.shopper.product_detail_tools import get_product_details
from apps.ai_assistant.tools.shopper.category_tools import list_product_categories
from apps.ai_assistant.tools.shopper.product_comparison_tools import compare_products
from apps.ai_assistant.tools.shopper.wishlist_tools import add_to_wishlist


SHOPPER_TOOLS = [
    search_products,
    get_product_details,
    list_product_categories,
    compare_products,
    add_to_wishlist,
]