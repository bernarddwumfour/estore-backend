"""common/admin.py — admin registration for shared models."""

from django.contrib import admin
from .models import SystemLog, GeneralConfig


@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ["app_name", "action", "severity", "status_code", "user_email", "created_at"]
    list_filter = ["severity", "app_name", "action", "status_code"]
    search_fields = ["description", "user_email", "path"]
    readonly_fields = [f.name for f in SystemLog._meta.fields]
    date_hierarchy = "created_at"


@admin.register(GeneralConfig)
class GeneralConfigAdmin(admin.ModelAdmin):
    list_display = ["store_name", "currency", "default_payment_method", "updated_at"]
    readonly_fields = ["updated_at"]

    def has_add_permission(self, request):
        return not GeneralConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
