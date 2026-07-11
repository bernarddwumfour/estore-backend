"""
Marketing URLs
"""

from django.urls import path

from apps.marketing.views import (
    admin_campaign_create,
    admin_campaign_detail,
    admin_campaign_list,
    admin_campaign_segments,
    admin_campaign_send,
    admin_campaign_test_send,
    admin_campaign_update,
)

app_name = "marketing"

urlpatterns = [
    path("/admin/campaigns", admin_campaign_list, name="admin-campaign-list"),
    path("/admin/campaigns/create", admin_campaign_create, name="admin-campaign-create"),
    path("/admin/campaigns/segments", admin_campaign_segments, name="admin-campaign-segments"),
    path("/admin/campaigns/<uuid:campaign_id>", admin_campaign_detail, name="admin-campaign-detail"),
    path("/admin/campaigns/<uuid:campaign_id>/update", admin_campaign_update, name="admin-campaign-update"),
    path("/admin/campaigns/<uuid:campaign_id>/test-send", admin_campaign_test_send, name="admin-campaign-test-send"),
    path("/admin/campaigns/<uuid:campaign_id>/send", admin_campaign_send, name="admin-campaign-send"),
]
