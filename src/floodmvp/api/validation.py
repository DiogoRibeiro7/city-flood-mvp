from __future__ import annotations

import datetime as dt

from floodmvp.common.errors import AppError
from floodmvp.common.time import parse_iso8601


def parse_query_timestamp(value: str, parameter: str) -> dt.datetime:
    """Parse a query timestamp or return the API's invalid-argument error.

    The shared timestamp parser raises ``ValueError`` for malformed ISO 8601
    strings. Query parameters need a structured HTTP 400 response instead.
    """
    try:
        return parse_iso8601(value)
    except ValueError as exc:
        raise AppError(
            code="INVALID_ARGUMENT",
            message=f"'{parameter}' must be a valid ISO 8601 timestamp",
        ) from exc
