# apps/social/zernio_service.py
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

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
        extra_headers: Optional[Dict[str, str]] = None,
        success_statuses: tuple = (200, 201, 204),
    ) -> Tuple[Optional[Any], Optional[str]]:
        """Make a Zernio API request. Returns (parsed_json, error_message)."""
        try:
            if not cls.is_configured():
                logger.warning("Zernio API key not configured")
                return None, "Social media service not configured"

            headers = cls._get_headers()
            if extra_headers:
                headers.update(extra_headers)

            response = requests.request(
                method,
                f"{cls.BASE_URL}{path}",
                json=json_payload,
                params=params,
                headers=headers,
                timeout=30,
            )

            if response.status_code in success_statuses:
                try:
                    return response.json(), None
                except ValueError:
                    return {}, None
            elif response.status_code in (400, 409):
                message = cls._response_error_message(response)
                logger.error(f"Zernio {response.status_code} on {path}: {message}")
                return None, message or f"Social media API error: {response.status_code}"
            elif response.status_code == 401:
                logger.error("Zernio authentication failed")
                return None, "Invalid social media API key"
            elif response.status_code == 402:
                message = cls._response_error_message(response)
                logger.error(f"Zernio payment required on {path}: {message}")
                return None, message or "Payment required for social media service"
            elif response.status_code == 403:
                message = cls._response_error_message(response)
                logger.error(f"Zernio access denied on {path}: {message}")
                return None, message or "Social media access denied"
            elif response.status_code == 404:
                logger.error(f"Zernio resource not found: {path}")
                return None, "Social media resource not found"
            elif response.status_code == 202:
                message = cls._response_error_message(response)
                logger.info(f"Zernio request still processing on {path}: {message}")
                return None, message or "Social media request is still processing"
            elif response.status_code == 424:
                message = cls._response_error_message(response)
                logger.error(f"Zernio dependency failed on {path}: {message}")
                return None, message or "Social media analytics unavailable"
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
        media_items: Optional[List[Dict[str, str]]] = None,
        scheduled_for: Optional[str] = None,
        timezone_name: Optional[str] = None,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Create a post on Zernio, publishing immediately unless scheduled.

        platforms: list of {"platform": ..., "accountId": ...} dicts.
        media_urls: remote media URLs (Cloudinary), converted into Zernio's
        mediaItems array. media_items may be provided directly by newer callers.
        """
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.create_post(
                content,
                platforms,
                media_urls=media_urls,
                media_items=media_items,
                scheduled_for=scheduled_for,
                timezone_name=timezone_name,
            )

        payload: Dict[str, Any] = {
            "content": content,
            "platforms": platforms,
        }
        normalized_media_items = media_items or cls._media_items_from_urls(media_urls or [])
        if normalized_media_items:
            payload["mediaItems"] = normalized_media_items
        if scheduled_for:
            payload["scheduledFor"] = scheduled_for
            payload["timezone"] = timezone_name or settings.TIME_ZONE
        else:
            payload["publishNow"] = True

        data, error = cls._request(
            "POST",
            "/posts",
            json_payload=payload,
            extra_headers={"x-request-id": str(uuid.uuid4())},
        )
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
    def get_post_analytics(
        cls, post_id: str, account_id: Optional[str] = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Get analytics for a post (impressions, reach, engagement, ...).

        Normalizes the Zernio response into a flat metrics dict so the
        dashboard renders a stable shape regardless of provider changes.
        """
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.get_post_analytics(post_id)

        # Verified live: analytics live under GET /analytics (no /posts suffix)
        params = {"postId": post_id}
        if account_id:
            params["accountId"] = account_id

        data, error = cls._request(
            "GET",
            "/analytics",
            params=params,
            success_statuses=(200, 202),
        )
        if error:
            return None, error

        container = cls._extract_dict(data, keys=("data", "post"))
        if (
            isinstance(container.get("post"), dict)
            and not isinstance(container.get("analytics"), dict)
            and not isinstance(container.get("platformAnalytics"), list)
        ):
            container = container["post"]
        return cls._normalize_post_analytics(container), None

    @classmethod
    def delete_post(cls, post_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """Delete a Zernio post"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.delete_post(post_id)
        return cls._request("DELETE", f"/posts/{post_id}")

    # ---------- Inbox: comments ----------

    @classmethod
    def list_post_comments(
        cls, post_id: str, account_id: Optional[str] = None
    ) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """List comments on a Zernio post"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.list_post_comments(post_id)
        if not account_id:
            return None, "Account id is required"
        data, error = cls._request(
            "GET",
            f"/inbox/comments/{post_id}",
            params={"accountId": account_id},
        )
        if error:
            return None, error
        comments = cls._extract_list(data, keys=("comments", "data"))
        return cls._flatten_comments(comments), None

    @classmethod
    def reply_comment(
        cls,
        post_id: str,
        comment_id: str,
        message: str,
        account_id: Optional[str] = None,
        parent_cid: Optional[str] = None,
        root_uri: Optional[str] = None,
        root_cid: Optional[str] = None,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Reply to a comment on a Zernio post"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.reply_comment(post_id, comment_id, message)
        if not account_id:
            return None, "Account id is required"
        payload = {
            "accountId": account_id,
            "commentId": comment_id,
            "message": message,
        }
        if parent_cid:
            payload["parentCid"] = parent_cid
        if root_uri:
            payload["rootUri"] = root_uri
        if root_cid:
            payload["rootCid"] = root_cid
        return cls._request(
            "POST",
            f"/inbox/comments/{post_id}",
            json_payload=payload,
        )

    @classmethod
    def comment_action(
        cls,
        post_id: str,
        comment_id: str,
        action: str,
        account_id: Optional[str] = None,
        cid: Optional[str] = None,
        like_uri: Optional[str] = None,
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Perform a moderation action on a comment: hide/unhide/like/unlike/delete"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.comment_action(post_id, comment_id, action)
        if not account_id:
            return None, "Account id is required"
        if action == "delete":
            return cls._request(
                "DELETE",
                f"/inbox/comments/{post_id}",
                params={"accountId": account_id, "commentId": comment_id},
            )
        if action == "hide":
            return cls._request(
                "POST",
                f"/inbox/comments/{post_id}/{comment_id}/hide",
                json_payload={"accountId": account_id},
            )
        if action == "unhide":
            return cls._request(
                "DELETE",
                f"/inbox/comments/{post_id}/{comment_id}/hide",
                params={"accountId": account_id},
            )
        if action == "like":
            payload = {"accountId": account_id}
            if cid:
                payload["cid"] = cid
            return cls._request(
                "POST",
                f"/inbox/comments/{post_id}/{comment_id}/like",
                json_payload=payload,
            )
        if action == "unlike":
            params = {"accountId": account_id}
            if like_uri:
                params["likeUri"] = like_uri
            return cls._request(
                "DELETE",
                f"/inbox/comments/{post_id}/{comment_id}/like",
                params=params,
            )
        return cls._request(
            "POST",
            f"/inbox/comments/{post_id}/{comment_id}/{action}",
            json_payload={"accountId": account_id},
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
        conversations = cls._extract_list(data, keys=("conversations", "data"))
        return [cls._normalize_conversation(c) for c in conversations], None

    @classmethod
    def list_messages(
        cls, conversation_id: str, account_id: Optional[str] = None
    ) -> Tuple[Optional[List[Dict]], Optional[str]]:
        """List messages in a conversation"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.list_messages(conversation_id)
        if not account_id:
            return None, "Account id is required"
        data, error = cls._request(
            "GET",
            f"/inbox/conversations/{conversation_id}/messages",
            params={"accountId": account_id},
        )
        if error:
            return None, error
        messages = cls._extract_list(data, keys=("messages", "data"))
        return [cls._normalize_message(m) for m in messages], None

    @classmethod
    def send_message(
        cls, conversation_id: str, message: str, account_id: Optional[str] = None
    ) -> Tuple[Optional[Dict], Optional[str]]:
        """Send a DM reply in a conversation"""
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.send_message(conversation_id, message)
        if not account_id:
            return None, "Account id is required"
        return cls._request(
            "POST",
            f"/inbox/conversations/{conversation_id}/messages",
            json_payload={"accountId": account_id, "message": message},
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
            "PATCH", f"/accounts/{account_id}", json_payload={"profileId": profile_id}
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
        The URL response field is parsed defensively across common envelopes.
        Test mode connects instantly and returns {"connected": True}.
        """
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.get_connect_url(platform, profile_id)
        if not profile_id:
            return None, "Profile id is required"
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
        result, error = cls._request("PUT", f"/profiles/{profile_id}", json_payload=data)
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

        Normalizes Zernio's GET /usage response into the dashboard shape.
        """
        sandbox = cls._sandbox()
        if sandbox:
            return sandbox.get_usage_stats()

        cache_key = "zernio_usage_stats"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached, None

        data, error = cls._request("GET", "/usage")
        if error:
            return None, error
        usage = data.get("usage", {}) if isinstance(data, dict) else {}
        limits = data.get("limits", {}) if isinstance(data, dict) else {}

        stats = {
            "plan": data.get("planName", "") if isinstance(data, dict) else "",
            "accounts_connected": usage.get("connectedAccounts", 0),
            "accounts_limit": limits.get("connectedAccounts", 0),
            "posts_this_month": usage.get("posts", usage.get("postsThisMonth", 0)),
            "posts_limit": limits.get("posts", limits.get("postsThisMonth", 0)),
            "profiles": usage.get("profiles", 0),
            "uploads": usage.get("uploads", 0),
            "uploads_limit": limits.get("uploads", 0),
            "spend": data.get("spend", {}) if isinstance(data, dict) else {},
            "raw": data,
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
            for key in (*keys, "result", "results", "payload"):
                value = data.get(key)
                if isinstance(value, dict):
                    nested = ZernioService._extract_list(value, keys)
                    if nested or any(isinstance(value.get(k), list) for k in keys):
                        return nested
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

    @staticmethod
    def _response_error_message(response) -> str:
        try:
            body = response.json()
        except ValueError:
            return ""
        if not isinstance(body, dict):
            return ""
        message = str(body.get("message") or body.get("error") or "").strip()
        if message:
            return message[:300]
        errors = body.get("errors")
        if isinstance(errors, list) and errors:
            first_error = errors[0]
            if isinstance(first_error, dict):
                message = str(
                    first_error.get("message")
                    or first_error.get("error")
                    or first_error.get("detail")
                    or ""
                ).strip()
            else:
                message = str(first_error).strip()
            if message:
                return message[:300]
        detail = str(body.get("detail") or body.get("details") or "").strip()
        if detail:
            return detail[:300]
        code = str(body.get("code") or "").strip()
        if code:
            return code[:300]
        return ""

    @staticmethod
    def _media_items_from_urls(media_urls: List[str]) -> List[Dict[str, str]]:
        items = []
        for url in media_urls:
            media_type = ZernioService._media_type_for_url(url)
            items.append({"type": media_type, "url": url})
        return items

    @staticmethod
    def _media_type_for_url(url: str) -> str:
        path = urlsplit(url).path.lower()
        if path.endswith((".mp4", ".mov", ".webm")):
            return "video"
        return "image"

    @staticmethod
    def _normalize_post_analytics(container: Dict) -> Dict:
        raw = (
            container.get("analytics")
            if isinstance(container.get("analytics"), dict)
            else container.get("metrics")
            if isinstance(container.get("metrics"), dict)
            else container.get("summary")
            if isinstance(container.get("summary"), dict)
            else container
        )
        if not isinstance(raw, dict):
            raw = {}

        platform_totals: Dict[str, float] = {}
        platform_analytics = container.get("platformAnalytics")
        metric_aliases = {
            "impressions": ("impressions", "impressionCount"),
            "reach": ("reach", "reachCount"),
            "likes": ("likes", "likeCount", "favorites", "favoriteCount"),
            "comments": ("comments", "commentCount", "numComments", "replyCount"),
            "shares": ("shares", "shareCount", "reposts", "retweets"),
            "clicks": ("clicks", "clickCount", "linkClicks"),
            "views": ("views", "viewCount", "videoViews", "playCount"),
            "saves": ("saves", "saveCount", "saved"),
            "follows": ("follows", "followCount"),
        }

        if isinstance(platform_analytics, list):
            for item in platform_analytics:
                if not isinstance(item, dict):
                    continue
                metrics = item.get("analytics") or item.get("metrics") or item.get("summary")
                if not isinstance(metrics, dict):
                    continue
                for key, aliases in metric_aliases.items():
                    platform_totals[key] = platform_totals.get(key, 0) + ZernioService._first_number(
                        metrics, aliases
                    )

        def metric(key: str) -> float:
            value = ZernioService._first_number(raw, metric_aliases[key])
            if value:
                return value
            return platform_totals.get(key, 0)

        likes = metric("likes")
        comments = metric("comments")
        shares = metric("shares")
        clicks = metric("clicks")
        views = metric("views")
        saves = metric("saves")
        follows = metric("follows")
        engagement_rate = ZernioService._number(
            raw.get("engagementRate", raw.get("engagement_rate"))
        )
        if not engagement_rate and platform_analytics:
            rate_values = []
            for item in platform_analytics:
                if not isinstance(item, dict):
                    continue
                metrics = item.get("analytics") or item.get("metrics") or item.get("summary")
                if not isinstance(metrics, dict):
                    continue
                rate = ZernioService._first_number(
                    metrics, ("engagementRate", "engagement_rate")
                )
                if rate:
                    rate_values.append(rate)
            if rate_values:
                engagement_rate = sum(rate_values) / len(rate_values)

        engagement = ZernioService._number(raw.get("engagement"))
        if not engagement:
            engagement = likes + comments + shares + clicks + views + saves + follows
        if not engagement:
            engagement = engagement_rate

        return {
            "impressions": metric("impressions"),
            "reach": metric("reach"),
            "engagement": engagement,
            "engagementRate": engagement_rate,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "clicks": clicks,
            "views": views,
            "saves": saves,
            "follows": follows,
            "syncStatus": container.get("syncStatus", raw.get("syncStatus", "")),
            "message": container.get("message", raw.get("message", "")),
            "lastUpdated": raw.get("lastUpdated", ""),
        }

    @staticmethod
    def _number(value: Any) -> float:
        if isinstance(value, bool):
            return 0
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return 0
        return 0

    @staticmethod
    def _first_number(source: Dict, keys: tuple) -> float:
        if not isinstance(source, dict):
            return 0
        for key in keys:
            value = ZernioService._number(source.get(key))
            if value:
                return value
        return 0

    @staticmethod
    def _flatten_comments(
        comments: List[Dict], parent_id: Optional[str] = None, depth: int = 0
    ) -> List[Dict]:
        """Flatten nested comment replies into a renderable thread list."""
        flattened = []
        for comment in comments:
            if not isinstance(comment, dict):
                continue

            normalized = ZernioService._normalize_comment(comment, parent_id, depth)
            flattened.append(normalized)

            replies = []
            for key in ("replies", "children", "comments", "nestedComments"):
                value = comment.get(key)
                if isinstance(value, list):
                    replies.extend(value)
                elif isinstance(value, dict):
                    replies.extend(
                        ZernioService._extract_list(value, keys=("comments", "replies", "data"))
                    )
            if replies:
                flattened.extend(
                    ZernioService._flatten_comments(
                        replies,
                        parent_id=normalized.get("id") or normalized.get("_id"),
                        depth=depth + 1,
                    )
                )
        return flattened

    @staticmethod
    def _normalize_comment(comment: Dict, parent_id: Optional[str], depth: int) -> Dict:
        normalized = dict(comment)
        comment_id = (
            normalized.get("_id")
            or normalized.get("id")
            or normalized.get("commentId")
            or normalized.get("comment_id")
            or normalized.get("cid")
            or normalized.get("uri")
        )
        if comment_id:
            normalized.setdefault("_id", str(comment_id))
            normalized.setdefault("id", str(comment_id))

        text = ZernioService._message_text(normalized)
        if text:
            normalized["message"] = text
            normalized["text"] = text

        author = normalized.get("from") or normalized.get("sender") or normalized.get("author")
        author_name = (
            ZernioService._object_string(
                author, ("displayName", "name", "username", "fullName", "handle")
            )
            or ZernioService._first_string(
                normalized, ("authorName", "senderName", "username", "name", "author")
            )
        )
        if author_name and not isinstance(normalized.get("from"), dict):
            normalized["from"] = {"name": author_name}

        existing_parent = normalized.get("parentId") or normalized.get("parent_id")
        if parent_id and not existing_parent:
            normalized["parentId"] = parent_id
        elif existing_parent:
            normalized["parentId"] = str(existing_parent)

        normalized["depth"] = depth
        normalized["isReply"] = bool(
            depth > 0
            or normalized.get("isReply")
            or normalized.get("is_reply")
            or normalized.get("parentId")
        )
        normalized["hidden"] = bool(normalized.get("hidden") or normalized.get("isHidden"))
        normalized["liked"] = bool(normalized.get("liked") or normalized.get("isLiked"))

        created_at = ZernioService._first_string(
            normalized, ("createdAt", "created_at", "timestamp", "time")
        )
        if created_at:
            normalized["createdAt"] = created_at
        return normalized

    @staticmethod
    def _normalize_conversation(conversation: Dict) -> Dict:
        if not isinstance(conversation, dict):
            return conversation

        normalized = dict(conversation)
        conversation_id = (
            normalized.get("_id")
            or normalized.get("id")
            or normalized.get("conversationId")
            or normalized.get("conversation_id")
        )
        if conversation_id:
            normalized.setdefault("_id", str(conversation_id))
            normalized.setdefault("id", str(conversation_id))

        account = normalized.get("account")
        account_id = (
            normalized.get("accountId")
            or normalized.get("account_id")
            or ZernioService._object_string(account, ("_id", "id", "accountId"))
        )
        if account_id:
            normalized["accountId"] = str(account_id)

        participant = ZernioService._conversation_participant(normalized)
        name = (
            ZernioService._first_string(
                normalized,
                (
                    "participantName",
                    "senderName",
                    "displayName",
                    "contactName",
                    "customerName",
                    "username",
                    "name",
                ),
            )
            or ZernioService._object_string(
                participant,
                ("displayName", "name", "username", "fullName", "handle", "title"),
            )
        )
        title = ZernioService._first_string(normalized, ("title", "subject"))
        if not name and title and title.lower() != "conversation":
            name = title
        if name:
            normalized["participantName"] = name

        last_message = normalized.get("lastMessage") or normalized.get("latestMessage")
        last_text = ZernioService._message_text(last_message)
        if last_text:
            normalized["lastMessage"] = last_text
        last_time = (
            ZernioService._object_string(last_message, ("sentAt", "createdAt", "timestamp"))
            or ZernioService._first_string(
                normalized, ("lastMessageAt", "updatedTime", "updatedAt", "lastActivityAt")
            )
        )
        if last_time:
            normalized["lastMessageAt"] = last_time
        if isinstance(last_message, dict):
            normalized["lastMessageIsOwn"] = ZernioService._message_is_outgoing(last_message)

        return normalized

    @staticmethod
    def _normalize_message(message: Dict) -> Dict:
        if not isinstance(message, dict):
            return message

        normalized = dict(message)
        message_id = (
            normalized.get("_id")
            or normalized.get("id")
            or normalized.get("messageId")
            or normalized.get("message_id")
        )
        if message_id:
            normalized.setdefault("_id", str(message_id))
            normalized.setdefault("id", str(message_id))

        text = ZernioService._message_text(normalized)
        if text:
            normalized["message"] = text

        created_at = ZernioService._first_string(
            normalized, ("sentAt", "createdAt", "created_at", "timestamp", "time")
        )
        if created_at:
            normalized["createdAt"] = created_at

        sender = normalized.get("sender") or normalized.get("from") or normalized.get("user")
        sender_name = ZernioService._object_string(
            sender, ("displayName", "name", "username", "fullName", "handle")
        )
        if sender_name:
            normalized["senderName"] = sender_name
        normalized["isOwn"] = ZernioService._message_is_outgoing(normalized)
        return normalized

    @staticmethod
    def _conversation_participant(conversation: Dict) -> Any:
        for key in ("participant", "sender", "contact", "customer", "user", "from"):
            value = conversation.get(key)
            if isinstance(value, dict):
                return value
        participants = conversation.get("participants")
        if isinstance(participants, list):
            for participant in participants:
                if isinstance(participant, dict):
                    name = ZernioService._object_string(
                        participant,
                        ("displayName", "name", "username", "fullName", "handle", "title"),
                    )
                    if name:
                        return participant
        return None

    @staticmethod
    def _first_string(source: Dict, keys: tuple) -> str:
        for key in keys:
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _object_string(source: Any, keys: tuple) -> str:
        if not isinstance(source, dict):
            return ""
        return ZernioService._first_string(source, keys)

    @staticmethod
    def _message_text(message: Any) -> str:
        if isinstance(message, str):
            return message.strip()
        if not isinstance(message, dict):
            return ""
        text = ZernioService._first_string(
            message, ("message", "text", "content", "body", "caption")
        )
        if text:
            return text
        content = message.get("content")
        if isinstance(content, dict):
            return ZernioService._first_string(content, ("text", "message", "body"))
        return ""

    @staticmethod
    def _message_is_outgoing(message: Dict) -> bool:
        direction = str(message.get("direction") or message.get("type") or "").lower()
        if direction in ("outgoing", "sent", "outbound", "own"):
            return True
        if direction in ("incoming", "received", "inbound"):
            return False
        return bool(
            message.get("isOwn")
            or message.get("fromMe")
            or message.get("outgoing")
            or message.get("is_outgoing")
        )
