from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppError(Exception):
    code: str
    message: str
    details: dict[str, object] | None = None


def as_error_payload(err: AppError, request_id: str) -> dict[str, object]:
    return {
        "error": {
            "code": err.code,
            "message": err.message,
            "details": err.details or {},
            "request_id": request_id,
        }
    }
