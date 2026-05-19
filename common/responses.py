# common/responses.py
from django.http import JsonResponse


# ─── Success Responses ────────────────────────────────────────────

def ok(data=None, message="Success"):
    """200 — General success, typically for GET."""
    return JsonResponse(_envelope(data=data, message=message), status=200)


def created(data=None, message="Resource created successfully."):
    """201 — Something was created, return the new resource."""
    return JsonResponse(_envelope(data=data, message=message), status=201)


def no_content():
    """204 — Success but nothing to return (e.g. DELETE)."""
    return JsonResponse({}, status=204)


# ─── Client Error Responses ───────────────────────────────────────

def bad_request(message="Bad request.", errors=None):
    """400 — Malformed input or failed validation."""
    return JsonResponse(_envelope(message=message, errors=errors), status=400)


def unauthorized(message="Authentication required."):
    """401 — No credentials or invalid token."""
    return JsonResponse(_envelope(message=message), status=401)


def forbidden(message="You do not have permission to perform this action."):
    """403 — Authenticated but not allowed."""
    return JsonResponse(_envelope(message=message), status=403)


def not_found(message="Resource not found."):
    """404 — Resource doesn't exist."""
    return JsonResponse(_envelope(message=message), status=404)


def method_not_allowed(message="Method not allowed."):
    """405 — Wrong HTTP method used."""
    return JsonResponse(_envelope(message=message), status=405)


def conflict(message="Resource already exists."):
    """409 — Duplicate resource."""
    return JsonResponse(_envelope(message=message), status=409)


def unprocessable(message="Unprocessable request.", errors=None):
    """422 — Input is valid but breaks business rules."""
    return JsonResponse(_envelope(message=message, errors=errors), status=422)


# ─── Server Error Responses ───────────────────────────────────────

def server_error(message="An unexpected error occurred."):
    """500 — Something broke on your side."""
    return JsonResponse(_envelope(message=message), status=500)


# ─── Private: Consistent Response Shape ───────────────────────────

def _envelope(data=None, message=None, errors=None):
    """
    Every response from this API shares the same shape:
    {
        "data": { ... } or null,
        "message": "..." or null,
        "errors": { ... } or null
    }
    """
    payload = {}
    if data is not None:
        payload["data"] = data
    if message is not None:
        payload["message"] = message
    if errors is not None:
        payload["errors"] = errors
    return payload