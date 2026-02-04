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
                "example": {
                    "error": {
                        "code": code,
                        "message": message,
                        "details": details or {},
                        "request_id": request_id,
                    }
                }
            }
        }
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
