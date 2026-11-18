import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.social.models import SocialAgentConversation, SocialAgentMessage


class ConversationControlTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_user(email="staff@example.com", password="password123", role="admin")
        self.auth = {"HTTP_AUTHORIZATION": "Bearer token"}
        self.control = "/api/social/admin/agent/conversations/thread-1?account_id=account-1"
        self.send = "/api/social/admin/inbox/conversations/thread-1/send"
        self.payload = json.dumps({"account_id": "account-1", "message": "Hello"})

    @patch("apps.social.views.ZernioService.is_configured", return_value=True)
    @patch("apps.social.views.ZernioService.send_message", return_value=({}, None))
    @patch("apps.social.conversation_control.enabled", return_value=True)
    @patch("apps.users.decorators.auth.validate_jwt_token")
    def test_staff_must_take_over_before_sending(self, validate, enabled, send, configured):
        from django.test import override_settings
        validate.return_value = (True, {"type": "access", "user_id": str(self.admin.pk)})
        with override_settings(ZERNIO_WEBHOOK_SECRET="secret"):
            self.assertEqual(self.client.get(self.control, **self.auth).json()["data"]["handler"], "ai")
            response = self.client.post(self.send, self.payload, content_type="application/json", **self.auth)
            self.assertEqual(response.status_code, 409)
            send.assert_not_called()
            response = self.client.put(self.control, json.dumps({"paused": True}), content_type="application/json", **self.auth)
            self.assertEqual(response.json()["data"]["handler"], "staff")
            self.assertEqual(self.client.post(self.send, self.payload, content_type="application/json", **self.auth).status_code, 200)
            send.assert_called_once()
            response = self.client.put(self.control, json.dumps({"paused": False}), content_type="application/json", **self.auth)
            self.assertEqual(response.json()["data"]["handler"], "ai")
            self.assertEqual(self.client.post(self.send, self.payload, content_type="application/json", **self.auth).status_code, 409)

    @patch("apps.social.conversation_control.enabled", return_value=True)
    @patch("apps.users.decorators.auth.validate_jwt_token")
    def test_takeover_cancels_pending_ai_and_waits_for_inflight_send(self, validate, enabled):
        from django.test import override_settings
        validate.return_value = (True, {"type": "access", "user_id": str(self.admin.pk)})
        thread = SocialAgentConversation.objects.create(account_id="account-1", conversation_id="thread-1")
        message = SocialAgentMessage.objects.create(conversation=thread, event_id="event-1", text="Hi", status="sending")
        with override_settings(ZERNIO_WEBHOOK_SECRET="secret"):
            response = self.client.put(self.control, json.dumps({"paused": True}), content_type="application/json", **self.auth)
            self.assertEqual(response.status_code, 409)
            message.status = "processing"
            message.save()
            response = self.client.put(self.control, json.dumps({"paused": True}), content_type="application/json", **self.auth)
            self.assertEqual(response.status_code, 200)
            message.refresh_from_db()
            self.assertEqual(message.status, "handed_over")

    @patch("apps.social.conversation_control.enabled", return_value=False)
    @patch("apps.users.decorators.auth.validate_jwt_token")
    def test_disabled_ai_defaults_to_staff(self, validate, enabled):
        from django.test import override_settings
        validate.return_value = (True, {"type": "access", "user_id": str(self.admin.pk)})
        with override_settings(ZERNIO_WEBHOOK_SECRET="secret"):
            self.assertEqual(self.client.get(self.control, **self.auth).json()["data"]["handler"], "staff")
            self.assertEqual(self.client.put(self.control, json.dumps({"paused": False}), content_type="application/json", **self.auth).status_code, 400)
