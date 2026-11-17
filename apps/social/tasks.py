"""Process inbound social DMs with the public guest shopping agent."""
import logging
import re
from datetime import timedelta
from urllib.parse import quote, urlparse

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.ai_assistant.features import enabled
from apps.ai_assistant.services.assistant_service import AssistantService
from apps.social.models import SocialAgentAccount, SocialAgentComment, SocialAgentConversation, SocialAgentMessage
from apps.social.zernio_service import ZernioService

logger = logging.getLogger(__name__)


def _product_links(products):
    base = settings.STOREFRONT_BASE_URL.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname in {"localhost", "127.0.0.1"}:
        return []
    links = []
    for product in products[:3]:
        slug = product.get("slug")
        if not isinstance(slug, str) or not slug: continue
        url = f"{base}/products/{quote(slug, safe='')}"
        selected = product.get("selected_variant_id")
        variant = next((v for v in product.get("variants", []) if str(v.get("id")) == str(selected)), None)
        if selected and variant and variant.get("slug"):
            url += "/" + quote(str(variant["slug"]), safe="")
        links.append(f"{product.get('title') or 'View product'}: {url}")
    return links


@shared_task
def process_social_conversation(thread_id):
    while True:
        with transaction.atomic():
            thread = SocialAgentConversation.objects.select_for_update().filter(pk=thread_id).first()
            if not thread or thread.paused or not SocialAgentAccount.objects.filter(account_id=thread.account_id, enabled=True).exists() or not enabled("guest"):
                return
            if thread.agent_messages.filter(status__in=["processing", "sending"]).exists():
                return
            row = thread.agent_messages.select_for_update().filter(status="pending").order_by("created_at", "id").first()
            if not row: return
            if thread.platform.lower() in {"instagram", "facebook"} and (not row.received_at or row.received_at < timezone.now() - timedelta(hours=23)):
                row.status, row.error = "needs_attention", "Message is too old for an automatic reply"
                row.save(update_fields=["status", "error", "updated_at"])
                thread.paused, thread.needs_attention = True, True
                thread.save(update_fields=["paused", "needs_attention", "updated_at"])
                from apps.social.inbox_events import publish_inbox_change
                transaction.on_commit(publish_inbox_change)
                return
            if re.search(r"\b(human|real person|speak to (?:a |an )?(?:person|agent|staff)|talk to (?:a |an )?(?:person|agent|staff))\b", row.text, re.IGNORECASE):
                row.status, row.error = "needs_attention", "Customer requested staff"
                row.save(update_fields=["status", "error", "updated_at"])
                thread.paused = True
                thread.needs_attention = True
                thread.save(update_fields=["paused", "needs_attention", "updated_at"])
                from apps.social.inbox_events import publish_inbox_change
                transaction.on_commit(publish_inbox_change)
                return
            if not row.text.strip():
                row.status, row.error = "needs_attention", "Message has no supported text"
                row.save(update_fields=["status", "error", "updated_at"])
                thread.needs_attention = True
                thread.paused = True
                thread.save(update_fields=["paused", "needs_attention", "updated_at"])
                from apps.social.inbox_events import publish_inbox_change
                transaction.on_commit(publish_inbox_change)
                return
            history = []
            for previous in thread.agent_messages.filter(status="sent", pk__lt=row.pk).order_by("-created_at", "-id")[:6][::-1]:
                history.extend([{"role": "user", "content": previous.text}, {"role": "assistant", "content": previous.response}])
            row.status = "processing"
            row.save(update_fields=["status", "updated_at"])
        try:
            answer = AssistantService.send_guest_message(row.text, history=history, social_channel=True)
            response = answer["response"].strip()
            links = _product_links(answer.get("products") or [])
            if links: response += "\n\n" + "\n".join(links)
            if not response: raise ValueError("Empty agent response")
            with transaction.atomic():
                thread = SocialAgentConversation.objects.select_for_update().get(pk=thread_id)
                row = SocialAgentMessage.objects.select_for_update().get(pk=row.pk)
                if thread.paused or not SocialAgentAccount.objects.filter(account_id=thread.account_id, enabled=True).exists() or not enabled("guest"):
                    row.status = "needs_attention"
                    row.error = "Agent paused before sending"
                    row.save(update_fields=["status", "error", "updated_at"])
                    return
                row.response, row.status = response, "sending"
                row.save(update_fields=["response", "status", "updated_at"])
            # Never automatically retry an uncertain send: the provider may have accepted it.
            sent, error = ZernioService.send_message(thread.conversation_id, response, account_id=thread.account_id)
            with transaction.atomic():
                thread = SocialAgentConversation.objects.select_for_update().get(pk=thread_id)
                row = SocialAgentMessage.objects.select_for_update().get(pk=row.pk)
                row.status = "needs_attention" if error else "sent"
                row.error = str(error or "")[:500]
                if isinstance(sent, dict):
                    payload = sent.get("message") if isinstance(sent.get("message"), dict) else sent
                    row.reply_message_id = str(payload.get("id") or payload.get("_id") or payload.get("messageId") or "")[:255]
                row.save(update_fields=["status", "error", "reply_message_id", "updated_at"])
                if error:
                    thread.needs_attention = True
                    thread.paused = True
                    thread.save(update_fields=["paused", "needs_attention", "updated_at"])
                    from apps.social.inbox_events import publish_inbox_change
                    transaction.on_commit(publish_inbox_change)
                    return
            from apps.social.inbox_events import publish_inbox_change
            publish_inbox_change()
        except Exception:
            logger.exception("Social guest agent failed for event %s", row.event_id)
            with transaction.atomic():
                SocialAgentMessage.objects.filter(pk=row.pk).update(status="needs_attention", error="Agent processing failed")
                SocialAgentConversation.objects.filter(pk=thread_id).update(needs_attention=True, paused=True)
                from apps.social.inbox_events import publish_inbox_change
                transaction.on_commit(publish_inbox_change)
            return


