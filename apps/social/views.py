"""
Social views — admin API endpoints for social posts and the Zernio inbox.
"""

import logging

from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from apps.common.logging import log_action, LogSeverity
from apps.social.schemas import (
    serialize_social_post,
    serialize_social_post_list,
    validate_comment_action,
    validate_comment_reply,
    validate_message_send,
    validate_post_approve,
    validate_post_create,
)
from apps.social.selectors import get_admin_social_posts, get_social_post_by_id
from apps.social.services import SocialPostService
from apps.social.zernio_service import ZernioService
from apps.users.decorators.auth import (
    json_request_required,
    jwt_required,
    role_required,
)
from estore.utils.responses import APIResponse

logger = logging.getLogger(__name__)
APP_NAME = "social"


def _first_post_account_id(post):
    """Return the first account id from a saved Zernio platforms payload."""
    for platform in post.platforms or []:
        if not isinstance(platform, dict):
            continue
        account_id = platform.get("accountId") or platform.get("account_id")
        if account_id:
            return str(account_id)
    return None


def _post_account_id_from_request(request, post, cleaned=None):
    """Prefer an explicit account id, then fall back to the post target."""
    cleaned = cleaned or {}
    return (
        cleaned.get("account_id")
        or request.GET.get("account_id")
        or request.GET.get("accountId")
        or _first_post_account_id(post)
    )


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_accounts(request):
    """Admin: list connected Zernio social accounts."""
    try:
        if not ZernioService.is_configured():
            return APIResponse.service_unavailable("Social media service not configured")

        accounts, error = ZernioService.list_accounts()
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(
            data={"accounts": accounts},
            message="Connected accounts retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin social accounts error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_post_list(request):
    """Admin: list social posts with filters and pagination."""
    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 20)), 100)
        status = request.GET.get("status") or None
        source = request.GET.get("source") or None
        search = request.GET.get("search") or None

        posts, total, pagination_meta = get_admin_social_posts(
            page=page,
            limit=limit,
            status=status,
            source=source,
            search=search,
            date_from=request.GET.get("date_from") or None,
            date_to=request.GET.get("date_to") or None,
        )

        return APIResponse.success(
            data={
                "posts": serialize_social_post_list(posts),
                "total": total,
                "pagination": pagination_meta,
            },
            message="Social posts retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin social post list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='60/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_social_post_create(request):
    """Admin: compose and send (or schedule) a social post."""
    try:
        cleaned, errors = validate_post_create(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)

        post, error = SocialPostService.create_manual_post(cleaned, request.user)
        if error:
            return APIResponse.bad_request(
                error if isinstance(error, str) else "Failed to send post",
                errors=error if isinstance(error, dict) else None,
            )

        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action="social_post_create",
            description="Social post sent to connected platforms",
            status_code=201,
            user=request.user,
            request=request,
            app_name=APP_NAME,
            extra={"social_post_id": str(post.id)},
        )
        return APIResponse.created(
            data=serialize_social_post(post),
            message="Social post sent successfully",
        )
    except Exception as e:
        logger.error(f"Admin social post create error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='60/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_social_post_approve(request, post_id):
    """Admin: approve a queued post (with optional edits) and publish it."""
    try:
        post = get_social_post_by_id(post_id)
        if not post:
            return APIResponse.not_found("Social post not found")

        cleaned, errors = validate_post_approve(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)

        post, error = SocialPostService.approve_post(post, cleaned, request.user)
        if error:
            if isinstance(error, dict):
                return APIResponse.validation_error(error)
            return APIResponse.bad_request(error)

        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action="social_post_approve",
            description="Queued social post approved and published",
            status_code=200,
            user=request.user,
            request=request,
            app_name=APP_NAME,
            extra={"social_post_id": str(post.id)},
        )
        return APIResponse.success(
            data=serialize_social_post(post),
            message="Social post approved and sent",
        )
    except Exception as e:
        logger.error(f"Admin social post approve error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='60/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_post_reject(request, post_id):
    """Admin: reject a queued post."""
    try:
        post = get_social_post_by_id(post_id)
        if not post:
            return APIResponse.not_found("Social post not found")

        post, error = SocialPostService.reject_post(post, request.user)
        if error:
            if isinstance(error, dict):
                return APIResponse.validation_error(error)
            return APIResponse.bad_request(error)

        return APIResponse.success(
            data=serialize_social_post(post),
            message="Social post rejected",
        )
    except Exception as e:
        logger.error(f"Admin social post reject error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@ratelimit(key='ip', rate='60/h', method='DELETE', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_post_delete(request, post_id):
    """Admin: delete a social post (also removes it from Zernio if sent)."""
    try:
        post = get_social_post_by_id(post_id)
        if not post:
            return APIResponse.not_found("Social post not found")

        deleted, error = SocialPostService.delete_post(post)
        if error:
            return APIResponse.bad_request(error)

        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action="social_post_delete",
            description="Social post deleted",
            status_code=200,
            user=request.user,
            request=request,
            app_name=APP_NAME,
            extra={"social_post_id": str(post_id)},
        )
        return APIResponse.success(message="Social post deleted")
    except Exception as e:
        logger.error(f"Admin social post delete error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_post_analytics(request, post_id):
    """Admin: analytics (impressions, reach, engagement, ...) for a sent post."""
    try:
        post = get_social_post_by_id(post_id)
        if not post:
            return APIResponse.not_found("Social post not found")
        if not post.zernio_post_id:
            return APIResponse.bad_request("This post has not been published yet")

        account_id = _post_account_id_from_request(request, post)
        analytics, error = ZernioService.get_post_analytics(
            post.zernio_post_id, account_id=account_id
        )
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(
            data={"analytics": analytics},
            message="Analytics retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin social post analytics error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_post_comments(request, post_id):
    """Admin: list comments on a sent social post."""
    try:
        post = get_social_post_by_id(post_id)
        if not post:
            return APIResponse.not_found("Social post not found")
        if not post.zernio_post_id:
            return APIResponse.bad_request("This post has not been published yet")

        account_id = _post_account_id_from_request(request, post)
        comments, error = ZernioService.list_post_comments(
            post.zernio_post_id, account_id=account_id
        )
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(
            data={"comments": comments},
            message="Comments retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin social post comments error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_social_comment_reply(request, post_id):
    """Admin: reply to a comment on a sent social post."""
    try:
        post = get_social_post_by_id(post_id)
        if not post:
            return APIResponse.not_found("Social post not found")
        if not post.zernio_post_id:
            return APIResponse.bad_request("This post has not been published yet")

        cleaned, errors = validate_comment_reply(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)

        account_id = _post_account_id_from_request(request, post, cleaned)
        result, error = ZernioService.reply_comment(
            post.zernio_post_id,
            cleaned["comment_id"],
            cleaned["message"],
            account_id=account_id,
            parent_cid=cleaned.get("parent_cid"),
            root_uri=cleaned.get("root_uri"),
            root_cid=cleaned.get("root_cid"),
        )
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(message="Reply sent successfully")
    except Exception as e:
        logger.error(f"Admin social comment reply error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_social_comment_action(request, post_id):
    """Admin: hide/unhide/like/unlike a comment on a sent social post."""
    try:
        post = get_social_post_by_id(post_id)
        if not post:
            return APIResponse.not_found("Social post not found")
        if not post.zernio_post_id:
            return APIResponse.bad_request("This post has not been published yet")

        cleaned, errors = validate_comment_action(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)

        account_id = _post_account_id_from_request(request, post, cleaned)
        result, error = ZernioService.comment_action(
            post.zernio_post_id,
            cleaned["comment_id"],
            cleaned["action"],
            account_id=account_id,
            cid=cleaned.get("cid"),
            like_uri=cleaned.get("like_uri"),
        )
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(message=f"Comment {cleaned['action']} successful")
    except Exception as e:
        logger.error(f"Admin social comment action error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_conversations(request):
    """Admin: list inbox conversations (DMs) across platforms."""
    try:
        if not ZernioService.is_configured():
            return APIResponse.service_unavailable("Social media service not configured")

        platform = request.GET.get("platform") or None
        conversations, error = ZernioService.list_conversations(platform)
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(
            data={"conversations": conversations},
            message="Conversations retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin social conversations error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_messages(request, conversation_id):
    """Admin: list messages in a conversation."""
    try:
        if not ZernioService.is_configured():
            return APIResponse.service_unavailable("Social media service not configured")

        account_id = request.GET.get("account_id") or request.GET.get("accountId")
        messages, error = ZernioService.list_messages(
            conversation_id, account_id=account_id
        )
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(
            data={"messages": messages},
            message="Messages retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin social messages error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_social_message_send(request, conversation_id):
    """Admin: send a DM reply in a conversation."""
    try:
        if not ZernioService.is_configured():
            return APIResponse.service_unavailable("Social media service not configured")

        cleaned, errors = validate_message_send(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)

        result, error = ZernioService.send_message(
            conversation_id, cleaned["message"], account_id=cleaned["account_id"]
        )
        if error:
            return APIResponse.bad_request(error)

        return APIResponse.success(message="Message sent successfully")
    except Exception as e:
        logger.error(f"Admin social message send error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET", "POST"])
@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_config(request):
    """Admin: read or update the social integration mode (test/live)."""
    from apps.social.models import SocialConfig
    from apps.social.schemas import validate_config_update

    try:
        config = SocialConfig.get()

        if request.method == "POST":
            import json as json_lib
            try:
                payload = json_lib.loads(request.body or b"{}")
            except ValueError:
                return APIResponse.bad_request("Invalid JSON body")

            cleaned, errors = validate_config_update(payload)
            if errors:
                return APIResponse.validation_error(errors)

            config.mode = cleaned["mode"]
            config.save()

            if config.mode == SocialConfig.MODE_TEST:
                from apps.social.sandbox import SandboxSocialService
                SandboxSocialService.seed_demo_conversations()

            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action="social_config_update",
                description=f"Social integration switched to {config.mode} mode",
                status_code=200,
                user=request.user,
                request=request,
                app_name=APP_NAME,
                extra={"mode": config.mode},
            )

        return APIResponse.success(
            data={
                "mode": config.mode,
                "live_configured": bool(ZernioService.API_KEY),
            },
            message="Social configuration retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin social config error: {str(e)}")
        return APIResponse.server_error()


def _not_configured_guard():
    """Shared 503 for config endpoints when Zernio is unavailable."""
    if not ZernioService.is_configured():
        return APIResponse.service_unavailable("Social media service not configured")
    return None


@csrf_exempt
@require_http_methods(["GET", "POST"])
@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_profiles(request):
    """Admin: list profiles or create one."""
    from apps.social.schemas import validate_profile_upsert
    import json as json_lib

    try:
        guard = _not_configured_guard()
        if guard:
            return guard

        if request.method == "POST":
            try:
                payload = json_lib.loads(request.body or b"{}")
            except ValueError:
                return APIResponse.bad_request("Invalid JSON body")

            cleaned, errors = validate_profile_upsert(payload)
            if errors:
                return APIResponse.validation_error(errors)

            profile, error = ZernioService.create_profile(
                cleaned["name"], cleaned.get("description", "")
            )
            if error:
                return APIResponse.bad_request(error)

            log_action(
                logger=logger,
                severity=LogSeverity.INFO,
                action="social_profile_create",
                description=f"Social profile '{cleaned['name']}' created",
                status_code=201,
                user=request.user,
                request=request,
                app_name=APP_NAME,
            )
            return APIResponse.created(
                data={"profile": profile}, message="Profile created successfully"
            )

        profiles, error = ZernioService.list_profiles()
        if error:
            return APIResponse.bad_request(error)
        return APIResponse.success(
            data={"profiles": profiles}, message="Profiles retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Admin social profiles error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["PATCH", "DELETE"])
@ratelimit(key='ip', rate='120/h', method='PATCH', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_profile_detail(request, profile_id):
    """Admin: rename (PATCH) or delete (DELETE) a profile."""
    from apps.social.schemas import validate_profile_upsert
    import json as json_lib

    try:
        guard = _not_configured_guard()
        if guard:
            return guard

        if request.method == "DELETE":
            _, error = ZernioService.delete_profile(profile_id)
            if error:
                return APIResponse.bad_request(error)
            log_action(
                logger=logger,
                severity=LogSeverity.WARNING,
                action="social_profile_delete",
                description="Social profile deleted",
                status_code=200,
                user=request.user,
                request=request,
                app_name=APP_NAME,
                extra={"profile_id": str(profile_id)},
            )
            return APIResponse.success(message="Profile deleted")

        try:
            payload = json_lib.loads(request.body or b"{}")
        except ValueError:
            return APIResponse.bad_request("Invalid JSON body")

        cleaned, errors = validate_profile_upsert(payload, partial=True)
        if errors:
            return APIResponse.validation_error(errors)
        if not cleaned:
            return APIResponse.bad_request("Nothing to update")

        profile, error = ZernioService.update_profile(profile_id, cleaned)
        if error:
            return APIResponse.bad_request(error)
        return APIResponse.success(
            data={"profile": profile}, message="Profile updated successfully"
        )
    except Exception as e:
        logger.error(f"Admin social profile detail error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@ratelimit(key='ip', rate='60/h', method='DELETE', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_account_disconnect(request, account_id):
    """Admin: disconnect a social account."""
    try:
        guard = _not_configured_guard()
        if guard:
            return guard

        _, error = ZernioService.disconnect_account(account_id)
        if error:
            return APIResponse.bad_request(error)

        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action="social_account_disconnect",
            description="Social account disconnected",
            status_code=200,
            user=request.user,
            request=request,
            app_name=APP_NAME,
            extra={"account_id": str(account_id)},
        )
        return APIResponse.success(message="Account disconnected")
    except Exception as e:
        logger.error(f"Admin social account disconnect error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='120/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_social_account_move(request, account_id):
    """Admin: move an account to another profile."""
    from apps.social.schemas import validate_account_move

    try:
        guard = _not_configured_guard()
        if guard:
            return guard

        cleaned, errors = validate_account_move(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)

        account, error = ZernioService.move_account(account_id, cleaned["profile_id"])
        if error:
            return APIResponse.bad_request(error)
        return APIResponse.success(
            data={"account": account}, message="Account moved successfully"
        )
    except Exception as e:
        logger.error(f"Admin social account move error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["POST"])
@ratelimit(key='ip', rate='60/h', method='POST', block=True)
@jwt_required
@role_required("admin", "staff")
@json_request_required
def admin_social_account_connect(request):
    """Admin: start connecting a new account.

    Live mode returns an OAuth URL to open; test mode connects instantly.
    """
    from apps.social.schemas import validate_connect

    try:
        guard = _not_configured_guard()
        if guard:
            return guard

        cleaned, errors = validate_connect(request.json_data)
        if errors:
            return APIResponse.validation_error(errors)

        result, error = ZernioService.get_connect_url(
            cleaned["platform"], cleaned.get("profile_id")
        )
        if error:
            return APIResponse.bad_request(error)

        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action="social_account_connect",
            description=f"Account connection started for {cleaned['platform']}",
            status_code=200,
            user=request.user,
            request=request,
            app_name=APP_NAME,
            extra={"platform": cleaned["platform"]},
        )
        return APIResponse.success(
            data=result, message="Connection started"
        )
    except Exception as e:
        logger.error(f"Admin social account connect error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_usage(request):
    """Admin: Zernio plan usage stats."""
    try:
        guard = _not_configured_guard()
        if guard:
            return guard

        stats, error = ZernioService.get_usage_stats()
        if error:
            return APIResponse.bad_request(error)
        return APIResponse.success(
            data={"usage": stats}, message="Usage retrieved successfully"
        )
    except Exception as e:
        logger.error(f"Admin social usage error: {str(e)}")
        return APIResponse.server_error()


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024
MAX_VIDEO_SIZE = 50 * 1024 * 1024
MAX_MEDIA_UPLOAD_FILES = 10


@csrf_exempt
@require_http_methods(["POST"])
@jwt_required
@role_required("admin", "staff")
@ratelimit(key='user', rate='60/h', method='POST', block=True)
def admin_social_media_upload(request):
    """Admin: upload one or more images/videos to the social media library."""
    import os as os_module
    from apps.social.models import SocialMedia
    from apps.social.schemas import serialize_social_media

    try:
        uploads = request.FILES.getlist("files") or request.FILES.getlist("file")
        if not uploads:
            return APIResponse.bad_request("No file provided")
        if len(uploads) > MAX_MEDIA_UPLOAD_FILES:
            return APIResponse.bad_request(
                f"Upload up to {MAX_MEDIA_UPLOAD_FILES} files at a time"
            )

        validated_uploads = []
        for upload in uploads:
            ext = os_module.path.splitext(upload.name)[1].lower()

            if ext in IMAGE_EXTENSIONS:
                media_type = SocialMedia.TYPE_IMAGE
                max_size = MAX_IMAGE_SIZE
            elif ext in VIDEO_EXTENSIONS:
                media_type = SocialMedia.TYPE_VIDEO
                max_size = MAX_VIDEO_SIZE
            else:
                allowed = ", ".join(sorted(IMAGE_EXTENSIONS | VIDEO_EXTENSIONS))
                return APIResponse.bad_request(
                    f"Invalid file type for {upload.name}. Allowed: {allowed}"
                )

            if upload.size > max_size:
                limit_mb = max_size // (1024 * 1024)
                return APIResponse.bad_request(
                    f"{upload.name} is too large. Maximum size for {media_type}s is {limit_mb}MB"
                )
            validated_uploads.append((upload, media_type))

        created_media = []
        for upload, media_type in validated_uploads:
            media = SocialMedia.objects.create(
                file=upload,
                media_type=media_type,
                name=upload.name[:200],
                uploaded_by=request.user,
            )
            created_media.append(media)

        log_action(
            logger=logger,
            severity=LogSeverity.INFO,
            action="social_media_upload",
            description=f"{len(created_media)} social media file(s) uploaded",
            status_code=201,
            user=request.user,
            request=request,
            app_name=APP_NAME,
            extra={
                "media_ids": [str(media.id) for media in created_media],
                "count": len(created_media),
            },
        )
        if len(created_media) == 1:
            return APIResponse.created(
                data=serialize_social_media(created_media[0]),
                message="Media uploaded successfully",
            )
        return APIResponse.created(
            data={"media": [serialize_social_media(media) for media in created_media]},
            message="Media uploaded successfully",
        )
    except Exception as e:
        logger.error(f"Admin social media upload error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["GET"])
@ratelimit(key='ip', rate='300/h', method='GET', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_media_list(request):
    """Admin: browse the social media library."""
    from apps.social.selectors import get_media_library
    from apps.social.schemas import serialize_social_media

    try:
        page = int(request.GET.get("page", 1))
        limit = min(int(request.GET.get("limit", 24)), 100)
        media_type = request.GET.get("media_type") or None
        search = request.GET.get("search") or None

        media, total, pagination_meta = get_media_library(
            page=page, limit=limit, media_type=media_type, search=search
        )
        return APIResponse.success(
            data={
                "media": [serialize_social_media(m) for m in media],
                "total": total,
                "pagination": pagination_meta,
            },
            message="Media library retrieved successfully",
        )
    except Exception as e:
        logger.error(f"Admin social media list error: {str(e)}")
        return APIResponse.server_error()


@csrf_exempt
@require_http_methods(["DELETE"])
@ratelimit(key='ip', rate='60/h', method='DELETE', block=True)
@jwt_required
@role_required("admin", "staff")
def admin_social_media_delete(request, media_id):
    """Admin: delete a file from the social media library."""
    from apps.social.models import SocialMedia

    try:
        media = SocialMedia.objects.filter(id=media_id).first()
        if not media:
            return APIResponse.not_found("Media not found")

        try:
            media.file.delete(save=False)
        except Exception as storage_error:
            logger.warning(f"Could not delete media file from storage: {str(storage_error)}")
        media.delete()

        log_action(
            logger=logger,
            severity=LogSeverity.WARNING,
            action="social_media_delete",
            description="Social media file deleted",
            status_code=200,
            user=request.user,
            request=request,
            app_name=APP_NAME,
            extra={"media_id": str(media_id)},
        )
        return APIResponse.success(message="Media deleted")
    except Exception as e:
        logger.error(f"Admin social media delete error: {str(e)}")
        return APIResponse.server_error()
