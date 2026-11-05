from __future__ import annotations

from typing import Any


def error_response(
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    request_id: str = "req_example",
) -> dict[str, Any]:
    return {
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                "example": {
                    "error": {
                        "code": code,
                        "message": message,
                        "details": details or {},
                        "request_id": request_id,
                    }
                },
            }
        }
    }


def error_responses(description: str, *errors: tuple[str, str]) -> dict[str, Any]:
    """Describe multiple runtime error codes sharing one HTTP status."""
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                "examples": {
                    code.lower(): {
                        "value": error_response(code, message)["content"]["application/json"][
                            "example"
                        ]
                    }
                    for code, message in errors
                },
            }
        },
    }


MIDDLEWARE_RESPONSES: dict[int | str, dict[str, Any]] = {
    413: {
        **error_response("REQUEST_TOO_LARGE", "Request body too large"),
        "description": "Request body exceeds configured REQUEST_MAX_BYTES; details includes max_bytes.",
    },
    429: error_responses(
        "Per-client or tenant request quota exceeded; tenant rejection details includes tenant_id.",
        ("RATE_LIMITED", "Too many requests"),
        ("TENANT_RATE_LIMITED", "Tenant request quota exceeded"),
    ),
    504: {
        **error_response("REQUEST_TIMEOUT", "Request timed out"),
        "description": "Upload or handler exceeds configured REQUEST_TIMEOUT_S; details includes timeout_s.",
    },
}


RESP_INVALID_ARGUMENT = error_response(
    code="INVALID_ARGUMENT",
    message="Validation error",
)

RESP_UNAUTHORIZED_API_KEY = error_response(
    code="UNAUTHORIZED",
    message="Missing API key",
)

RESP_FORBIDDEN_API_KEY = error_response(
    code="FORBIDDEN",
    message="Invalid API key",
)

RESP_UNAUTHORIZED_BEARER = error_response(
    code="UNAUTHORIZED",
    message="Unauthorized",
)

RESP_FORBIDDEN_BEARER = error_response(
    code="FORBIDDEN",
    message="Forbidden",
)
