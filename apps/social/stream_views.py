"""Authenticated server-sent notifications for the social inbox."""
import time

from django.db import close_old_connections
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_GET
from django_ratelimit.decorators import ratelimit

from apps.social.models import SocialInboxRevision
from apps.users.decorators.auth import role_required


def inbox_event_stream():
    # The stream is deliberately bounded so credentials are checked on reconnect.
    started = time.monotonic()
    last_revision = SocialInboxRevision.objects.filter(pk=1).values_list("revision", flat=True).first() or 0
    last_heartbeat = started
    try:
        yield "retry: 3000\nevent: ready\ndata: {}\n\n"
        while time.monotonic() - started < 45:
            close_old_connections()
            revision = SocialInboxRevision.objects.filter(pk=1).values_list("revision", flat=True).first() or 0
            if revision != last_revision:
                last_revision = revision
                yield 'event: inbox.changed\ndata: {}\n\n'
            now = time.monotonic()
            if now - last_heartbeat >= 15:
                yield ": heartbeat\n\n"
                last_heartbeat = now
            time.sleep(2)
    finally:
        close_old_connections()


@require_GET
@role_required("admin", "staff")
@ratelimit(key="user", rate="600/h", method="GET", block=True)
def social_inbox_stream(request):
    response = StreamingHttpResponse(inbox_event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    response["X-Accel-Buffering"] = "no"
    return response
