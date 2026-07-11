import json

from django.test import Client, TestCase

from apps.social.models import (
    SandboxComment,
    SandboxConversation,
    SocialConfig,
    SocialPost,
)
from apps.social.services import SocialPostService
from apps.social.tests.factories import make_admin, make_user
from apps.social.zernio_service import ZernioService
from apps.users.utils.token_utils import generate_jwt_token


def enable_test_mode():
    config = SocialConfig.get()
    config.mode = SocialConfig.MODE_TEST
    config.save()


class SandboxModeTests(TestCase):
    """End-to-end flows in test mode — no API key, no HTTP."""

    def setUp(self):
        enable_test_mode()
        self.admin = make_admin()

    def test_is_configured_without_key(self):
        self.assertTrue(ZernioService.is_configured())

    def test_list_accounts_returns_sandbox_accounts(self):
        accounts, error = ZernioService.list_accounts()
        self.assertIsNone(error)
        self.assertEqual(len(accounts), 3)  # auto-seeded demo accounts
        self.assertTrue(all(a["profileId"] for a in accounts))

    def test_create_manual_post_and_comments_flow(self):
        post, error = SocialPostService.create_manual_post(
            {"caption": "Sandbox hello"}, self.admin
        )
        self.assertIsNone(error)
        self.assertEqual(post.status, SocialPost.STATUS_SENT)
        self.assertTrue(post.zernio_post_id.startswith("sandbox_"))

        # posting seeds fake comments to interact with
        comments, error = ZernioService.list_post_comments(post.zernio_post_id)
        self.assertIsNone(error)
        self.assertGreater(len(comments), 0)

        # reply, like and hide behave like the real inbox
        _, error = ZernioService.reply_comment(
            post.zernio_post_id, comments[0]["_id"], "Thanks!"
        )
        self.assertIsNone(error)
        _, error = ZernioService.comment_action(
            post.zernio_post_id, comments[0]["_id"], "hide"
        )
        self.assertIsNone(error)
        # hidden comments stay visible on the dashboard (flagged) so the
        # admin can unhide them; they are only hidden from customers
        remaining, _ = ZernioService.list_post_comments(post.zernio_post_id)
        by_id = {c["_id"]: c for c in remaining}
        self.assertIn(comments[0]["_id"], by_id)
        self.assertTrue(by_id[comments[0]["_id"]]["hidden"])
        self.assertTrue(any(c["isReply"] for c in remaining))

        _, error = ZernioService.comment_action(
            post.zernio_post_id, comments[0]["_id"], "unhide"
        )
        self.assertIsNone(error)
        remaining, _ = ZernioService.list_post_comments(post.zernio_post_id)
        by_id = {c["_id"]: c for c in remaining}
        self.assertFalse(by_id[comments[0]["_id"]]["hidden"])

    def test_conversations_and_messages_flow(self):
        conversations, error = ZernioService.list_conversations()
        self.assertIsNone(error)
        self.assertGreater(len(conversations), 0)  # demo data auto-seeded
        # messenger-style list metadata
        self.assertIn("lastMessage", conversations[0])
        self.assertIn("lastMessageAt", conversations[0])
        self.assertTrue(conversations[0]["lastMessage"])

        conversation_id = conversations[0]["_id"]
        messages, error = ZernioService.list_messages(conversation_id)
        self.assertIsNone(error)
        self.assertGreater(len(messages), 0)

        _, error = ZernioService.send_message(conversation_id, "On it!")
        self.assertIsNone(error)
        messages, _ = ZernioService.list_messages(conversation_id)
        self.assertTrue(messages[-1]["isOwn"])
        self.assertEqual(messages[-1]["message"], "On it!")

    def test_delete_post_removes_sandbox_comments(self):
        post, _ = SocialPostService.create_manual_post(
            {"caption": "To be deleted"}, self.admin
        )
        self.assertTrue(
            SandboxComment.objects.filter(zernio_post_id=post.zernio_post_id).exists()
        )
        deleted, error = SocialPostService.delete_post(post)
        self.assertTrue(deleted)
        self.assertFalse(
            SandboxComment.objects.filter(zernio_post_id=post.zernio_post_id).exists()
        )


class SocialConfigApiTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin = make_admin()
        self.user = make_user()

    def _auth(self, user):
        token = generate_jwt_token(user)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_get_config_defaults_to_live(self):
        response = self.client.get("/api/social/admin/config", **self._auth(self.admin))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["mode"], "live")

    def test_switch_to_test_mode_seeds_demo_conversations(self):
        response = self.client.post(
            "/api/social/admin/config",
            data=json.dumps({"mode": "test"}),
            content_type="application/json",
            **self._auth(self.admin),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["mode"], "test")
        self.assertTrue(SocialConfig.test_mode_active())
        self.assertTrue(SandboxConversation.objects.exists())

    def test_invalid_mode_rejected(self):
        response = self.client.post(
            "/api/social/admin/config",
            data=json.dumps({"mode": "staging"}),
            content_type="application/json",
            **self._auth(self.admin),
        )
        self.assertEqual(response.status_code, 422)

    def test_config_requires_admin(self):
        response = self.client.get("/api/social/admin/config", **self._auth(self.user))
        self.assertEqual(response.status_code, 403)


class SandboxAnalyticsAndDeleteTests(TestCase):
    def setUp(self):
        enable_test_mode()
        self.admin = make_admin()

    def test_post_analytics_shape_and_determinism(self):
        post, _ = SocialPostService.create_manual_post(
            {"caption": "Analytics test"}, self.admin
        )
        analytics, error = ZernioService.get_post_analytics(post.zernio_post_id)
        self.assertIsNone(error)
        for key in ("impressions", "reach", "engagement", "likes", "comments", "shares", "clicks"):
            self.assertIn(key, analytics)
        # deterministic per post id
        again, _ = ZernioService.get_post_analytics(post.zernio_post_id)
        self.assertEqual(analytics["impressions"], again["impressions"])
        # comment count reflects seeded sandbox comments
        self.assertGreater(analytics["comments"], 0)

    def test_delete_comment_action(self):
        post, _ = SocialPostService.create_manual_post(
            {"caption": "Delete comment test"}, self.admin
        )
        comments, _ = ZernioService.list_post_comments(post.zernio_post_id)
        target = comments[0]["_id"]
        _, error = ZernioService.comment_action(post.zernio_post_id, target, "delete")
        self.assertIsNone(error)
        remaining, _ = ZernioService.list_post_comments(post.zernio_post_id)
        self.assertNotIn(target, {c["_id"] for c in remaining})

    def test_analytics_endpoint(self):
        client = Client()
        token = generate_jwt_token(self.admin)
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        post, _ = SocialPostService.create_manual_post(
            {"caption": "Endpoint analytics"}, self.admin
        )
        response = client.get(
            f"/api/social/admin/posts/{post.id}/analytics", **auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("impressions", response.json()["data"]["analytics"])

    def test_post_list_date_filter(self):
        client = Client()
        token = generate_jwt_token(self.admin)
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        SocialPostService.create_manual_post({"caption": "Filter me"}, self.admin)
        response = client.get(
            "/api/social/admin/posts?date_from=2020-01-01&date_to=2099-12-31", **auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["total"], 1)
        response = client.get(
            "/api/social/admin/posts?date_to=2020-01-01", **auth
        )
        self.assertEqual(response.json()["data"]["total"], 0)
        # malformed dates are ignored rather than erroring
        response = client.get(
            "/api/social/admin/posts?date_from=garbage", **auth
        )
        self.assertEqual(response.status_code, 200)


class SandboxConfigManagementTests(TestCase):
    """Profiles, account management and usage in test mode."""

    def setUp(self):
        enable_test_mode()
        self.admin = make_admin()
        self.client = Client()

    def _auth(self):
        token = generate_jwt_token(self.admin)
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def test_profile_crud_roundtrip(self):
        profiles, error = ZernioService.list_profiles()
        self.assertIsNone(error)
        self.assertEqual(len(profiles), 1)  # seeded Default

        created, error = ZernioService.create_profile("Campaigns", "Promo accounts")
        self.assertIsNone(error)

        updated, error = ZernioService.update_profile(created["_id"], {"name": "Ads"})
        self.assertIsNone(error)
        self.assertEqual(updated["name"], "Ads")

        _, error = ZernioService.delete_profile(created["_id"])
        self.assertIsNone(error)
        profiles, _ = ZernioService.list_profiles()
        self.assertEqual(len(profiles), 1)

    def test_delete_profile_keeps_accounts(self):
        from apps.social.models import SandboxAccount, SandboxProfile

        accounts, _ = ZernioService.list_accounts()
        default_profile_id = accounts[0]["profileId"]
        _, error = ZernioService.delete_profile(default_profile_id)
        self.assertIsNone(error)
        self.assertEqual(SandboxProfile.objects.count(), 0)
        # accounts survive, just unassigned
        self.assertEqual(SandboxAccount.objects.count(), 3)
        accounts, _ = ZernioService.list_accounts()
        self.assertTrue(all(a["profileId"] is None for a in accounts))

    def test_connect_disconnect_and_move(self):
        result, error = ZernioService.get_connect_url("tiktok")
        self.assertIsNone(error)
        self.assertTrue(result["connected"])
        account_id = result["account"]["_id"]

        accounts, _ = ZernioService.list_accounts()
        self.assertIn(account_id, {a["_id"] for a in accounts})

        profile, _ = ZernioService.create_profile("Video", "")
        moved, error = ZernioService.move_account(account_id, profile["_id"])
        self.assertIsNone(error)
        self.assertEqual(moved["profileId"], profile["_id"])

        _, error = ZernioService.disconnect_account(account_id)
        self.assertIsNone(error)
        accounts, _ = ZernioService.list_accounts()
        self.assertNotIn(account_id, {a["_id"] for a in accounts})

    def test_usage_stats_shape(self):
        stats, error = ZernioService.get_usage_stats()
        self.assertIsNone(error)
        for key in ("plan", "accounts_connected", "accounts_limit", "posts_this_month", "posts_limit", "profiles"):
            self.assertIn(key, stats)
        self.assertEqual(stats["accounts_connected"], 3)

    def test_profiles_endpoint_crud(self):
        response = self.client.get("/api/social/admin/profiles", **self._auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["data"]["profiles"]), 1)

        response = self.client.post(
            "/api/social/admin/profiles",
            data=json.dumps({"name": "Retail"}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 201)
        profile_id = response.json()["data"]["profile"]["_id"]

        response = self.client.patch(
            f"/api/social/admin/profiles/{profile_id}",
            data=json.dumps({"name": "Retail GH"}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["profile"]["name"], "Retail GH")

        response = self.client.delete(
            f"/api/social/admin/profiles/{profile_id}", **self._auth()
        )
        self.assertEqual(response.status_code, 200)

    def test_profile_create_validation(self):
        response = self.client.post(
            "/api/social/admin/profiles",
            data=json.dumps({"name": ""}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 422)

    def test_connect_endpoint_test_mode(self):
        response = self.client.post(
            "/api/social/admin/accounts/connect",
            data=json.dumps({"platform": "pinterest"}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["data"]["connected"])

    def test_connect_endpoint_invalid_platform(self):
        response = self.client.post(
            "/api/social/admin/accounts/connect",
            data=json.dumps({"platform": "myspace"}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 422)

    def test_disconnect_and_move_endpoints(self):
        accounts, _ = ZernioService.list_accounts()
        account_id = accounts[0]["_id"]
        profile, _ = ZernioService.create_profile("Other", "")

        response = self.client.post(
            f"/api/social/admin/accounts/{account_id}/move",
            data=json.dumps({"profile_id": profile["_id"]}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)

        response = self.client.delete(
            f"/api/social/admin/accounts/{account_id}/disconnect", **self._auth()
        )
        self.assertEqual(response.status_code, 200)

    def test_usage_endpoint(self):
        response = self.client.get("/api/social/admin/usage", **self._auth())
        self.assertEqual(response.status_code, 200)
        self.assertIn("accounts_connected", response.json()["data"]["usage"])
