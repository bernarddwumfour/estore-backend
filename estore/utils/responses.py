"""
users/utils/responses.py

Standardized HTTP responses for consistent API behavior
"""

import json
from datetime import datetime
from django.http import JsonResponse
from django.utils import timezone
import uuid


class APIResponse:
    """Factory for standardized API responses"""

    @staticmethod
    def _build_response(
        success: bool,
        message: str,
        data: dict = None,
        errors: dict = None,
        status_code: int = 200,
    ) -> JsonResponse:
        """Build standardized response object"""
        response = {
            "success": success,
            "message": message,
            "data": data or {},
            "errors": errors or {},
        }

        # Remove empty fields
        if not response["data"]:
            del response["data"]
        if not response["errors"]:
            del response["errors"]

        return JsonResponse(response, status=status_code, safe=False)

    @staticmethod
    def success(data: dict = None, message: str = "Success") -> JsonResponse:
        return APIResponse._build_response(True, message, data=data, status_code=200)

    @staticmethod
    def created(data: dict = None, message: str = "Resource created") -> JsonResponse:
        return APIResponse._build_response(True, message, data=data, status_code=201)

    @staticmethod
    def accepted(message: str = "Request accepted") -> JsonResponse:
        return APIResponse._build_response(True, message, status_code=202)

    @staticmethod
    def no_content() -> JsonResponse:
        return JsonResponse({}, status=204)

    @staticmethod
    def bad_request(message: str = "Bad request", errors: dict = None) -> JsonResponse:
        return APIResponse._build_response(
            False, message, errors=errors, status_code=400
        )

    @staticmethod
    def unauthorized(message: str = "Authentication required") -> JsonResponse:
        return APIResponse._build_response(False, message, status_code=401)

    @staticmethod
    def forbidden(message: str = "Insufficient permissions") -> JsonResponse:
        return APIResponse._build_response(False, message, status_code=403)

    @staticmethod
    def not_found(message: str = "Resource not found") -> JsonResponse:
        return APIResponse._build_response(False, message, status_code=404)

    @staticmethod
    def conflict(
        message: str = "Resource conflict", errors: dict = None
    ) -> JsonResponse:
        return APIResponse._build_response(
            False, message, errors=errors, status_code=409
        )

    @staticmethod
    def validation_error(errors: dict) -> JsonResponse:
        return APIResponse._build_response(
            False, "Validation failed", errors=errors, status_code=422
        )

    @staticmethod
    def server_error(message: str = "Internal server error") -> JsonResponse:
        return APIResponse._build_response(False, message, status_code=500)

    @staticmethod
    def service_unavailable(
        message: str = "Service temporarily unavailable",
    ) -> JsonResponse:
        return APIResponse._build_response(False, message, status_code=503)
