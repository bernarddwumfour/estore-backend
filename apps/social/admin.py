"""social/admin.py — admin registration for social models."""

from django.contrib import admin

from .models import (
    SandboxAccount,
    SandboxComment,
    SandboxConversation,
    SandboxMessage,
    SandboxProfile,
    SocialConfig,
    SocialMedia,
    SocialPost,
)


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "source",
        "status",
        "created_by",
        "scheduled_for",
        "created_at",
    ]
    list_filter = ["source", "status"]
    search_fields = ["caption", "zernio_post_id"]
    readonly_fields = ["created_at", "updated_at", "sent_at"]


@admin.register(SocialConfig)
class SocialConfigAdmin(admin.ModelAdmin):
    list_display = ["mode", "updated_at"]
    readonly_fields = ["updated_at"]

    def has_add_permission(self, request):
        return not SocialConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(SocialMedia)
class SocialMediaAdmin(admin.ModelAdmin):
    list_display = ["name", "media_type", "uploaded_by", "created_at"]
    list_filter = ["media_type"]
    search_fields = ["name"]
    readonly_fields = ["created_at"]


@admin.register(SandboxComment)
class SandboxCommentAdmin(admin.ModelAdmin):
    list_display = ["author", "zernio_post_id", "is_reply", "hidden", "created_at"]
    list_filter = ["is_reply", "hidden"]
    search_fields = ["author", "message", "zernio_post_id"]
    readonly_fields = ["created_at"]


@admin.register(SandboxConversation)
class SandboxConversationAdmin(admin.ModelAdmin):
    list_display = ["name", "platform", "created_at"]
    list_filter = ["platform"]
    search_fields = ["name"]
    readonly_fields = ["created_at"]


@admin.register(SandboxMessage)
class SandboxMessageAdmin(admin.ModelAdmin):
    list_display = ["conversation", "is_outgoing", "created_at"]
    list_filter = ["is_outgoing"]
    readonly_fields = ["created_at"]


@admin.register(SandboxProfile)
class SandboxProfileAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(SandboxAccount)
class SandboxAccountAdmin(admin.ModelAdmin):
    list_display = ["name", "platform", "profile", "created_at"]
    list_filter = ["platform"]
    search_fields = ["name"]
    readonly_fields = ["created_at"]