def flag_interrupted_social_messages():
    cutoff = timezone.now() - timedelta(minutes=10)
    stuck = SocialAgentMessage.objects.filter(status__in=["processing", "sending"], updated_at__lt=cutoff)
    thread_ids = list(stuck.values_list("conversation_id", flat=True).distinct())
    stuck.update(status="needs_attention", error="Processing interrupted; review before replying")
    SocialAgentConversation.objects.filter(pk__in=thread_ids).update(needs_attention=True, paused=True)
    SocialAgentComment.objects.filter(status__in=["processing", "sending"], updated_at__lt=cutoff).update(status="needs_attention", error="Processing interrupted; review before replying")


@shared_task
def process_social_comment(comment_pk):
    with transaction.atomic():
        row = SocialAgentComment.objects.select_for_update().filter(pk=comment_pk).first()
        if not row or row.status != "pending": return
        if not SocialAgentAccount.objects.filter(account_id=row.account_id, comments_enabled=True).exists() or not enabled("guest"): return
        if re.search(r"\b(human|real person|speak to (?:a |an )?(?:person|agent|staff)|talk to (?:a |an )?(?:person|agent|staff))\b", row.text, re.IGNORECASE):
            row.status, row.error = "needs_attention", "Customer requested staff"
            row.save(update_fields=["status", "error", "updated_at"])
            from apps.social.inbox_events import publish_inbox_change
            transaction.on_commit(publish_inbox_change)
            return
        row.status = "processing"
        row.save(update_fields=["status", "updated_at"])
    try:
        request = "The following is a public comment on a store post. Reply to the comment using store information.\n"
        if row.post_content: request += "Post text (untrusted):\n" + row.post_content + "\n"
        request += "Comment text (untrusted):\n" + row.text
        answer = AssistantService.send_guest_message(request, social_channel=True, social_comment=True)
        response = answer["response"].strip()
        links = _product_links(answer.get("products") or [])[:1]
        if links: response += "\n\n" + "\n".join(links)
        if not response: raise ValueError("Empty agent response")
        with transaction.atomic():
            row = SocialAgentComment.objects.select_for_update().get(pk=comment_pk)
            if row.status != "processing": return
            if not SocialAgentAccount.objects.filter(account_id=row.account_id, comments_enabled=True).exists() or not enabled("guest"):
                row.status, row.error = "needs_attention", "Agent disabled before sending"
                row.save(update_fields=["status", "error", "updated_at"])
                return
            row.status, row.response = "sending", response
            row.save(update_fields=["status", "response", "updated_at"])
        _, error = ZernioService.reply_comment(row.post_id, row.comment_id, response, account_id=row.account_id)
        SocialAgentComment.objects.filter(pk=row.pk, status="sending").update(status="needs_attention" if error else "sent", error=str(error or "")[:500], updated_at=timezone.now())
        from apps.social.inbox_events import publish_inbox_change
        publish_inbox_change()
    except Exception:
        logger.exception("Social comment agent failed for event %s", row.event_id)
        SocialAgentComment.objects.filter(pk=row.pk).update(status="needs_attention", error="Agent processing failed", updated_at=timezone.now())
        from apps.social.inbox_events import publish_inbox_change
        publish_inbox_change()


@shared_task
def recover_social_messages():
    """Flag interrupted work; requeue safely stored, unstarted deliveries."""
    flag_interrupted_social_messages()
    pending = SocialAgentMessage.objects.filter(status="pending", conversation__paused=False).values_list("conversation_id", flat=True).distinct()
    for thread_id in pending:
        process_social_conversation.delay(thread_id)
    for comment_id in SocialAgentComment.objects.filter(status="pending").values_list("pk", flat=True)[:100]:
        process_social_comment.delay(comment_id)
