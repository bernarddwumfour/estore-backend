"""Trust session credentials only from an authenticated server-side BFF."""
import ipaddress
from django.conf import settings
from django.utils.crypto import constant_time_compare
from estore.utils.responses import APIResponse
from apps.users.services.browser_session_service import resolve_session


class BFFMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        supplied = request.headers.get("X-BFF-Key")
        request.is_bff = False
        if supplied is not None:
            if not settings.BFF_SHARED_SECRET or not constant_time_compare(supplied, settings.BFF_SHARED_SECRET):
                return APIResponse.forbidden()
            request.is_bff = True
            # Only the authenticated BFF may supply a platform-verified client IP.
            client_ip = request.headers.get("X-BFF-Client-IP")
            if client_ip:
                try:
                    request.META["REMOTE_ADDR"] = str(ipaddress.ip_address(client_ip))
                except ValueError:
                    return APIResponse.bad_request("Invalid client address")
            token = request.headers.get("X-BFF-Session", "")
            if token:
                session = resolve_session(token)
                if not session:
                    return APIResponse.unauthorized("Session expired")
                request.bff_user = session.user
                request.user = session.user
        response = self.get_response(request)
        if request.is_bff:
            response["Cache-Control"] = "no-store"
        return response
