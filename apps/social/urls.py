"""
Social URLs
"""

from django.urls import path

from apps.social.views import (
    admin_social_accounts,
    admin_social_account_connect,
    admin_social_account_disconnect,
    admin_social_account_move,
    admin_social_config,
    admin_social_media_delete,
    admin_social_media_list,
    admin_social_media_upload,
    admin_social_comment_action,
    admin_social_comment_reply,
    admin_social_conversations,
    admin_social_message_send,
    admin_social_messages,
    admin_social_post_analytics,
    admin_social_post_approve,
    admin_social_post_comments,
    admin_social_post_create,
    admin_social_post_delete,
    admin_social_post_list,
    admin_social_post_reject,
    admin_social_profile_detail,
    admin_social_profiles,
    admin_social_usage,
)

app_name = "social"

urlpatterns = [
    path("/admin/accounts", admin_social_accounts, name="admin-social-accounts"),
    path("/admin/config", admin_social_config, name="admin-social-config"),
    path("/admin/usage", admin_social_usage, name="admin-social-usage"),
    path("/admin/media", admin_social_media_list, name="admin-social-media-list"),
    path("/admin/media/upload", admin_social_media_upload, name="admin-social-media-upload"),
    path("/admin/media/<uuid:media_id>/delete", admin_social_media_delete, name="admin-social-media-delete"),
    path("/admin/profiles", admin_social_profiles, name="admin-social-profiles"),
    path("/admin/profiles/<str:profile_id>", admin_social_profile_detail, name="admin-social-profile-detail"),
    path("/admin/accounts/connect", admin_social_account_connect, name="admin-social-account-connect"),
    path("/admin/accounts/<str:account_id>/disconnect", admin_social_account_disconnect, name="admin-social-account-disconnect"),
    path("/admin/accounts/<str:account_id>/move", admin_social_account_move, name="admin-social-account-move"),
    path("/admin/posts", admin_social_post_list, name="admin-social-post-list"),
    path("/admin/posts/create", admin_social_post_create, name="admin-social-post-create"),
    path("/admin/posts/<uuid:post_id>/approve", admin_social_post_approve, name="admin-social-post-approve"),
    path("/admin/posts/<uuid:post_id>/reject", admin_social_post_reject, name="admin-social-post-reject"),
    path("/admin/posts/<uuid:post_id>/delete", admin_social_post_delete, name="admin-social-post-delete"),
    path("/admin/posts/<uuid:post_id>/analytics", admin_social_post_analytics, name="admin-social-post-analytics"),
    path("/admin/posts/<uuid:post_id>/comments", admin_social_post_comments, name="admin-social-post-comments"),
    path("/admin/posts/<uuid:post_id>/comments/reply", admin_social_comment_reply, name="admin-social-comment-reply"),
    path("/admin/posts/<uuid:post_id>/comments/action", admin_social_comment_action, name="admin-social-comment-action"),
    path("/admin/inbox/conversations", admin_social_conversations, name="admin-social-conversations"),
    path("/admin/inbox/conversations/<str:conversation_id>/messages", admin_social_messages, name="admin-social-messages"),
    path("/admin/inbox/conversations/<str:conversation_id>/send", admin_social_message_send, name="admin-social-message-send"),
]
