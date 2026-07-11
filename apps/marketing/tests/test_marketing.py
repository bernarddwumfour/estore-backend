import json
from unittest.mock import patch

from django.test import Client, TestCase

from apps.marketing.models import EmailCampaign
from apps.marketing.selectors import get_segment_counts, get_segment_queryset
from apps.marketing.services import CampaignService
from apps.marketing.tests.factories import (
    make_admin,
    make_campaign,
    make_customer_profile,
    make_user,
)
from apps.users.utils.token_utils import generate_jwt_token


class SegmentSelectorTests(TestCase):
    def setUp(self):
        self.customer = make_user()
        self.verified = make_user(email_verified=True)
        self.optout_user = make_user()
        make_customer_profile(self.optout_user, receive_marketing=False, receive_newsletter=False)
        self.optin_user = make_user()
        make_customer_profile(self.optin_user, receive_marketing=True, receive_newsletter=True)
        self.admin = make_admin()

    def test_all_users_excludes_inactive_and_guests(self):
        inactive = make_user(is_active=False)
        guest = make_user(password=None)  # User.save() marks passwordless users as guests
        emails = set(
            get_segment_queryset(EmailCampaign.SEGMENT_ALL_USERS).values_list("email", flat=True)
        )
        self.assertNotIn(inactive.email, emails)
        self.assertNotIn(guest.email, emails)
        self.assertIn(self.customer.email, emails)
        self.assertIn(self.admin.email, emails)

    def test_customers_segment_excludes_admin(self):
        emails = set(
            get_segment_queryset(EmailCampaign.SEGMENT_CUSTOMERS).values_list("email", flat=True)
        )
        self.assertIn(self.customer.email, emails)
        self.assertNotIn(self.admin.email, emails)

    def test_verified_customers_segment(self):
        emails = set(
            get_segment_queryset(EmailCampaign.SEGMENT_VERIFIED_CUSTOMERS).values_list(
                "email", flat=True
            )
        )
        self.assertIn(self.verified.email, emails)
        self.assertNotIn(self.customer.email, emails)

    def test_newsletter_segment_respects_flag(self):
        emails = set(
            get_segment_queryset(EmailCampaign.SEGMENT_NEWSLETTER_SUBSCRIBERS).values_list(
                "email", flat=True
            )
        )
        self.assertIn(self.optin_user.email, emails)
        self.assertNotIn(self.optout_user.email, emails)
        self.assertNotIn(self.customer.email, emails)  # no profile → not subscribed

    def test_promotion_type_excludes_marketing_optout_in_any_segment(self):
        emails = set(
            get_segment_queryset(
                EmailCampaign.SEGMENT_ALL_USERS, campaign_type=EmailCampaign.TYPE_PROMOTION
            ).values_list("email", flat=True)
        )
        self.assertNotIn(self.optout_user.email, emails)
        self.assertIn(self.optin_user.email, emails)
        # users without a profile are not treated as opted out
        self.assertIn(self.customer.email, emails)

    def test_segment_counts_shape(self):
        counts = get_segment_counts()
        for segment, _label in EmailCampaign.SEGMENT_CHOICES:
            self.assertIn(segment, counts)


