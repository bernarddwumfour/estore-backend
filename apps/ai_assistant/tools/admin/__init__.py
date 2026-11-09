from .product_tools import (
    search_admin_products, get_admin_product, list_admin_variants,
    get_admin_variant, list_admin_categories, get_admin_category, get_inventory_health,
)
from .product_write_tools import (
    create_admin_product, update_admin_product,
    create_admin_variant, update_admin_variant,
    create_admin_category, update_admin_category,
    bulk_admin_products, bulk_admin_variants, bulk_admin_categories,
)
from .user_tools import (
    search_admin_users, get_admin_user, search_admin_affiliates,
    prepare_admin_user_update,
)
from .marketing_tools import (
    search_admin_promotions, search_admin_discount_codes,
    get_admin_promotion_details, search_admin_blog_posts,
    get_admin_blog_post_details, search_admin_reviews,
    prepare_admin_marketing_action, prepare_admin_promotion_create,
    prepare_admin_discount_code_create, prepare_admin_blog_post_create,
)
from .social_post_tools import (
    search_admin_social_posts, get_admin_social_post_details,
    list_admin_social_accounts, get_admin_social_post_analytics,
    prepare_admin_social_post, prepare_admin_social_post_approval,
    prepare_admin_social_post_rejection,
)

ADMIN_TOOLS = [
    search_admin_products, get_admin_product, list_admin_variants,
    get_admin_variant, list_admin_categories, get_admin_category, get_inventory_health,
    create_admin_product, update_admin_product,
    create_admin_variant, update_admin_variant,
    create_admin_category, update_admin_category,
    bulk_admin_products, bulk_admin_variants, bulk_admin_categories,
    search_admin_users, get_admin_user, search_admin_affiliates,
    prepare_admin_user_update,
    search_admin_promotions, search_admin_discount_codes,
    get_admin_promotion_details, search_admin_blog_posts,
    get_admin_blog_post_details, search_admin_reviews,
    prepare_admin_marketing_action, prepare_admin_promotion_create,
    prepare_admin_discount_code_create, prepare_admin_blog_post_create,
    search_admin_social_posts, get_admin_social_post_details,
    list_admin_social_accounts, get_admin_social_post_analytics,
    prepare_admin_social_post, prepare_admin_social_post_approval,
    prepare_admin_social_post_rejection,
]
