"""
Social services — write logic for social posts (compose, approve, reject, delete).

All Zernio HTTP calls happen synchronously here on admin action; the approval
queue means nothing is time-critical.
"""

import logging
from typing import Dict, List, Optional, Tuple

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.social.captions import (
    build_product_caption,
    build_promotion_caption,
    get_product_image_url,
    get_promotion_image_url,
)
from apps.social.models import SocialPost
from apps.social.zernio_service import ZernioService

logger = logging.getLogger(__name__)


class SocialPostService:
    """Write operations for social posts"""

    @staticmethod
    def resolve_platforms(
        account_ids: Optional[List[str]] = None,
    ) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """Build the Zernio platforms payload from connected accounts.

        Posts to all connected accounts by default, optionally filtered by the
        ZERNIO_PLATFORMS setting and/or an explicit account_ids selection.
        """
        accounts, error = ZernioService.list_accounts()
        if error:
            return None, error

        allowed_platforms = getattr(settings, 'ZERNIO_PLATFORMS', [])
        platforms = []
        for account in accounts:
            account_id = account.get("_id") or account.get("id")
            platform = account.get("platform")
            if not account_id or not platform:
                continue
            if allowed_platforms and platform not in allowed_platforms:
                continue
            if account_ids and account_id not in account_ids:
                continue
            platforms.append({"platform": platform, "accountId": account_id})

        if not platforms:
            return None, "No matching connected social accounts found"
        return platforms, None

    @staticmethod
    def _send_to_zernio(post: SocialPost, user) -> Tuple[Optional[SocialPost], Optional[str]]:
        """Send a SocialPost to Zernio and record the outcome on the row."""
        media_urls = [post.image_url] if post.image_url else None
        scheduled_for = (
            post.scheduled_for.isoformat() if post.scheduled_for else None
        )

        result, error = ZernioService.create_post(
            content=post.caption,
            platforms=post.platforms,
            media_urls=media_urls,
            scheduled_for=scheduled_for,
        )

        if error:
            post.status = SocialPost.STATUS_FAILED
            post.error = error[:255]
            post.save(update_fields=["status", "error", "updated_at"])
            return None, error

        post.status = SocialPost.STATUS_SENT
        post.zernio_post_id = str(result.get("_id") or result.get("id") or "")
        post.error = ""
        post.sent_at = timezone.now()
        post.reviewed_by = user
        post.save(
            update_fields=[
                "status", "zernio_post_id", "error", "sent_at",
                "reviewed_by", "updated_at",
            ]
        )
        return post, None

    @staticmethod
    def create_manual_post(data: Dict, user) -> Tuple[Optional[SocialPost], Optional[str]]:
        """Compose and send (or schedule) a post from the dashboard."""
        if not ZernioService.is_configured():
            return None, "Social media service not configured"

        platforms, error = SocialPostService.resolve_platforms(data.get("account_ids"))
        if error:
            return None, error

        post = SocialPost.objects.create(
            source=SocialPost.SOURCE_MANUAL,
            caption=data["caption"],
            image_url=data.get("image_url", ""),
            platforms=platforms,
            scheduled_for=data.get("scheduled_for"),
            status=SocialPost.STATUS_PENDING_APPROVAL,
            created_by=user,
        )
        return SocialPostService._send_to_zernio(post, user)

    @staticmethod
    def approve_post(post: SocialPost, data: Dict, user) -> Tuple[Optional[SocialPost], Optional[str]]:
        """Approve a queued post (with optional edits) and send it to Zernio."""
        if post.status not in (SocialPost.STATUS_PENDING_APPROVAL, SocialPost.STATUS_FAILED):
            return None, {"status": "Only pending or failed posts can be approved"}

        if not ZernioService.is_configured():
            return None, "Social media service not configured"

        if "caption" in data:
            post.caption = data["caption"]
        if "image_url" in data:
            post.image_url = data["image_url"]
        if "scheduled_for" in data:
            post.scheduled_for = data["scheduled_for"]

        platforms, error = SocialPostService.resolve_platforms(data.get("account_ids"))
        if error:
            return None, error
        post.platforms = platforms
        post.save(
            update_fields=["caption", "image_url", "scheduled_for", "platforms", "updated_at"]
        )
        return SocialPostService._send_to_zernio(post, user)

    @staticmethod
    def reject_post(post: SocialPost, user) -> Tuple[Optional[SocialPost], Optional[str]]:
        """Reject a queued post so it never reaches Zernio."""
        if post.status != SocialPost.STATUS_PENDING_APPROVAL:
            return None, {"status": "Only pending posts can be rejected"}

        post.status = SocialPost.STATUS_REJECTED
        post.reviewed_by = user
        post.save(update_fields=["status", "reviewed_by", "updated_at"])
        return post, None

    @staticmethod
    def queue_for_approval(source: str, obj) -> None:
        """Queue a templated post for admin approval when a product is
        published or a promotion is activated. No Zernio call happens here.

        Must never break the caller's transaction: everything is wrapped in
        try/except and the row is created after commit.
        """
        try:
            if not ZernioService.is_configured():
                return

            object_id = obj.id

            def _create_queued_post():
                try:
                    from apps.social.selectors import pending_or_sent_post_exists

                    if pending_or_sent_post_exists(source, object_id):
                        return
                    if source == SocialPost.SOURCE_PRODUCT:
                        caption = build_product_caption(obj)
                        image_url = get_product_image_url(obj)
                    else:
                        caption = build_promotion_caption(obj)
                        image_url = get_promotion_image_url(obj)

                    SocialPost.objects.create(
                        source=source,
                        object_id=object_id,
                        caption=caption,
                        image_url=image_url or "",
                        status=SocialPost.STATUS_PENDING_APPROVAL,
                    )
                except Exception as e:
                    logger.error(f"Failed to queue social post for {source}: {str(e)}")

            transaction.on_commit(_create_queued_post)
        except Exception as e:
            logger.error(f"Failed to schedule social post queueing: {str(e)}")

    @staticmethod
    def delete_post(post: SocialPost) -> Tuple[bool, Optional[str]]:
        """Delete a post record.

        Zernio only allows deleting draft/scheduled posts — published posts
        are owned by the platform and must be removed there (Zernio never
        learns about platform-side deletions either). So:
        - still-scheduled post: cancel it on Zernio first; block on failure
          so a "deleted" post can't publish later.
        - published (or never-sent) post: just remove our record.
        """
        is_pending_on_zernio = (
            post.zernio_post_id
            and post.scheduled_for is not None
            and post.scheduled_for > timezone.now()
        )
        if is_pending_on_zernio:
            _, error = ZernioService.delete_post(post.zernio_post_id)
            if error:
                return False, (
                    f"Could not cancel the scheduled post on Zernio: {error}"
                )
        elif post.zernio_post_id:
            # Best-effort: Zernio rejects deleting published posts (the
            # platform owns them) — never let that block the local delete
            ZernioService.delete_post(post.zernio_post_id)
        post.delete()
        return True, None