class CampaignServiceTests(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.recipient = make_user()

    def test_update_rejected_unless_draft(self):
        campaign = make_campaign(status=EmailCampaign.STATUS_SENT)
        updated, error = CampaignService.update_campaign(campaign, {"name": "New"})
        self.assertIsNone(updated)
        self.assertIn("status", error)

    def test_initiate_send_runs_task_and_updates_counts(self):
        campaign = make_campaign(created_by=self.admin)

        with patch("apps.marketing.tasks.email_service.send_batch") as mock_batch:
            mock_batch.return_value = (2, 0, [])
            with self.captureOnCommitCallbacks(execute=True):
                campaign, error = CampaignService.initiate_send(str(campaign.id))
            self.assertIsNone(error)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_SENT)
        self.assertEqual(campaign.sent_count, 2)
        self.assertEqual(campaign.failed_count, 0)
        self.assertIsNotNone(campaign.sent_at)
        # messages included both active users
        recipients = {m["to"] for m in mock_batch.call_args[0][0]}
        self.assertIn(self.recipient.email, recipients)

    def test_initiate_send_rejected_when_already_sending(self):
        campaign = make_campaign(status=EmailCampaign.STATUS_SENDING)
        result, error = CampaignService.initiate_send(str(campaign.id))
        self.assertIsNone(result)
        self.assertIn("status", error)

    def test_task_skips_campaign_not_in_sending_status(self):
        from apps.marketing.tasks import send_campaign_task

        campaign = make_campaign(status=EmailCampaign.STATUS_SENT, sent_count=5)
        with patch("apps.marketing.tasks.email_service.send_batch") as mock_batch:
            send_campaign_task(str(campaign.id))
        mock_batch.assert_not_called()
        campaign.refresh_from_db()
        self.assertEqual(campaign.sent_count, 5)

    def test_partial_failure_sets_partially_sent(self):
        campaign = make_campaign()
        with patch("apps.marketing.tasks.email_service.send_batch") as mock_batch:
            mock_batch.return_value = (1, 1, [{"email": "x@y.z", "error": "boom"}])
            with self.captureOnCommitCallbacks(execute=True):
                campaign, error = CampaignService.initiate_send(str(campaign.id))
            self.assertIsNone(error)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_PARTIALLY_SENT)
        self.assertEqual(campaign.error_sample, [{"email": "x@y.z", "error": "boom"}])

    def test_send_test_uses_email_service(self):
        campaign = make_campaign()
        with patch("apps.marketing.services.email_service.send") as mock_send:
            mock_send.return_value = True
            ok, error = CampaignService.send_test(campaign, "review@example.com")
        self.assertTrue(ok)
        self.assertIsNone(error)
        kwargs = mock_send.call_args.kwargs
        self.assertEqual(kwargs["recipient_email"], "review@example.com")
        self.assertTrue(kwargs["subject"].startswith("[TEST]"))


class CampaignApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_admin()
        self.customer = make_user()

    def _auth_headers(self, user):
        token = generate_jwt_token(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_create_requires_admin_role(self):
        payload = {"name": "N", "subject": "S", "html_body": "<p>B</p>"}
        response = self.client.post(
            "/api/marketing/admin/campaigns/create",
            data=json.dumps(payload),
            content_type="application/json",
            **self._auth_headers(self.customer),
        )
        self.assertEqual(response.status_code, 403)

    def test_create_list_detail_update_flow(self):
        payload = {
            "name": "July Newsletter",
            "subject": "News for July",
            "html_body": "<p>Hello</p>",
            "campaign_type": "newsletter",
            "segment": "all_users",
        }
        response = self.client.post(
            "/api/marketing/admin/campaigns/create",
            data=json.dumps(payload),
            content_type="application/json",
            **self._auth_headers(self.admin),
        )
        self.assertEqual(response.status_code, 201)
        campaign_id = response.json()["data"]["id"]

        response = self.client.get(
            "/api/marketing/admin/campaigns", **self._auth_headers(self.admin)
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["total"], 1)

        response = self.client.get(
            f"/api/marketing/admin/campaigns/{campaign_id}",
            **self._auth_headers(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["html_body"], "<p>Hello</p>")

        response = self.client.patch(
            f"/api/marketing/admin/campaigns/{campaign_id}/update",
            data=json.dumps({"subject": "Updated subject"}),
            content_type="application/json",
            **self._auth_headers(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["subject"], "Updated subject")

    def test_create_validation_errors(self):
        response = self.client.post(
            "/api/marketing/admin/campaigns/create",
            data=json.dumps({"name": "", "segment": "nonsense"}),
            content_type="application/json",
            **self._auth_headers(self.admin),
        )
        self.assertEqual(response.status_code, 422)
        errors = response.json()["errors"]
        self.assertIn("name", errors)
        self.assertIn("subject", errors)
        self.assertIn("segment", errors)

    def test_segments_endpoint(self):
        response = self.client.get(
            "/api/marketing/admin/campaigns/segments",
            **self._auth_headers(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        segments = response.json()["data"]["segments"]
        values = {s["value"] for s in segments}
        self.assertIn("all_users", values)
        self.assertTrue(all("recipients" in s for s in segments))

    def test_send_endpoint_transitions_and_blocks_resend(self):
        campaign = make_campaign(created_by=self.admin)

        with patch("apps.marketing.tasks.email_service.send_batch") as mock_batch:
            mock_batch.return_value = (2, 0, [])
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    f"/api/marketing/admin/campaigns/{campaign.id}/send",
                    **self._auth_headers(self.admin),
                )
        self.assertEqual(response.status_code, 200)

        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.STATUS_SENT)

        # A sent campaign cannot be sent again
        response = self.client.post(
            f"/api/marketing/admin/campaigns/{campaign.id}/send",
            **self._auth_headers(self.admin),
        )
        self.assertEqual(response.status_code, 422)
