"""
Common app URLs
"""

from django.urls import path
from apps.common.views.log_views import (
    log_list,
    log_detail,
    log_stats,
    log_apps,
)
from apps.common.views.general_config_views import admin_general_config

app_name = "common"

urlpatterns = [
    path("/admin/general/config", admin_general_config, name="general-config"),
    path("/admin/logs", log_list, name="log-list"),
    path("/admin/logs/stats", log_stats, name="log-stats"),
    path("/admin/logs/apps", log_apps, name="log-apps"),
    path("/admin/logs/<uuid:log_id>", log_detail, name="log-detail"),
]