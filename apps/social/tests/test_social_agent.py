import hashlib
import hmac
import json
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.management import call_command

from apps.social.models import SocialAgentAccount, SocialAgentConversation, SocialAgentMessage
from apps.social.tasks import process_social_conversation
from django.contrib.auth import get_user_model


@override_settings(ZERNIO_WEBHOOK_SECRET="test-secret", REDIS_URL="redis://example", CELERY_TASK_ALWAYS_EAGER=False)
class SocialAgentTests(TestCase):
    def setUp(self):
        SocialAgentAccount.objects.create(account_id="account-1", enabled=True)
        self.event = {"id": "event-1", "event": "message.received", "timestamp": timezone.now().isoformat(),
                      "account": {"accountId": "account-1", "platform": "instagram"},
                      "conversation": {"id": "thread-1", "platform": "instagram"},
                      "message": {"id": "message-1", "text": "Show me phones", "sender": {"id": "customer"}}}

    def post_event(self, event=None, signature=None):
        body = json.dumps(event or self.event).encode()
        signature = signature or hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        return self.client.post("/api/social/webhooks/zernio", data=body, content_type="application/json", HTTP_X_ZERNIO_SIGNATURE=signature)

    @patch("apps.social.tasks.process_social_conversation.delay")
    def test_signature_deduplication_and_queue(self, enqueue):
        self.assertEqual(self.post_event(signature="bad").status_code, 403)
        self.assertEqual(self.post_event().status_code, 200)
        self.assertEqual(self.post_event().status_code, 200)
        self.assertEqual(SocialAgentMessage.objects.count(), 1)
        self.assertEqual(enqueue.call_count, 2)

    @patch("apps.social.tasks.process_social_conversation.delay")
    def test_outgoing_and_standby_are_ignored(self, enqueue):
        self.event["message"]["isOwn"] = True
        self.assertEqual(self.post_event().status_code, 200)
        self.event["message"].pop("isOwn")
        self.event["metadata"] = {"standby": True}
        self.assertEqual(self.post_event().status_code, 200)
        self.assertFalse(SocialAgentMessage.objects.exists())
        enqueue.assert_not_called()

    @patch("apps.social.tasks.enabled", return_value=True)
    @patch("apps.social.tasks.AssistantService.send_guest_message")
    @patch("apps.social.tasks.ZernioService.send_message", return_value=({}, None))
    def test_reply_once_and_human_handoff(self, send, agent, enabled):
        thread = SocialAgentConversation.objects.create(account_id="account-1", conversation_id="thread-1")
        message = SocialAgentMessage.objects.create(conversation=thread, event_id="event-1", text="Hello")
        agent.return_value = {"response": "Hello!", "products": []}
        process_social_conversation(thread.pk)
        process_social_conversation(thread.pk)
        message.refresh_from_db()
        self.assertEqual(message.status, "sent")
        send.assert_called_once()
        SocialAgentMessage.objects.create(conversation=thread, event_id="event-2", text="I want to speak to a human")
        process_social_conversation(thread.pk)
        thread.refresh_from_db()
        self.assertTrue(thread.paused and thread.needs_attention)
        send.assert_called_once()

    @patch("apps.social.tasks.enabled", return_value=True)
    @patch("apps.social.tasks.AssistantService.send_guest_message", return_value={"response": "Hello", "products": []})
    @patch("apps.social.tasks.ZernioService.send_message", return_value=(None, "timeout"))
    def test_uncertain_send_is_not_retried(self, send, agent, enabled):
        thread = SocialAgentConversation.objects.create(account_id="account-1", conversation_id="thread-1")
        row = SocialAgentMessage.objects.create(conversation=thread, event_id="event-1", text="Hello")
        process_social_conversation(thread.pk)
        process_social_conversation(thread.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, "needs_attention")
        send.assert_called_once()

    @patch("apps.social.tasks.enabled", return_value=False)
    @patch("apps.social.tasks.AssistantService.send_guest_message")
    def test_disabled_guest_agent_does_not_reply(self, agent, enabled):
        thread = SocialAgentConversation.objects.create(account_id="account-1", conversation_id="thread-1")
        row = SocialAgentMessage.objects.create(conversation=thread, event_id="event-1", text="Hello")
        process_social_conversation(thread.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, "pending")
        agent.assert_not_called()

    @patch("apps.users.decorators.auth.validate_jwt_token")
    def test_agent_controls_require_staff(self, validate):
        user = get_user_model().objects.create_user(email="customer@example.com", password="password123")
        validate.return_value = (True, {"type": "access", "user_id": str(user.pk)})
        response = self.client.put("/api/social/admin/agent/accounts/account-1", data=json.dumps({"enabled": False}), content_type="application/json", HTTP_AUTHORIZATION="Bearer test")
        self.assertEqual(response.status_code, 403)
        self.assertTrue(SocialAgentAccount.objects.get(account_id="account-1").enabled)

    @override_settings(REDIS_URL="", CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.social.tasks.process_social_conversation.delay")
    def test_database_queue_never_runs_inline(self, enqueue):
        self.assertEqual(self.post_event().status_code, 200)
        self.assertEqual(SocialAgentMessage.objects.get().status, "pending")
        enqueue.assert_not_called()

    @override_settings(REDIS_URL="", CELERY_TASK_ALWAYS_EAGER=True)
    @patch("apps.social.tasks.enabled", return_value=True)
    @patch("apps.social.tasks.AssistantService.send_guest_message", return_value={"response": "Hello", "products": []})
    @patch("apps.social.tasks.ZernioService.send_message", return_value=({}, None))
    def test_database_worker_processes_queued_messages(self, send, agent, enabled):
        self.post_event()
        call_command("run_social_agent_worker", once=True)
        self.assertEqual(SocialAgentMessage.objects.get().status, "sent")
        send.assert_called_once()
