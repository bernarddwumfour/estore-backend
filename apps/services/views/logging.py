"""Structured request logging for the service catalog."""
import logging
import time
from functools import wraps

from django_ratelimit.exceptions import Ratelimited

from apps.common.logging import LogSeverity, log_action

logger = logging.getLogger(__name__)


def log_service_request(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        started = time.monotonic()
        status = 500
        try:
            response = view(request, *args, **kwargs)
            status = response.status_code
            return response
        except Ratelimited:
            status = 429
            raise
        except Exception:
            logger.exception("Service request failed: %s", view.__name__)
            raise
        finally:
            severity = LogSeverity.ERROR if status >= 500 else (
                LogSeverity.WARNING if status >= 400 else LogSeverity.INFO
            )
            log_action(
                logger=logger, severity=severity, action=view.__name__,
                description="Service catalog request completed", status_code=status,
                user=getattr(request, "user", None), request=request, app_name="services",
                extra={"duration_ms": round((time.monotonic() - started) * 1000, 2),
                       "path": request.path, "method": request.method},
            )
    return wrapped
