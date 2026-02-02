from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone


def configure_logging() -> None:
    level = os.getenv("APP_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(message)s",
    )


def log_json(level: int, message: str, **fields: object) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": logging.getLevelName(level).lower(),
        "msg": message,
        **fields,
    }
    logging.getLogger("floodmvp").log(level, json.dumps(payload, default=str))
