from __future__ import annotations

import logging
import os


def configure_logging() -> None:
    level = os.getenv("APP_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(asctime)s %(name)s - %(message)s",
    )
