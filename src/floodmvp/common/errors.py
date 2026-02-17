from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AppError(Exception):
    code: str
    message: str
    details: dict[str, object] | None = None
    status_code: int = 400


def as_error_payload(err: AppError, request_id: str) -> dict[str, object]:
    return {
        "error": {
            "code": err.code,
            "message": err.message,
            "details": err.details or {},
            "request_id": request_id,
        }
    }


def as_error_payload_raw(
    code: str,
    message: str,
    details: dict[str, object] | None,
    request_id: str,
) -> dict[str, object]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
            "request_id": request_id,
        }
    }
