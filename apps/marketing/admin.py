from django.contrib import admin

from apps.marketing.models import EmailCampaign


@admin.register(EmailCampaign)
class EmailCampaignAdmin(admin.ModelAdmin):
    list_display = ("name", "campaign_type", "segment", "status", "sent_count", "failed_count", "created_at")
    list_filter = ("status", "campaign_type", "segment")
    search_fields = ("name", "subject")
    readonly_fields = ("total_recipients", "sent_count", "failed_count", "error_sample", "sent_at")
