import json
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import Client, TestCase

from apps.social.models import SocialPost
from apps.social.captions import build_product_caption, build_promotion_caption
from apps.social.services import SocialPostService
from apps.social.tests.factories import (
    ZERNIO_ACCOUNTS,
    make_admin,
    make_social_post,
    make_user,
)
from apps.social.zernio_service import ZernioService
from apps.users.utils.token_utils import generate_jwt_token


def _response(status_code=200, payload=None):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = payload if payload is not None else {}
    mock.text = json.dumps(payload or {})
    return mock


def configured(func):
    """Run a test with the Zernio API key present."""
    return patch.object(ZernioService, "API_KEY", "sk_test")(func)


class ZernioServiceTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_not_configured_returns_error(self):
        with patch.object(ZernioService, "API_KEY", ""):
            accounts, error = ZernioService.list_accounts()
        self.assertIsNone(accounts)
        self.assertIn("not configured", error)

    @configured
    def test_list_accounts_success_and_cache(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(200, {"accounts": ZERNIO_ACCOUNTS})
            accounts, error = ZernioService.list_accounts()
            self.assertIsNone(error)
            self.assertEqual(len(accounts), 2)

            # second call served from cache — no extra HTTP request
            ZernioService.list_accounts()
            self.assertEqual(mock_request.call_count, 1)

    @configured
    def test_create_post_publish_now_payload(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(201, {"post": {"_id": "zp_1"}})
            result, error = ZernioService.create_post(
                "Hello", [{"platform": "twitter", "accountId": "acc_tw"}],
                media_urls=["https://res.cloudinary.com/img.jpg"],
            )
        self.assertIsNone(error)
        self.assertEqual(result["_id"], "zp_1")
        payload = mock_request.call_args.kwargs["json"]
        self.assertTrue(payload["publishNow"])
        self.assertEqual(payload["mediaUrls"], ["https://res.cloudinary.com/img.jpg"])
        self.assertNotIn("scheduledFor", payload)

    @configured
    def test_create_post_scheduled_payload(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(201, {"post": {"_id": "zp_2"}})
            ZernioService.create_post(
                "Hello", [{"platform": "twitter", "accountId": "acc_tw"}],
                scheduled_for="2030-01-01T09:00:00+00:00",
            )
        payload = mock_request.call_args.kwargs["json"]
        self.assertNotIn("publishNow", payload)
        self.assertEqual(payload["scheduledFor"], "2030-01-01T09:00:00+00:00")
        self.assertIn("timezone", payload)

    @configured
    def test_400_surfaces_zernio_message(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(
                400, {"message": "Duplicate content: an identical post was already published"}
            )
            result, error = ZernioService.create_post("x", [])
        self.assertIsNone(result)
        self.assertIn("Duplicate content", error)

    @configured
    def test_error_statuses_do_not_leak_body(self):
        for status_code, expected in [(401, "Invalid social media API key"), (429, "Rate limit")]:
            with patch("apps.social.zernio_service.requests.request") as mock_request:
                mock_request.return_value = _response(status_code, {"secret": "internals"})
                result, error = ZernioService.create_post("x", [])
            self.assertIsNone(result)
            self.assertIn(expected.split()[0], error)
            self.assertNotIn("internals", error)

    @configured
    def test_timeout_and_connection_errors(self):
        with patch(
            "apps.social.zernio_service.requests.request",
            side_effect=requests.Timeout,
        ):
            result, error = ZernioService.list_accounts()
        self.assertIsNone(result)
        self.assertIn("timeout", error)

        with patch(
            "apps.social.zernio_service.requests.request",
            side_effect=requests.ConnectionError,
        ):
            result, error = ZernioService.list_conversations()
        self.assertIsNone(result)
        self.assertIn("connect", error)


class CaptionTests(TestCase):
    def test_product_caption_contains_title_and_link(self):
        product = MagicMock()
        product.title = "Blue Sneakers"
        product.description = "Comfy " * 100
        product.slug = "blue-sneakers"
        product.default_variant.discounted_price = 120
        caption = build_product_caption(product)
        self.assertIn("Blue Sneakers", caption)
        self.assertIn("/products/blue-sneakers", caption)
        self.assertIn("120", caption)
        # description is truncated
        self.assertLess(len(caption), 700)

    def test_promotion_caption_contains_name_and_link(self):
        promotion = MagicMock()
        promotion.name = "Summer Bundle"
        promotion.description = "Save big"
        promotion.slug = "summer-bundle"
        promotion.bundle_price = 300
        promotion.ends_at = None
        caption = build_promotion_caption(promotion)
        self.assertIn("Summer Bundle", caption)
        self.assertIn("/promotions/summer-bundle", caption)
        self.assertIn("300", caption)


class SocialPostServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.admin = make_admin()

    def test_create_manual_post_not_configured(self):
        with patch.object(ZernioService, "API_KEY", ""):
            post, error = SocialPostService.create_manual_post(
                {"caption": "Hi"}, self.admin
            )
        self.assertIsNone(post)
        self.assertIn("not configured", error)
        self.assertEqual(SocialPost.objects.count(), 0)

    @configured
    def test_create_manual_post_success(self):
        with patch.object(
            ZernioService, "list_accounts", return_value=(ZERNIO_ACCOUNTS, None)
        ), patch.object(
            ZernioService, "create_post", return_value=({"_id": "zp_9"}, None)
        ) as mock_create:
            post, error = SocialPostService.create_manual_post(
                {"caption": "Hi", "account_ids": ["acc_tw"]}, self.admin
            )
        self.assertIsNone(error)
        self.assertEqual(post.status, SocialPost.STATUS_SENT)
        self.assertEqual(post.zernio_post_id, "zp_9")
        self.assertIsNotNone(post.sent_at)
        # only the selected account was targeted
        platforms = mock_create.call_args.kwargs["platforms"]
        self.assertEqual(platforms, [{"platform": "twitter", "accountId": "acc_tw"}])

    @configured
    def test_create_manual_post_zernio_failure_records_failed(self):
        with patch.object(
            ZernioService, "list_accounts", return_value=(ZERNIO_ACCOUNTS, None)
        ), patch.object(
            ZernioService, "create_post", return_value=(None, "Social media API error: 500")
        ):
            post, error = SocialPostService.create_manual_post(
                {"caption": "Hi"}, self.admin
            )
        self.assertIsNone(post)
        self.assertIn("500", error)
        saved = SocialPost.objects.get()
        self.assertEqual(saved.status, SocialPost.STATUS_FAILED)
        self.assertTrue(saved.error)

    @configured
    def test_create_manual_post_no_matching_accounts(self):
        with patch.object(
            ZernioService, "list_accounts", return_value=(ZERNIO_ACCOUNTS, None)
        ):
            post, error = SocialPostService.create_manual_post(
                {"caption": "Hi", "account_ids": ["acc_missing"]}, self.admin
            )
        self.assertIsNone(post)
        self.assertIn("No matching", error)

    @configured
    def test_approve_post_sends_and_records_reviewer(self):
        queued = make_social_post(status=SocialPost.STATUS_PENDING_APPROVAL)
        with patch.object(
            ZernioService, "list_accounts", return_value=(ZERNIO_ACCOUNTS, None)
        ), patch.object(
            ZernioService, "create_post", return_value=({"_id": "zp_5"}, None)
        ):
            post, error = SocialPostService.approve_post(
                queued, {"caption": "Edited caption"}, self.admin
            )
        self.assertIsNone(error)
        self.assertEqual(post.status, SocialPost.STATUS_SENT)
        self.assertEqual(post.caption, "Edited caption")
        self.assertEqual(post.reviewed_by, self.admin)

    def test_approve_rejected_for_sent_post(self):
        sent = make_social_post(status=SocialPost.STATUS_SENT)
        post, error = SocialPostService.approve_post(sent, {}, self.admin)
        self.assertIsNone(post)
        self.assertIn("status", error)

    def test_reject_post(self):
        queued = make_social_post(status=SocialPost.STATUS_PENDING_APPROVAL)
        post, error = SocialPostService.reject_post(queued, self.admin)
        self.assertIsNone(error)
        self.assertEqual(post.status, SocialPost.STATUS_REJECTED)

    def test_reject_only_pending(self):
        sent = make_social_post(status=SocialPost.STATUS_SENT)
        post, error = SocialPostService.reject_post(sent, self.admin)
        self.assertIsNone(post)
        self.assertIn("status", error)

    @configured
    def test_delete_published_post_succeeds_despite_zernio_refusal(self):
        # Zernio can't delete published posts (platform owns them) — the
        # Zernio call is best-effort and must never block the local delete
        sent = make_social_post(status=SocialPost.STATUS_SENT, zernio_post_id="zp_7")
        with patch.object(
            ZernioService, "delete_post", return_value=(None, "Published posts cannot be deleted")
        ) as mock_delete:
            deleted, error = SocialPostService.delete_post(sent)
        self.assertTrue(deleted)
        self.assertIsNone(error)
        mock_delete.assert_called_once_with("zp_7")
        self.assertEqual(SocialPost.objects.count(), 0)

    @configured
    def test_delete_scheduled_post_cancels_on_zernio(self):
        from django.utils import timezone

        scheduled = make_social_post(
            status=SocialPost.STATUS_SENT,
            zernio_post_id="zp_8",
            scheduled_for=timezone.now() + timezone.timedelta(hours=2),
        )
        with patch.object(
            ZernioService, "delete_post", return_value=({}, None)
        ) as mock_delete:
            deleted, error = SocialPostService.delete_post(scheduled)
        self.assertTrue(deleted)
        mock_delete.assert_called_once_with("zp_8")
        self.assertEqual(SocialPost.objects.count(), 0)

    @configured
    def test_delete_scheduled_post_blocked_when_cancel_fails(self):
        from django.utils import timezone

        scheduled = make_social_post(
            status=SocialPost.STATUS_SENT,
            zernio_post_id="zp_9",
            scheduled_for=timezone.now() + timezone.timedelta(hours=2),
        )
        with patch.object(
            ZernioService, "delete_post", return_value=(None, "Social media service timeout")
        ):
            deleted, error = SocialPostService.delete_post(scheduled)
        self.assertFalse(deleted)
        self.assertIn("Could not cancel", error)
        self.assertEqual(SocialPost.objects.count(), 1)


class SocialApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client()
        self.admin = make_admin()
        self.user = make_user()

    def _auth(self, user):
        token = generate_jwt_token(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_endpoints_require_auth(self):
        response = self.client.get("/api/social/admin/posts")
        self.assertEqual(response.status_code, 401)

    def test_endpoints_require_admin_role(self):
        response = self.client.get("/api/social/admin/posts", **self._auth(self.user))
        self.assertEqual(response.status_code, 403)

    def test_post_list(self):
        make_social_post()
        make_social_post(status=SocialPost.STATUS_SENT)
        response = self.client.get(
            "/api/social/admin/posts?status=pending_approval", **self._auth(self.admin)
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["posts"][0]["status"], "pending_approval")

    def test_create_post_validation_error(self):
        response = self.client.post(
            "/api/social/admin/posts/create",
            data=json.dumps({"caption": ""}),
            content_type="application/json",
            **self._auth(self.admin),
        )
        self.assertEqual(response.status_code, 422)

    @configured
    def test_create_post_happy_path(self):
        with patch.object(
            ZernioService, "list_accounts", return_value=(ZERNIO_ACCOUNTS, None)
        ), patch.object(
            ZernioService, "create_post", return_value=({"_id": "zp_1"}, None)
        ):
            response = self.client.post(
                "/api/social/admin/posts/create",
                data=json.dumps({"caption": "Launching today!"}),
                content_type="application/json",
                **self._auth(self.admin),
            )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["data"]["status"], "sent")

    @configured
    def test_approve_endpoint(self):
        queued = make_social_post()
        with patch.object(
            ZernioService, "list_accounts", return_value=(ZERNIO_ACCOUNTS, None)
        ), patch.object(
            ZernioService, "create_post", return_value=({"_id": "zp_2"}, None)
        ):
            response = self.client.post(
                f"/api/social/admin/posts/{queued.id}/approve",
                data=json.dumps({}),
                content_type="application/json",
                **self._auth(self.admin),
            )
        self.assertEqual(response.status_code, 200)
        queued.refresh_from_db()
        self.assertEqual(queued.status, SocialPost.STATUS_SENT)

    def test_reject_endpoint(self):
        queued = make_social_post()
        response = self.client.post(
            f"/api/social/admin/posts/{queued.id}/reject", **self._auth(self.admin)
        )
        self.assertEqual(response.status_code, 200)
        queued.refresh_from_db()
        self.assertEqual(queued.status, SocialPost.STATUS_REJECTED)

    def test_accounts_unconfigured_returns_503(self):
        with patch.object(ZernioService, "API_KEY", ""):
            response = self.client.get(
                "/api/social/admin/accounts", **self._auth(self.admin)
            )
        self.assertEqual(response.status_code, 503)

    @configured
    def test_comments_require_published_post(self):
        queued = make_social_post()  # no zernio_post_id
        response = self.client.get(
            f"/api/social/admin/posts/{queued.id}/comments", **self._auth(self.admin)
        )
        self.assertEqual(response.status_code, 400)

    @configured
    def test_comment_reply_flow(self):
        sent = make_social_post(status=SocialPost.STATUS_SENT, zernio_post_id="zp_3")
        with patch.object(
            ZernioService, "reply_comment", return_value=({}, None)
        ) as mock_reply:
            response = self.client.post(
                f"/api/social/admin/posts/{sent.id}/comments/reply",
                data=json.dumps({"comment_id": "c1", "message": "Thanks!"}),
                content_type="application/json",
                **self._auth(self.admin),
            )
        self.assertEqual(response.status_code, 200)
        mock_reply.assert_called_once_with("zp_3", "c1", "Thanks!")

    @configured
    def test_message_send_flow(self):
        with patch.object(
            ZernioService, "send_message", return_value=({}, None)
        ) as mock_send:
            response = self.client.post(
                "/api/social/admin/inbox/conversations/conv_1/send",
                data=json.dumps({"message": "Hello there"}),
                content_type="application/json",
                **self._auth(self.admin),
            )
        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once_with("conv_1", "Hello there")
