
from django.urls import path

from . import views

app_name = "ai_assistant"

urlpatterns = [
    path("chat/", views.assistant_chat, name="assistant-chat"),
    path("guest/chat/", views.guest_assistant_chat, name="guest-assistant-chat"),
    path("admin/chat/", views.admin_assistant_chat, name="admin-assistant-chat"),
    path("admin/conversations/", views.admin_assistant_conversations, name="admin-assistant-conversations"),
    path("admin/conversations/<uuid:conversation_id>/", views.admin_assistant_conversation_detail,
         name="admin-assistant-conversation-detail"),
    path("admin/conversations/<uuid:conversation_id>/events/", views.append_admin_assistant_conversation_event,
         name="append-admin-assistant-conversation-event"),
    path("admin/actions/prepare/", views.prepare_admin_product_bulk_action,
         name="prepare-admin-product-bulk-action"),
    path("admin/marketing/actions/prepare/", views.prepare_admin_marketing_action,
         name="prepare-admin-marketing-action"),
    path("admin/marketing/actions/<uuid:action_id>/confirm/", views.confirm_admin_marketing_action,
         name="confirm-admin-marketing-action"),
    path("admin/social/posts/actions/<uuid:action_id>/confirm/", views.confirm_admin_social_post_action,
         name="confirm-admin-social-post-action"),
    path("admin/actions/<uuid:action_id>/confirm/", views.confirm_admin_product_action,
         name="confirm-admin-product-action"),
    path("admin/users/actions/<uuid:action_id>/confirm/", views.confirm_admin_user_action,
         name="confirm-admin-user-action"),
    path("orders/<uuid:draft_id>/confirm/", views.confirm_assistant_order, name="assistant-order-confirm"),
]
