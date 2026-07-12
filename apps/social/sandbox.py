"""
Sandbox social service — simulates Zernio locally for test mode.

Mirrors the return shapes of ZernioService so callers can't tell the
difference. Data lives in the Sandbox* models; no HTTP happens here.
"""

import random
import uuid
from typing import Dict, List, Optional, Tuple

from apps.social.models import (
    SandboxAccount,
    SandboxComment,
    SandboxConversation,
    SandboxMessage,
    SandboxProfile,
)

DEFAULT_SANDBOX_ACCOUNTS = [
    ("instagram", "Store (Sandbox)"),
    ("twitter", "Store (Sandbox)"),
    ("facebook", "Store (Sandbox)"),
]

DEMO_COMMENTERS = ["ama_shops", "kwesi.o", "nana_yaa", "kofi_deals", "esi_styles"]
DEMO_COMMENTS = [
    "Love this! 😍 Is it still available?",
    "How much is shipping to Kumasi?",
    "Just ordered mine 🔥",
    "Do you have this in other colors?",
    "Price please?",
]
DEMO_CONVERSATIONS = [
    ("Ama Mensah", "instagram", ["Hi! Do you deliver on weekends?"]),
    ("Kwesi Osei", "twitter", ["Is the promo still running?", "Also, can I pay on delivery?"]),
]


