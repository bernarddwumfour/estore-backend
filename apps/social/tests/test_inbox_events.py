import hashlib
import hmac
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.social.inbox_events import publish_inbox_change
from apps.social.models import SocialInboxRevision
from apps.social.stream_views import inbox_event_stream


class InboxStreamTests(TestCase):
    def test_stream_emits_when_revision_changes(self):
        stream = inbox_event_stream()
        self.assertIn("event: ready", next(stream))
        publish_inbox_change()
        self.assertIn("event: inbox.changed", next(stream))
        stream.close()

    @patch("apps.users.decorators.auth.validate_jwt_token")
    def test_stream_requires_staff(self, validate):
        user = get_user_model().objects.create_user(email="customer@example.com", password="password123")
        admin = get_user_model().objects.create_user(email="admin@example.com", password="password123", role="admin")
        validate.return_value = (True, {"type": "access", "user_id": str(user.pk)})
        self.assertEqual(self.client.get("/api/social/admin/inbox/events", HTTP_AUTHORIZATION="Bearer x").status_code, 403)
        validate.return_value = (True, {"type": "access", "user_id": str(admin.pk)})
        response = self.client.get("/api/social/admin/inbox/events", HTTP_AUTHORIZATION="Bearer x")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.streaming)
        self.assertIn(b"event: ready", next(iter(response.streaming_content)))
        response.close()

    @override_settings(ZERNIO_WEBHOOK_SECRET="secret")
    def test_signed_sent_event_notifies_without_requiring_agent_enabled(self):
        payload = json.dumps({"id": "event", "event": "message.sent"}).encode()
        signature = hmac.new(b"secret", payload, hashlib.sha256).hexdigest()
        response = self.client.post("/api/social/webhooks/zernio", data=payload, content_type="application/json", HTTP_X_ZERNIO_SIGNATURE=signature)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SocialInboxRevision.objects.get(pk=1).revision, 1)
