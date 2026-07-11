# apps/social/zernio_service.py
import logging
from typing import Any, Dict, List, Optional, Tuple

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

ACCOUNTS_CACHE_KEY = "zernio_connected_accounts"
ACCOUNTS_CACHE_TIMEOUT = 300


class ZernioService:
    """Zernio social-media integration for publishing posts and managing the inbox"""

    BASE_URL = getattr(settings, 'ZERNIO_BASE_URL', 'https://zernio.com/api/v1')
    API_KEY = getattr(settings, 'ZERNIO_API_KEY', '')

    @classmethod
    def _get_headers(cls) -> Dict[str, str]:
        """Get request headers for Zernio API"""
        return {
            'Authorization': f'Bearer {cls.API_KEY}',
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        }

    @classmethod
    def _sandbox(cls):
        """Return the sandbox service when test mode is active, else None"""
        from apps.social.models import SocialConfig

        if SocialConfig.test_mode_active():
            from apps.social.sandbox import SandboxSocialService

            return SandboxSocialService
        return None

    @classmethod
    def is_configured(cls) -> bool:
        """Check if Zernio is properly configured (always true in test mode)"""
        if cls._sandbox():
            return True
        return bool(cls.API_KEY)

    @classmethod
    def _request(
        cls,
        method: str,
        path: str,
        json_payload: Optional[Dict] = None,
        params: Optional[Dict] = None,
    ) -> Tuple[Optional[Any], Optional[str]]:
        """Make a Zernio API request. Returns (parsed_json, error_message)."""
        try:
            if not cls.is_configured():
                logger.warning("Zernio API key not configured")
                return None, "Social media service not configured"

            response = requests.request(
                method,
                f"{cls.BASE_URL}{path}",
                json=json_payload,
                params=params,
                headers=cls._get_headers(),
                timeout=30,
            )

            if response.status_code in (200, 201):
                try:
                    return response.json(), None
                except ValueError:
                    return {}, None
            elif response.status_code == 400:
                # 400s carry actionable validation messages (e.g. duplicate
                # content) — surface Zernio's message, not a generic error
                try:
                    body = response.json()
                    message = str(
                        body.get("message") or body.get("error") or ""
                    ).strip()[:200]
                except ValueError:
                    message = ""
                logger.error(f"Zernio 400 on {path}: {message}")
                return None, message or "Social media API error: 400"
            elif response.status_code == 401:
                logger.error("Zernio authentication failed")
                return None, "Invalid social media API key"
            elif response.status_code == 404:
                logger.error(f"Zernio resource not found: {path}")
                return None, "Social media resource not found"
            elif response.status_code == 429:
                logger.error("Zernio rate limit exceeded")
                return None, "Rate limit exceeded, please try again later"
            else:
                logger.error(
                    f"Zernio API error: {response.status_code} - {response.text[:500]}"
                )
                return None, f"Social media API error: {response.status_code}"

        except requests.Timeout:
            logger.error(f"Zernio request timeout: {path}")
            return None, "Social media service timeout"
        except requests.ConnectionError:
            logger.error(f"Zernio connection error: {path}")
            return None, "Unable to connect to social media service"
        except Exception as e:
            logger.error(f"Zernio error: {str(e)}")
            return None, "Social media service error. Please try again later."

    # ---------- Accounts ----------

    @classmethod
    def list_accounts(cls, use_cache: bool = True) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """List connected social accounts (cached for 5 minutes)"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.list_accounts()
        if use_cache:
            cached = cache.get(ACCOUNTS_CACHE_KEY)
            if cached is not None:
                return cached, None

        # Verified against the live API (quickstart): GET /accounts.
        # ("list-accounts" in their docs is the SDK method name, not the path.)
        data, error = cls._request("GET", "/accounts")
        if error:
            return None, error

        accounts = cls._extract_list(data, keys=("accounts", "data"))
        cache.set(ACCOUNTS_CACHE_KEY, accounts, ACCOUNTS_CACHE_TIMEOUT)
        return accounts, None

    # ---------- Posts ----------

    @classmethod
    def create_post(
        cls,
        content: str,
        platforms: List[Dict[str, str]],
        media_urls: Optional[List[str]] = None,
        scheduled_for: Optional[str] = None,
        timezone_name: Optional[str] = None,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Create a post on Zernio, publishing immediately unless scheduled.

        platforms: list of {"platform": ..., "accountId": ...} dicts.
        media_urls: remote image URLs (Cloudinary). NOTE: the exact Zernio
        media field is unverified against their API (docs incomplete);
        `mediaUrls` is the candidate name — confirm in Stage 0 verification.
        """
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.create_post(content, platforms, media_urls, scheduled_for, timezone_name)

        payload: Dict[str, Any] = {
            "content": content,
            "platforms": platforms,
        }
        if media_urls:
            payload["mediaUrls"] = media_urls
        if scheduled_for:
            payload["scheduledFor"] = scheduled_for
            payload["timezone"] = timezone_name or settings.TIME_ZONE
        else:
            payload["publishNow"] = True

        data, error = cls._request("POST", "/posts", json_payload=payload)
        if error:
            return None, error
        return cls._extract_dict(data, keys=("post", "data")), None

    @classmethod
    def get_post(cls, post_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Get a Zernio post by id"""
        data, error = cls._request("GET", f"/posts/{post_id}")
        if error:
            return None, error
        return cls._extract_dict(data, keys=("post", "data")), None

    @classmethod
    def get_post_analytics(cls, post_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Get analytics for a post (impressions, reach, engagement, ...).

        Normalizes the Zernio response into a flat metrics dict so the
        dashboard renders a stable shape regardless of provider changes.
        """
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.get_post_analytics(post_id)

        # Verified live: analytics live under GET /analytics (no /posts suffix)
        data, error = cls._request(
            "GET", "/analytics", params={"postId": post_id}
        )
        if error:
            return None, error

        raw = cls._extract_dict(data, keys=("analytics", "post", "data"))
        return {
            "impressions": raw.get("impressions", 0),
            "reach": raw.get("reach", 0),
            "engagement": raw.get("engagement", 0),
            "likes": raw.get("likes", 0),
            "comments": raw.get("comments", 0),
            "shares": raw.get("shares", 0),
            "clicks": raw.get("clicks", 0),
        }, None

    @classmethod
    def delete_post(cls, post_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Delete a Zernio post"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.delete_post(post_id)
        return cls._request("DELETE", f"/posts/{post_id}")

    # ---------- Inbox: comments ----------

    @classmethod
    def list_post_comments(cls, post_id: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """List comments on a Zernio post"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.list_post_comments(post_id)
        data, error = cls._request("GET", f"/inbox/post-comments/{post_id}")
        if error:
            return None, error
        return cls._extract_list(data, keys=("comments", "data")), None

    @classmethod
    def reply_comment(
        cls, post_id: str, comment_id: str, message: str
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Reply to a comment on a Zernio post"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.reply_comment(post_id, comment_id, message)
        return cls._request(
            "POST",
            f"/inbox/reply/{post_id}",
            json_payload={"commentId": comment_id, "message": message},
        )

    @classmethod
    def comment_action(
        cls, post_id: str, comment_id: str, action: str
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Perform a moderation action on a comment: hide/unhide/like/unlike/delete"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.comment_action(post_id, comment_id, action)
        if action == "delete":
            return cls._request(
                "DELETE",
                f"/inbox/delete-comment/{post_id}",
                json_payload={"commentId": comment_id},
            )
        return cls._request(
            "POST", f"/inbox/{action}-comment/{post_id}/{comment_id}"
        )

    # ---------- Inbox: conversations / DMs ----------

    @classmethod
    def list_conversations(
        cls, platform: Optional[str] = None
    ) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """List inbox conversations, optionally filtered by platform"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.list_conversations(platform)
        params = {"platform": platform} if platform else None
        data, error = cls._request("GET", "/inbox/conversations", params=params)
        if error:
            return None, error
        return cls._extract_list(data, keys=("conversations", "data")), None

    @classmethod
    def list_messages(cls, conversation_id: str) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """List messages in a conversation"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.list_messages(conversation_id)
        data, error = cls._request("GET", f"/inbox/messages/{conversation_id}")
        if error:
            return None, error
        return cls._extract_list(data, keys=("messages", "data")), None

    @classmethod
    def send_message(
        cls, conversation_id: str, message: str
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Send a DM reply in a conversation"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.send_message(conversation_id, message)
        return cls._request(
            "POST",
            f"/inbox/send/{conversation_id}",
            json_payload={"message": message},
        )

    # ---------- Account management ----------

    @classmethod
    def get_account(cls, account_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Get details for a connected account"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.get_account(account_id)
        data, error = cls._request("GET", f"/accounts/{account_id}")
        if error:
            return None, error
        return cls._extract_dict(data, keys=("account", "data")), None

    @classmethod
    def disconnect_account(cls, account_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Disconnect a social account"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.disconnect_account(account_id)
        result, error = cls._request("DELETE", f"/accounts/{account_id}")
        if not error:
            cache.delete(ACCOUNTS_CACHE_KEY)
        return result, error

    @classmethod
    def move_account(cls, account_id: str, profile_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Move an account to another profile"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.move_account(account_id, profile_id)
        result, error = cls._request(
            "POST", f"/accounts/{account_id}/move", json_payload={"profileId": profile_id}
        )
        if not error:
            cache.delete(ACCOUNTS_CACHE_KEY)
        return result, error

    @classmethod
    def get_connect_url(
        cls, platform: str, profile_id: Optional[str] = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Get the OAuth URL to connect a new account for a platform.

        Live mode returns {"url": ...} for the frontend to open in a new tab.
        NOTE: the exact response field for the URL is unverified against the
        live API (docs incomplete) — parsed defensively; confirm in Stage 0.
        Test mode connects instantly and returns {"connected": True}.
        """
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.get_connect_url(platform, profile_id)
        params = {"profileId": profile_id} if profile_id else None
        data, error = cls._request("GET", f"/connect/{platform}", params=params)
        if error:
            return None, error
        body = cls._extract_dict(data, keys=("data",))
        url = body.get("url") or body.get("authUrl") or body.get("authorizationUrl")
        if not url:
            logger.error(f"Zernio connect URL missing in response for {platform}")
            return None, "Could not get authorization link"
        return {"url": url}, None

    # ---------- Profiles ----------

    @classmethod
    def list_profiles(cls) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """List Zernio profiles (workspaces grouping accounts)"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.list_profiles()
        data, error = cls._request("GET", "/profiles")
        if error:
            return None, error
        return cls._extract_list(data, keys=("profiles", "data")), None

    @classmethod
    def create_profile(cls, name: str, description: str = "") -> Tuple[Optional[Dict], Optional[str]]:
        """Create a Zernio profile"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.create_profile(name, description)
        data, error = cls._request(
            "POST", "/profiles", json_payload={"name": name, "description": description}
        )
        if error:
            return None, error
        return cls._extract_dict(data, keys=("profile", "data")), None

    @classmethod
    def update_profile(cls, profile_id: str, data: Dict) -> Tuple[Optional[Dict], Optional[str]]:
        """Rename/update a Zernio profile"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.update_profile(profile_id, data)
        result, error = cls._request("PATCH", f"/profiles/{profile_id}", json_payload=data)
        if error:
            return None, error
        return cls._extract_dict(result, keys=("profile", "data")), None

    @classmethod
    def delete_profile(cls, profile_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Delete a Zernio profile"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.delete_profile(profile_id)
        return cls._request("DELETE", f"/profiles/{profile_id}")

    # ---------- Usage ----------

    @classmethod
    def get_usage_stats(cls) -> Tuple[Optional[Dict], Optional[str]]:
        """Usage metrics (cached 5 minutes).

        Zernio exposes no usage/quota endpoint (verified against the live
        API), so this synthesizes stats from real sources: connected
        accounts and profiles from the API, posts-this-month from our own
        sent SocialPost records. Plan/limits are unknown → empty/0.
        """
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.get_usage_stats()

        cache_key = "zernio_usage_stats"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached, None

        accounts, error = cls.list_accounts()
        if error:
            return None, error
        profiles, _profiles_error = cls.list_profiles()

        from django.utils import timezone
        from apps.social.models import SocialPost

        month_start = timezone.now().replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        posts_this_month = SocialPost.objects.filter(
            status=SocialPost.STATUS_SENT, sent_at__gte=month_start
        ).count()

        stats = {
            "plan": "",
            "accounts_connected": len(accounts or []),
            "accounts_limit": 0,
            "posts_this_month": posts_this_month,
            "posts_limit": 0,
            "profiles": len(profiles or []),
        }
        cache.set(cache_key, stats, 300)
        return stats, None

    # ---------- Response helpers ----------

    @staticmethod
    def _extract_list(data: Any, keys: tuple) -> List[Dict]:
        """Pull the list body out of a Zernio response regardless of envelope"""
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, list):
                    return value
        return []

    @staticmethod
    def _extract_dict(data: Any, keys: tuple) -> Dict:
        """Pull the object body out of a Zernio response regardless of envelope"""
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, dict):
                    return value
            return data
        return {}
