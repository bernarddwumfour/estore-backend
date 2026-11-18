"""Authenticated controls and signed delivery for the social shopping agent."""
import hashlib
import hmac
import json
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.social.models import SocialAgentAccount, SocialAgentComment, SocialAgentConversation, SocialAgentMessage, SocialAgentWorker, SocialConfig
from apps.social.zernio_service import ZernioService
from apps.social.inbox_events import publish_inbox_change
from apps.social.conversation_control import ai_available
from apps.users.decorators.auth import role_required
from estore.utils.responses import APIResponse


@csrf_exempt
@require_http_methods(["POST"])
def zernio_webhook(request):
    secret = settings.ZERNIO_WEBHOOK_SECRET
    signature = request.headers.get("X-Zernio-Signature", "")
    if not secret or not hmac.compare_digest(hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest(), signature):
        return JsonResponse({"error": "Invalid signature"}, status=403)
    try:
        event = json.loads(request.body)
        if not isinstance(event, dict): raise ValueError
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid payload"}, status=400)
    if event.get("test"):
        return JsonResponse({"ok": True})
    if event.get("event") in {"comment.received", "message.received", "message.sent", "message.edited", "message.deleted", "message.delivered", "message.read", "message.failed", "conversation.started"}:
        publish_inbox_change()
    if event.get("event") == "comment.received":
        return receive_comment(event)
    if event.get("event") != "message.received":
        return JsonResponse({"ok": True})
    if SocialConfig.test_mode_active():
        return JsonResponse({"ok": True})
    account, conversation, message = event.get("account"), event.get("conversation"), event.get("message")
    if not all(isinstance(x, dict) for x in (account, conversation, message)):
        return JsonResponse({"error": "Missing message details"}, status=400)
    event_id = event.get("id")
    account_id = account.get("accountId")
    conversation_id = conversation.get("id") or message.get("conversationId")
    text = ZernioService._message_text(message)
    sender = message.get("sender") or {}
    metadata = event.get("metadata") or {}
    if not all(isinstance(v, str) and 0 < len(v) <= 255 for v in (event_id, account_id, conversation_id)) or not isinstance(text, str) or not isinstance(sender, dict) or not isinstance(metadata, dict):
        return JsonResponse({"error": "Invalid message details"}, status=400)
    if metadata.get("standby") or sender.get("isOwnAccount") or ZernioService._message_is_outgoing(message) or message.get("isFromMe"):
        return JsonResponse({"ok": True})
    account_settings, _ = SocialAgentAccount.objects.get_or_create(account_id=account_id)
    if not account_settings.enabled:
        return JsonResponse({"ok": True})
    # Without Redis the database-backed worker picks up the persisted row.
    use_celery = bool(getattr(settings, "REDIS_URL", "") and not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))
    from apps.social.tasks import process_social_conversation
    timestamp = event.get("timestamp")
    received_at = parse_datetime(timestamp) if isinstance(timestamp, str) else None
    if received_at and timezone.is_naive(received_at): received_at = None
    with transaction.atomic():
        thread, _ = SocialAgentConversation.objects.get_or_create(account_id=account_id, conversation_id=conversation_id, defaults={"platform": str(conversation.get("platform") or account.get("platform") or "")[:40]})
        row, _ = SocialAgentMessage.objects.get_or_create(event_id=event_id, defaults={"conversation": thread, "provider_message_id": str(message.get("id") or "")[:255], "text": text[:10000], "received_at": received_at})
        if row.conversation_id != thread.pk:
            return JsonResponse({"error": "Event conflict"}, status=409)
        if row.status == "pending" and thread.platform.lower() in {"instagram", "facebook"}:
            if not received_at or received_at < timezone.now() - timedelta(hours=23) or received_at > timezone.now() + timedelta(minutes=5):
                row.status, row.error = "needs_attention", "Message is outside the automatic reply window or has no timestamp"
                row.save(update_fields=["status", "error", "updated_at"])
                thread.paused, thread.needs_attention = True, True
                thread.save(update_fields=["paused", "needs_attention", "updated_at"])
    try:
        if row.status == "pending" and use_celery: process_social_conversation.delay(thread.pk)
    except Exception:
        return JsonResponse({"error": "Could not queue message"}, status=503)
    return JsonResponse({"ok": True})


def receive_comment(event):
    if SocialConfig.test_mode_active(): return JsonResponse({"ok": True})
    account, comment, post = event.get("account"), event.get("comment"), event.get("post")
    if not all(isinstance(value, dict) for value in (account, comment, post)):
        return JsonResponse({"error": "Missing comment details"}, status=400)
    account_id = account.get("accountId") or account.get("id")
    event_id = event.get("id")
    comment_id = comment.get("id")
    post_id = comment.get("postId") or post.get("id") or comment.get("platformPostId") or post.get("platformPostId")
    platform = comment.get("platform") or account.get("platform")
    author = comment.get("author")
    text = comment.get("text")
    if not all(isinstance(v, str) and 0 < len(v) <= 255 for v in (account_id, event_id, comment_id, post_id, platform)) or not isinstance(author, dict) or not isinstance(text, str) or any(c in post_id for c in "/?#"):
        return JsonResponse({"error": "Invalid comment details"}, status=400)
    if author.get("isOwnAccount") is True:
        return JsonResponse({"ok": True})
    account_settings, _ = SocialAgentAccount.objects.get_or_create(account_id=account_id)
    if not account_settings.comments_enabled: return JsonResponse({"ok": True})
    content = post.get("content")
    defaults = {"event_id": event_id, "post_id": post_id, "text": text[:10000],
                "post_content": content[:5000] if isinstance(content, str) else ""}
    if author.get("isOwnAccount") is not False or not text.strip():
        defaults.update(status="needs_attention", error="Cannot verify comment author or text")
    row, _ = SocialAgentComment.objects.get_or_create(account_id=account_id, platform=platform.lower(), comment_id=comment_id, defaults=defaults)
    if row.status == "pending" and getattr(settings, "REDIS_URL", "") and not getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        try:
            from apps.social.tasks import process_social_comment
            process_social_comment.delay(row.pk)
        except Exception:
            return JsonResponse({"error": "Could not queue comment"}, status=503)
    return JsonResponse({"ok": True})
