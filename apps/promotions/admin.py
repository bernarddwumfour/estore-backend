from django.contrib import admin

from apps.promotions.models import (
    Promotion,
    PromotionItem,
    PromotionImage,
    DiscountCode,
    AffiliateCommission,
)


@admin.register(DiscountCode)
class DiscountCodeAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "discount_type", "value", "is_active", "affiliate")
    search_fields = ("code", "name")
    list_filter = ("discount_type", "is_active")


@admin.register(AffiliateCommission)
class AffiliateCommissionAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "affiliate",
        "commission_rate",
        "commissionable_amount",
        "commission_amount",
        "status",
    )
    search_fields = ("order__order_number", "affiliate__user__email")
    list_filter = ("status",)


admin.site.register(Promotion)
admin.site.register(PromotionItem)
admin.site.register(PromotionImage)
