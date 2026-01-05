"""
products/admin.py
"""

from django.contrib import admin
from .models import (
    Category,
    Brand,
    Product,
    ProductVariant,
    VariantImage,
    ProductReview,
    Wishlist,
)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "parent", "is_active"]
    list_filter = ["is_active", "parent"]
    search_fields = ["name", "slug"]
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ("name",)}


class VariantImageInline(admin.TabularInline):
    model = VariantImage
    extra = 1


class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = [
        "title",
        "slug",
        "status",
        "is_featured",
        "average_rating",
        "created_at",
    ]
    list_filter = ["status", "is_featured", "is_bestseller", "category"]
    search_fields = ["title", "slug", "description"]
    prepopulated_fields = {"slug": ("title",)}
    inlines = [ProductVariantInline]
    readonly_fields = [
        "average_rating",
        "total_reviews",
        "created_at",
        "updated_at",
        "published_at",
    ]


@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = [
        "sku",
        "product",
        "price",
        "discount_amount",
        "stock",
        "is_default",
        "is_active",
    ]
    list_filter = ["is_active", "is_default"]
    search_fields = ["sku", "product__title"]
    inlines = [VariantImageInline]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = [
        "product",
        "user",
        "rating",
        "is_approved",
        "is_verified_purchase",
        "created_at",
    ]
    list_filter = ["rating", "is_approved", "is_verified_purchase"]
    search_fields = ["product__title", "user__email", "comment"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(Wishlist)
class WishlistAdmin(admin.ModelAdmin):
    list_display = ["user", "variant", "created_at"]
    list_filter = ["created_at"]
    search_fields = ["user__email", "variant__sku"]
    readonly_fields = ["created_at"]
