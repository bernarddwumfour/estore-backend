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

from apps.social.models import SocialAgentAccount, SocialAgentConversation, SocialAgentMessage, SocialAgentWorker, SocialConfig
from apps.social.zernio_service import ZernioService
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
    if event.get("event") != "message.received" or event.get("test"):
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
    if not SocialAgentAccount.objects.filter(account_id=account_id, enabled=True).exists():
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


@csrf_exempt
@require_http_methods(["GET", "PUT"])
@role_required("admin", "staff")
@ratelimit(key="user", rate="60/h", method="PUT", block=True)
def agent_account(request, account_id):
    if request.method == "PUT":
        try:
            data = json.loads(request.body)
            if not isinstance(data, dict) or not isinstance(data.get("enabled"), bool): raise ValueError
        except (ValueError, UnicodeDecodeError): return APIResponse.bad_request("A boolean enabled value is required")
        if data["enabled"]:
            if not settings.ZERNIO_WEBHOOK_SECRET:
                return APIResponse.bad_request("Configure the webhook secret before enabling automatic replies")
            accounts, error = ZernioService.list_accounts(use_cache=False)
            if error: return APIResponse.bad_request("Unable to verify the connected account")
            if not any(str(a.get("id") or a.get("_id") or a.get("accountId")) == account_id for a in accounts): return APIResponse.not_found("Connected account not found")
        item, _ = SocialAgentAccount.objects.update_or_create(account_id=account_id, defaults={"enabled": data["enabled"]})
    else:
        item = SocialAgentAccount.objects.filter(account_id=account_id).first()
    worker = SocialAgentWorker.objects.filter(pk=1, last_seen__gte=timezone.now() - timedelta(minutes=2)).exists()
    return APIResponse.success({"enabled": item.enabled if item else False,
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
        thread, _ = SocialAgentConversation.objects.update_or_create(account_id=account_id, conversation_id=conversation_id, defaults={"paused": data["paused"], "needs_attention": False})
    else:
        thread = SocialAgentConversation.objects.filter(account_id=account_id, conversation_id=conversation_id).first()
    entries = []
    if thread:
        entries = list(thread.agent_messages.order_by("-created_at").values("provider_message_id", "reply_message_id", "status", "error")[:50])
    return APIResponse.success({"paused": thread.paused if thread else False, "needs_attention": thread.needs_attention if thread else False, "activity": entries}, "Social agent conversation settings")
