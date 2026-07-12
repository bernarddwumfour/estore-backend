"""blog/admin.py — Django admin registration for blog models."""

from django.contrib import admin

from .models import BlogCategory, BlogPost


@admin.register(BlogCategory)
class BlogCategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["created_at", "updated_at"]


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "slug",
        "category",
        "status",
        "is_featured",
        "published_at",
        "created_at",
    ]
    list_filter = ["status", "is_featured", "category"]
    search_fields = ["title", "slug", "excerpt", "author_name"]
    prepopulated_fields = {"slug": ("title",)}
    readonly_fields = ["created_at", "updated_at", "published_at"]
    date_hierarchy = "created_at"
