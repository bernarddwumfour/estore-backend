from django.contrib import admin

from apps.ai_assistant.models import (
    Conversation,
    ConversationMessage,
)


class ConversationMessageInline(admin.TabularInline):
    model = ConversationMessage
    extra = 0
    readonly_fields = (
        "id",
        "role",
        "content",
        "created_at",
    )
    can_delete = False


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "title",
        "is_active",
        "created_at",
        "updated_at",
    )

    list_filter = (
        "is_active",
        "created_at",
    )

    search_fields = (
        "user__email",
        "title",
    )

    readonly_fields = (
        "id",
        "created_at",
        "updated_at",
    )

    inlines = [ConversationMessageInline]


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "role",
        "created_at",
    )

    list_filter = (
        "role",
        "created_at",
    )

    search_fields = (
        "content",
        "conversation__title",
    )

    readonly_fields = (
        "id",
        "conversation",
        "role",
        "content",
        "metadata",
        "created_at",
    )