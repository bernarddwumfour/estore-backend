from apps.ai_assistant.tools.shopper.product_tools import search_products
from apps.ai_assistant.tools.shopper.product_detail_tools import get_product_details
from apps.ai_assistant.tools.shopper.category_tools import list_product_categories
from apps.ai_assistant.tools.shopper.product_comparison_tools import compare_products
from apps.ai_assistant.tools.shopper.wishlist_tools import add_to_wishlist
from apps.ai_assistant.tools.shopper.order_tools import prepare_order
from apps.ai_assistant.tools.shopper.order_tracking_tools import track_customer_orders
from apps.ai_assistant.tools.shopper.service_tools import search_services, get_service_details, list_service_categories, compare_services
from apps.ai_assistant.tools.shopper.appointment_tools import check_service_availability, list_my_appointments, prepare_appointment, prepare_appointment_cancellation


SHOPPER_TOOLS = [
    search_products,
    get_product_details,
    list_product_categories,
    compare_products,
    search_services,
    get_service_details,
    list_service_categories,
    compare_services,
    check_service_availability,
    list_my_appointments,
    prepare_appointment,
    prepare_appointment_cancellation,
    add_to_wishlist,
    prepare_order,
    track_customer_orders,
]