@csrf_exempt
@require_http_methods(["GET", "PUT"])
@role_required("admin", "staff")
@ratelimit(key="user", rate="60/h", method="PUT", block=True)
def agent_account(request, account_id):
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            if not isinstance(data, dict) or not data or set(data) - {"enabled", "comments_enabled"} or any(not isinstance(value, bool) for value in data.values()): raise ValueError
        except (ValueError, UnicodeDecodeError): return APIResponse.bad_request("A boolean enabled value is required")
        if any(data.values()):
            if not settings.ZERNIO_WEBHOOK_SECRET:
                return APIResponse.bad_request("Configure the webhook secret before enabling automatic replies")
            accounts, error = ZernioService.list_accounts(use_cache=False)
            if error: return APIResponse.bad_request("Unable to verify the connected account")
            if not any(str(a.get("id") or a.get("_id") or a.get("accountId")) == account_id for a in accounts): return APIResponse.not_found("Connected account not found")
        item, _ = SocialAgentAccount.objects.update_or_create(account_id=account_id, defaults=data)
        publish_inbox_change()
    else:
        item = SocialAgentAccount.objects.filter(account_id=account_id).first()
    worker = SocialAgentWorker.objects.filter(pk=1, last_seen__gte=timezone.now() - timedelta(minutes=2)).exists()
    return APIResponse.success({"enabled": item.enabled if item else True, "comments_enabled": item.comments_enabled if item else True,
        "configured": bool(settings.ZERNIO_WEBHOOK_SECRET),
        "queue_backend": "redis" if getattr(settings, "REDIS_URL", "") else "database",
        "worker_online": worker if not getattr(settings, "REDIS_URL", "") else None}, "Social agent account settings")


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@role_required("admin", "staff")
@ratelimit(key="user", rate="60/h", method="PUT", block=True)
def agent_conversation(request, conversation_id):
    account_id = request.GET.get("account_id", "")
    if not account_id or len(account_id) > 255: return APIResponse.bad_request("Account ID is required")
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            if not isinstance(data, dict) or not isinstance(data.get("paused"), bool): raise ValueError
        except (ValueError, UnicodeDecodeError): return APIResponse.bad_request("A boolean paused value is required")
        with transaction.atomic():
            thread, _ = SocialAgentConversation.objects.get_or_create(account_id=account_id, conversation_id=conversation_id)
            thread = SocialAgentConversation.objects.select_for_update().get(pk=thread.pk)
            if not data["paused"] and not ai_available(account_id):
                return APIResponse.bad_request("Enable the guest assistant and social AI replies before handing over to AI")
            if data["paused"] and thread.agent_messages.filter(status="sending").exists():
                return APIResponse.conflict("An AI reply is being sent. Please try again in a moment.")
            # Messages received while staff is handling the conversation were handled by staff.
            if thread.paused != data["paused"]:
                thread.agent_messages.filter(status__in=["pending", "processing"]).update(status="handed_over", error="Conversation handed over")
            thread.paused = data["paused"]
            thread.needs_attention = False
            thread.save(update_fields=["paused", "needs_attention", "updated_at"])
        publish_inbox_change()
    else:
        thread = SocialAgentConversation.objects.filter(account_id=account_id, conversation_id=conversation_id).first()
    entries = []
    if thread:
        entries = list(thread.agent_messages.order_by("-created_at").values("provider_message_id", "reply_message_id", "status", "error")[:50])
    available = ai_available(account_id)
    paused = thread.paused if thread else False
    return APIResponse.success({"paused": paused, "ai_available": available,
        "handler": "ai" if available and not paused else "staff",
        "needs_attention": thread.needs_attention if thread else False, "activity": entries}, "Social agent conversation settings")


@require_http_methods(["GET"])
@role_required("admin", "staff")
@ratelimit(key="user", rate="100/h", method="GET", block=True)
def agent_comments(request):
    account_id = request.GET.get("account_id", "")
    if not account_id or len(account_id) > 255: return APIResponse.bad_request("Account ID is required")
    records = SocialAgentComment.objects.filter(account_id=account_id).order_by("-created_at")[:50]
    return APIResponse.success({"comments": [{"id": str(c.pk), "post_id": c.post_id, "comment_id": c.comment_id,
        "text": c.text, "response": c.response, "status": c.status, "error": c.error,
        "created_at": c.created_at.isoformat()} for c in records]}, "Comment agent activity")