class SandboxSocialService:
    """Drop-in stand-in for ZernioService used when SocialConfig.mode == test"""

    @classmethod
    def _serialize_account(cls, account: SandboxAccount) -> Dict:
        return {
            "_id": str(account.id),
            "platform": account.platform,
            "name": account.name,
            "profileId": str(account.profile_id) if account.profile_id else None,
            "profileName": account.profile.name if account.profile else None,
        }

    @classmethod
    def list_accounts(cls) -> Tuple[Optional[List[Dict]], Optional[str]]:
        cls.seed_demo_accounts()
        accounts = [
            cls._serialize_account(a)
            for a in SandboxAccount.objects.select_related("profile")
        ]
        return accounts, None

    @classmethod
    def get_account(cls, account_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        account = SandboxAccount.objects.select_related("profile").filter(id=account_id).first()
        if not account:
            return None, "Social media resource not found"
        return cls._serialize_account(account), None

    @classmethod
    def disconnect_account(cls, account_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        deleted, _ = SandboxAccount.objects.filter(id=account_id).delete()
        if not deleted:
            return None, "Social media resource not found"
        return {}, None

    @classmethod
    def move_account(cls, account_id: str, profile_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        account = SandboxAccount.objects.filter(id=account_id).first()
        if not account:
            return None, "Social media resource not found"
        profile = SandboxProfile.objects.filter(id=profile_id).first()
        if not profile:
            return None, "Social media resource not found"
        account.profile = profile
        account.save(update_fields=["profile"])
        return cls._serialize_account(account), None

    @classmethod
    def get_connect_url(cls, platform: str, profile_id: Optional[str] = None) -> Tuple[Optional[Dict], Optional[str]]:
        """Test mode connects instantly instead of returning an OAuth URL."""
        cls.seed_demo_accounts()
        profile = None
        if profile_id:
            profile = SandboxProfile.objects.filter(id=profile_id).first()
        if profile is None:
            profile = SandboxProfile.objects.first()
        account = SandboxAccount.objects.create(
            platform=platform,
            name=f"{platform.title()} (Sandbox)",
            profile=profile,
        )
        return {"connected": True, "account": cls._serialize_account(account)}, None

    # ---------- Profiles ----------

    @classmethod
    def _serialize_profile(cls, profile: SandboxProfile) -> Dict:
        return {
            "_id": str(profile.id),
            "name": profile.name,
            "description": profile.description,
            "accounts": profile.accounts.count(),
        }

    @classmethod
    def list_profiles(cls) -> Tuple[Optional[List[Dict]], Optional[str]]:
        cls.seed_demo_accounts()
        return [cls._serialize_profile(p) for p in SandboxProfile.objects.all()], None

    @classmethod
    def create_profile(cls, name: str, description: str = "") -> Tuple[Optional[Dict], Optional[str]]:
        profile = SandboxProfile.objects.create(name=name, description=description)
        return cls._serialize_profile(profile), None

    @classmethod
    def update_profile(cls, profile_id: str, data: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        profile = SandboxProfile.objects.filter(id=profile_id).first()
        if not profile:
            return None, "Social media resource not found"
        if "name" in data:
            profile.name = data["name"]
        if "description" in data:
            profile.description = data["description"]
        profile.save()
        return cls._serialize_profile(profile), None

    @classmethod
    def delete_profile(cls, profile_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        deleted, _ = SandboxProfile.objects.filter(id=profile_id).delete()
        if not deleted:
            return None, "Social media resource not found"
        return {}, None

    # ---------- Usage ----------

    @classmethod
    def get_usage_stats(cls) -> Tuple[Optional[Dict], Optional[str]]:
        """Real sandbox counts plus static plan limits so tiles render."""
        from apps.social.models import SocialPost

        cls.seed_demo_accounts()
        accounts = SandboxAccount.objects.count()
        posts_sent = SocialPost.objects.filter(status=SocialPost.STATUS_SENT).count()
        return {
            "plan": "Sandbox",
            "accounts_connected": accounts,
            "accounts_limit": 10,
            "posts_this_month": posts_sent,
            "posts_limit": 500,
            "profiles": SandboxProfile.objects.count(),
            "uploads": 0,
            "uploads_limit": 100,
        }, None

    @classmethod
    def seed_demo_accounts(cls) -> None:
        """Create a default profile with demo accounts on first access."""
        if SandboxProfile.objects.exists() or SandboxAccount.objects.exists():
            return
        profile = SandboxProfile.objects.create(
            name="Default", description="Auto-created sandbox profile"
        )
        for platform, name in DEFAULT_SANDBOX_ACCOUNTS:
            SandboxAccount.objects.create(platform=platform, name=name, profile=profile)

    @classmethod
    def create_post(
        cls,
        content: str,
        platforms: List[Dict[str, str]],
        media_urls: Optional[List[str]] = None,
        media_items: Optional[List[Dict[str, str]]] = None,
        scheduled_for: Optional[str] = None,
        timezone_name: Optional[str] = None,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        post_id = f"sandbox_{uuid.uuid4().hex[:12]}"
        # Seed a few fake comments so the engagement flow can be tested
        for author, message in random.sample(
            list(zip(DEMO_COMMENTERS, DEMO_COMMENTS)), k=2
        ):
            SandboxComment.objects.create(
                zernio_post_id=post_id, author=author, message=message
            )
        return {
            "_id": post_id,
            "status": "published",
            "mediaItems": media_items or media_urls or [],
        }, None

    @classmethod
    def delete_post(cls, post_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        SandboxComment.objects.filter(zernio_post_id=post_id).delete()
        return {}, None

    @classmethod
    def list_post_comments(cls, post_id: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        comments = [
            {
                "_id": str(comment.id),
                "author": comment.author,
                "message": comment.message,
                "hidden": comment.hidden,
                "liked": comment.liked,
                "isReply": comment.is_reply,
                "createdAt": comment.created_at.isoformat(),
            }
            for comment in SandboxComment.objects.filter(zernio_post_id=post_id)
        ]
        return comments, None

    @classmethod
    def reply_comment(
        cls, post_id: str, comment_id: str, message: str
    ) -> Tuple[Optional[Dict], Optional[str]]:
        SandboxComment.objects.create(
            zernio_post_id=post_id,
            author="Store (you)",
            message=message,
            is_reply=True,
        )
        return {}, None

    @classmethod
    def comment_action(
        cls, post_id: str, comment_id: str, action: str
    ) -> Tuple[Optional[Dict], Optional[str]]:
        comment = SandboxComment.objects.filter(
            id=comment_id, zernio_post_id=post_id
        ).first()
        if not comment:
            return None, "Social media resource not found"
        if action == "delete":
            comment.delete()
            return {}, None
        if action in ("hide", "unhide"):
            comment.hidden = action == "hide"
        elif action in ("like", "unlike"):
            comment.liked = action == "like"
        comment.save(update_fields=["hidden", "liked"])
        return {}, None

    @classmethod
    def get_post_analytics(cls, post_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Deterministic fake metrics so the analytics panel can be tested."""
        seed = int.from_bytes(post_id.encode()[-8:], "big")
        impressions = 400 + seed % 4600
        reach = int(impressions * (0.55 + (seed % 30) / 100))
        likes = 10 + seed % 240
        comment_count = SandboxComment.objects.filter(
            zernio_post_id=post_id, is_reply=False
        ).count()
        shares = seed % 40
        clicks = seed % 130
        engagement = likes + comment_count + shares + clicks
        return {
            "impressions": impressions,
            "reach": reach,
            "engagement": engagement,
            "likes": likes,
            "comments": comment_count,
            "shares": shares,
            "clicks": clicks,
        }, None

    @classmethod
    def list_conversations(
        cls, platform: Optional[str] = None
    ) -> Tuple[Optional[List[Dict]], Optional[str]]:
        cls.seed_demo_conversations()
        queryset = SandboxConversation.objects.prefetch_related("messages")
        if platform:
            queryset = queryset.filter(platform=platform)
        conversations = []
        for c in queryset:
            last = c.messages.order_by("-created_at").first()
            conversations.append({
                "_id": str(c.id),
                "name": c.name,
                "platform": c.platform,
                "accountId": f"sandbox_{c.platform}",
                "lastMessage": last.message if last else "",
                "lastMessageAt": last.created_at.isoformat() if last else c.created_at.isoformat(),
                "lastMessageIsOwn": last.is_outgoing if last else False,
            })
        conversations.sort(key=lambda c: c["lastMessageAt"], reverse=True)
        return conversations, None

    @classmethod
    def list_messages(cls, conversation_id: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        conversation = SandboxConversation.objects.filter(id=conversation_id).first()
        if not conversation:
            return None, "Social media resource not found"
        messages = [
            {
                "_id": str(m.id),
                "message": m.message,
                "isOwn": m.is_outgoing,
                "createdAt": m.created_at.isoformat(),
            }
            for m in conversation.messages.all()
        ]
        return messages, None

    @classmethod
    def send_message(
        cls, conversation_id: str, message: str
    ) -> Tuple[Optional[Dict], Optional[str]]:
        conversation = SandboxConversation.objects.filter(id=conversation_id).first()
        if not conversation:
            return None, "Social media resource not found"
        SandboxMessage.objects.create(
            conversation=conversation, message=message, is_outgoing=True
        )
        return {}, None

    @classmethod
    def seed_demo_conversations(cls) -> None:
        """Create demo conversations once so the inbox has content to test."""
        if SandboxConversation.objects.exists():
            return
        for name, platform, messages in DEMO_CONVERSATIONS:
            conversation = SandboxConversation.objects.create(
                name=name, platform=platform
            )
            for message in messages:
                SandboxMessage.objects.create(
                    conversation=conversation, message=message, is_outgoing=False
                )
