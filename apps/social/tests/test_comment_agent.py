import hashlib
import hmac
import json
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.social.models import SocialAgentAccount, SocialAgentComment
from apps.social.tasks import process_social_comment


@override_settings(ZERNIO_WEBHOOK_SECRET="secret", REDIS_URL="", CELERY_TASK_ALWAYS_EAGER=True)
class CommentAgentTests(TestCase):
    def setUp(self):
        self.event = {"id": "event-1", "event": "comment.received", "account": {"accountId": "a", "platform": "instagram"},
                      "post": {"id": None, "platformPostId": "native-post", "content": "Phones"},
                      "comment": {"id": "comment-1", "platform": "instagram", "text": "How much?", "author": {"id": "customer", "isOwnAccount": False}}}

    def post_event(self):
        body = json.dumps(self.event).encode()
        signature = hmac.new(b"secret", body, hashlib.sha256).hexdigest()
        return self.client.post("/api/social/webhooks/zernio", data=body, content_type="application/json", HTTP_X_ZERNIO_SIGNATURE=signature)

    @patch("apps.social.tasks.enabled", return_value=True)
    @patch("apps.social.tasks.AssistantService.send_guest_message", return_value={"response": "Hello!", "products": []})
    @patch("apps.social.tasks.ZernioService.reply_comment", return_value=({}, None))
    def test_incoming_is_deduplicated_and_worker_replies_once(self, reply, agent, enabled):
        self.assertEqual(self.post_event().status_code, 200)
        self.event["id"] = "event-2"
        self.assertEqual(self.post_event().status_code, 200)
        self.assertEqual(SocialAgentComment.objects.count(), 1)
        call_command("run_social_agent_worker", once=True)
        row = SocialAgentComment.objects.get()
        self.assertEqual(row.status, "sent")
        reply.assert_called_once_with("native-post", "comment-1", "Hello!", account_id="a")
        self.assertTrue(agent.call_args.kwargs["social_comment"])
        process_social_comment(row.pk)
        reply.assert_called_once()

    def test_own_comment_ignored_and_unknown_author_flagged(self):
        self.event["comment"]["author"]["isOwnAccount"] = True
        self.post_event()
        self.assertFalse(SocialAgentComment.objects.exists())
        del self.event["comment"]["author"]["isOwnAccount"]
        self.post_event()
        self.assertEqual(SocialAgentComment.objects.get().status, "needs_attention")

    def test_comments_can_be_disabled_independently(self):
        SocialAgentAccount.objects.create(account_id="a", enabled=True, comments_enabled=False)
        self.post_event()
        self.assertFalse(SocialAgentComment.objects.exists())

    @patch("apps.social.tasks.enabled", return_value=True)
    @patch("apps.social.tasks.AssistantService.send_guest_message", return_value={"response": "Hello", "products": []})
    @patch("apps.social.tasks.ZernioService.reply_comment", return_value=(None, "timeout"))
    def test_uncertain_reply_is_not_retried(self, reply, agent, enabled):
        self.post_event()
        row = SocialAgentComment.objects.get()
        process_social_comment(row.pk)
        process_social_comment(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, "needs_attention")
        reply.assert_called_once()
