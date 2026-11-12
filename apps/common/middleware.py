from django.conf import settings
from django.utils.deprecation import MiddlewareMixin
from django.utils.module_loading import import_string
from django_ratelimit.exceptions import Ratelimited


class RateLimitExceptionMiddleware(MiddlewareMixin):
    """Return the configured rate-limit response for decorator exceptions.

    django-ratelimit raises ``Ratelimited``, which inherits from Django's
    ``PermissionDenied``. Without handling it here, Django converts it to a
    403 response and bypasses the configured ``RATELIMIT_VIEW``.
    """

    def process_exception(self, request, exception):
        if not isinstance(exception, Ratelimited):
            return None

        rate_limit_view = getattr(settings, "RATELIMIT_VIEW", None)
        if not rate_limit_view:
            return None

        handler = import_string(rate_limit_view) if isinstance(rate_limit_view, str) else rate_limit_view
        return handler(request, exception)
