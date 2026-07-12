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
        self.assertEqual(
            payload["mediaItems"],
            [{"type": "image", "url": "https://res.cloudinary.com/img.jpg"}],
        )
        self.assertNotIn("mediaUrls", payload)
        self.assertNotIn("scheduledFor", payload)
        self.assertTrue(mock_request.call_args.kwargs["headers"]["x-request-id"])

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
    def test_pending_post_analytics_is_not_an_error(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(
                202,
                {
                    "postId": "zp_pending",
                    "syncStatus": "pending",
                    "message": "Analytics are still syncing",
                    "analytics": {"impressions": 0, "engagementRate": 0},
                },
            )
            analytics, error = ZernioService.get_post_analytics("zp_pending")

        self.assertIsNone(error)
        self.assertEqual(analytics["syncStatus"], "pending")
        self.assertEqual(analytics["message"], "Analytics are still syncing")
        self.assertEqual(analytics["impressions"], 0)

    @configured
    def test_post_analytics_reads_nested_and_platform_metrics(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(
                200,
                {
                    "postId": "zp_analytics",
                    "analytics": {
                        "impressions": 0,
                        "reach": 0,
                        "likes": 0,
                        "comments": 0,
                        "shares": 0,
                        "clicks": 0,
                        "engagementRate": 0,
                    },
                    "platformAnalytics": [
                        {
                            "platform": "instagram",
                            "analytics": {
                                "impressions": 100,
                                "reach": 80,
                                "likes": 7,
                                "comments": 3,
                                "shares": 2,
                                "clicks": 5,
                                "engagementRate": 10.0,
                            },
                        },
                        {
                            "platform": "facebook",
                            "analytics": {
                                "impressions": 50,
                                "reach": 30,
                                "likes": 4,
                                "comments": 2,
                                "shares": 1,
                                "clicks": 0,
                                "engagementRate": 8.0,
                            },
                        },
                    ],
                    "syncStatus": "synced",
                },
            )
            analytics, error = ZernioService.get_post_analytics("zp_analytics")

        self.assertIsNone(error)
        self.assertEqual(analytics["impressions"], 150)
        self.assertEqual(analytics["reach"], 110)
        self.assertEqual(analytics["likes"], 11)
        self.assertEqual(analytics["comments"], 5)
        self.assertEqual(analytics["shares"], 3)
        self.assertEqual(analytics["clicks"], 5)
        self.assertEqual(analytics["engagement"], 24)
        self.assertEqual(analytics["engagementRate"], 9.0)

    @configured
    def test_post_analytics_accepts_account_id_and_metric_aliases(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(
                200,
                {
                    "data": {
                        "post": {
                            "summary": {
                                "impressionCount": "12",
                                "likeCount": "5",
                                "commentCount": "2",
                                "shareCount": "1",
                                "linkClicks": "4",
                            },
                            "syncStatus": "synced",
                        }
                    }
                },
            )
            analytics, error = ZernioService.get_post_analytics(
                "zp_analytics", account_id="acc_1"
            )

        self.assertIsNone(error)
        self.assertEqual(
            mock_request.call_args.kwargs["params"],
            {"postId": "zp_analytics", "accountId": "acc_1"},
        )
        self.assertEqual(analytics["impressions"], 12)
        self.assertEqual(analytics["likes"], 5)
        self.assertEqual(analytics["comments"], 2)
        self.assertEqual(analytics["shares"], 1)
        self.assertEqual(analytics["clicks"], 4)

    @configured
    def test_create_post_explicit_media_items_payload(self):
        media_items = [
            {"type": "image", "url": "https://cdn.example.com/photo.jpg", "title": "Photo"},
            {"type": "video", "url": "https://cdn.example.com/reel.mp4", "title": "Reel"},
        ]
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(201, {"post": {"_id": "zp_media"}})
            result, error = ZernioService.create_post(
                "Hello",
                [{"platform": "instagram", "accountId": "acc_ig"}],
                media_items=media_items,
            )

        self.assertIsNone(error)
        self.assertEqual(result["_id"], "zp_media")
        payload = mock_request.call_args.kwargs["json"]
        self.assertEqual(payload["mediaItems"], media_items)
        self.assertNotIn("mediaUrls", payload)

    @configured
    def test_409_surfaces_zernio_message(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(
                409, {"message": "Duplicate content: an identical post was already published"}
            )
            result, error = ZernioService.create_post("x", [])
        self.assertIsNone(result)
        self.assertIn("Duplicate content", error)

    @configured
    def test_comment_endpoints_match_current_zernio_routes(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(200, {"comments": []})
            comments, error = ZernioService.list_post_comments("zp_1", "acc_1")
            self.assertIsNone(error)
            self.assertEqual(comments, [])
            self.assertEqual(mock_request.call_args.args[0], "GET")
            self.assertTrue(mock_request.call_args.args[1].endswith("/inbox/comments/zp_1"))
            self.assertEqual(mock_request.call_args.kwargs["params"], {"accountId": "acc_1"})

            mock_request.reset_mock()
            mock_request.return_value = _response(200, {})
            ZernioService.reply_comment("zp_1", "c1", "Thanks", account_id="acc_1")
            self.assertEqual(mock_request.call_args.args[0], "POST")
            self.assertTrue(mock_request.call_args.args[1].endswith("/inbox/comments/zp_1"))
            self.assertEqual(
                mock_request.call_args.kwargs["json"],
                {"accountId": "acc_1", "commentId": "c1", "message": "Thanks"},
            )

            mock_request.reset_mock()
            ZernioService.comment_action("zp_1", "c1", "like", account_id="acc_1", cid="cid_1")
            self.assertEqual(mock_request.call_args.args[0], "POST")
            self.assertTrue(mock_request.call_args.args[1].endswith("/inbox/comments/zp_1/c1/like"))
            self.assertEqual(mock_request.call_args.kwargs["json"], {"accountId": "acc_1", "cid": "cid_1"})

            mock_request.reset_mock()
            ZernioService.comment_action("zp_1", "c1", "unlike", account_id="acc_1", like_uri="like_1")
            self.assertEqual(mock_request.call_args.args[0], "DELETE")
            self.assertTrue(mock_request.call_args.args[1].endswith("/inbox/comments/zp_1/c1/like"))
            self.assertEqual(
                mock_request.call_args.kwargs["params"],
                {"accountId": "acc_1", "likeUri": "like_1"},
            )

    @configured
    def test_nested_comment_replies_are_flattened_for_ui(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(
                200,
                {
                    "comments": [
                        {
                            "commentId": "c_parent",
                            "content": {"text": "Top-level comment"},
                            "from": {"name": "Customer"},
                            "createdAt": "2030-01-01T10:00:00Z",
                            "replies": [
                                {
                                    "commentId": "c_reply",
                                    "content": {"text": "Store reply"},
                                    "from": {"name": "Store"},
                                    "createdAt": "2030-01-01T10:05:00Z",
                                }
                            ],
                        }
                    ]
                },
            )
            comments, error = ZernioService.list_post_comments("zp_1", "acc_1")

        self.assertIsNone(error)
        self.assertEqual(len(comments), 2)
        self.assertEqual(comments[0]["id"], "c_parent")
        self.assertEqual(comments[0]["message"], "Top-level comment")
        self.assertFalse(comments[0]["isReply"])
        self.assertEqual(comments[1]["id"], "c_reply")
        self.assertEqual(comments[1]["message"], "Store reply")
        self.assertTrue(comments[1]["isReply"])
        self.assertEqual(comments[1]["parentId"], "c_parent")
        self.assertEqual(comments[1]["depth"], 1)

    @configured
    def test_message_endpoints_match_current_zernio_routes(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(200, {"messages": []})
            messages, error = ZernioService.list_messages("conv_1", "acc_1")
            self.assertIsNone(error)
            self.assertEqual(messages, [])
            self.assertEqual(mock_request.call_args.args[0], "GET")
            self.assertTrue(mock_request.call_args.args[1].endswith("/inbox/conversations/conv_1/messages"))
            self.assertEqual(mock_request.call_args.kwargs["params"], {"accountId": "acc_1"})

            mock_request.reset_mock()
            mock_request.return_value = _response(200, {})
            ZernioService.send_message("conv_1", "Hello", "acc_1")
            self.assertEqual(mock_request.call_args.args[0], "POST")
            self.assertTrue(mock_request.call_args.args[1].endswith("/inbox/conversations/conv_1/messages"))
            self.assertEqual(mock_request.call_args.kwargs["json"], {"accountId": "acc_1", "message": "Hello"})

    @configured
    def test_nested_conversation_response_is_normalized_for_chat_ui(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(200, {
                "data": {
                    "conversations": [
                        {
                            "conversationId": "conv_nested",
                            "account": {"_id": "acc_nested"},
                            "participant": {"name": "Ama Mensah"},
                            "lastMessage": {
                                "text": "Do you deliver today?",
                                "direction": "incoming",
                                "createdAt": "2030-01-01T10:00:00Z",
                            },
                        }
                    ]
                }
            })
            conversations, error = ZernioService.list_conversations()

        self.assertIsNone(error)
        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0]["id"], "conv_nested")
        self.assertEqual(conversations[0]["accountId"], "acc_nested")
        self.assertEqual(conversations[0]["participantName"], "Ama Mensah")
        self.assertEqual(conversations[0]["lastMessage"], "Do you deliver today?")
        self.assertEqual(conversations[0]["lastMessageAt"], "2030-01-01T10:00:00Z")
        self.assertFalse(conversations[0]["lastMessageIsOwn"])

    @configured
    def test_nested_message_response_is_normalized_for_chat_ui(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(200, {
                "data": {
                    "messages": [
                        {
                            "messageId": "msg_nested",
                            "content": {"text": "Yes, we deliver today."},
                            "sender": {"username": "store"},
                            "direction": "outgoing",
                            "sentAt": "2030-01-01T10:02:00Z",
                        }
                    ]
                }
            })
            messages, error = ZernioService.list_messages("conv_nested", "acc_nested")

        self.assertIsNone(error)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["id"], "msg_nested")
        self.assertEqual(messages[0]["message"], "Yes, we deliver today.")
        self.assertEqual(messages[0]["senderName"], "store")
        self.assertEqual(messages[0]["createdAt"], "2030-01-01T10:02:00Z")
        self.assertTrue(messages[0]["isOwn"])

    @configured
    def test_account_and_profile_update_methods_match_docs(self):
        with patch("apps.social.zernio_service.requests.request") as mock_request:
            mock_request.return_value = _response(200, {"account": {"_id": "acc_1"}})
            ZernioService.move_account("acc_1", "profile_1")
            self.assertEqual(mock_request.call_args.args[0], "PATCH")
            self.assertTrue(mock_request.call_args.args[1].endswith("/accounts/acc_1"))
            self.assertEqual(mock_request.call_args.kwargs["json"], {"profileId": "profile_1"})

            mock_request.reset_mock()
            mock_request.return_value = _response(200, {"profile": {"_id": "profile_1"}})
            ZernioService.update_profile("profile_1", {"name": "Retail"})
            self.assertEqual(mock_request.call_args.args[0], "PUT")
            self.assertTrue(mock_request.call_args.args[1].endswith("/profiles/profile_1"))

    @configured
    def test_connect_requires_profile_id(self):
        result, error = ZernioService.get_connect_url("instagram")
        self.assertIsNone(result)
        self.assertIn("Profile id is required", error)

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
    def test_create_manual_post_sends_multiple_media_items(self):
        media_items = [
            {"type": "image", "url": "https://cdn.example.com/photo.jpg", "title": "Photo"},
            {"type": "video", "url": "https://cdn.example.com/reel.mp4", "title": "Reel"},
        ]
        with patch.object(
            ZernioService, "list_accounts", return_value=(ZERNIO_ACCOUNTS, None)
        ), patch.object(
            ZernioService, "create_post", return_value=({"_id": "zp_media"}, None)
        ) as mock_create:
            post, error = SocialPostService.create_manual_post(
                {"caption": "Gallery", "media_items": media_items, "account_ids": ["acc_ig"]},
                self.admin,
            )

        self.assertIsNone(error)
        self.assertEqual(post.media_items, media_items)
        self.assertEqual(post.image_url, "https://cdn.example.com/photo.jpg")
        self.assertEqual(mock_create.call_args.kwargs["media_items"], media_items)

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
        media_items = [
            {"type": "image", "url": "https://cdn.example.com/photo.jpg", "title": "Photo"},
            {"type": "video", "url": "https://cdn.example.com/reel.mp4", "title": "Reel"},
        ]
        with patch.object(
            ZernioService, "list_accounts", return_value=(ZERNIO_ACCOUNTS, None)
        ), patch.object(
            ZernioService, "create_post", return_value=({"_id": "zp_1"}, None)
        ):
            response = self.client.post(
                "/api/social/admin/posts/create",
                data=json.dumps({"caption": "Launching today!", "media_items": media_items}),
                content_type="application/json",
                **self._auth(self.admin),
            )
        self.assertEqual(response.status_code, 201)
        data = response.json()["data"]
        self.assertEqual(data["status"], "sent")
        self.assertEqual(data["media_items"], media_items)
        self.assertEqual(data["image_url"], "https://cdn.example.com/photo.jpg")

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
        mock_reply.assert_called_once_with(
            "zp_3",
            "c1",
            "Thanks!",
            account_id="acc_test",
            parent_cid=None,
            root_uri=None,
            root_cid=None,
        )

    @configured
    def test_message_send_flow(self):
        with patch.object(
            ZernioService, "send_message", return_value=({}, None)
        ) as mock_send:
            response = self.client.post(
                "/api/social/admin/inbox/conversations/conv_1/send",
                data=json.dumps({"message": "Hello there", "account_id": "acc_1"}),
                content_type="application/json",
                **self._auth(self.admin),
            )
        self.assertEqual(response.status_code, 200)
        mock_send.assert_called_once_with("conv_1", "Hello there", account_id="acc_1")
