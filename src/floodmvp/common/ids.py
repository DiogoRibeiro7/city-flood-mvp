from __future__ import annotations

import uuid


def new_id(prefix: str) -> str:
    """Create a stable, URL-safe-ish id (prefix + uuid4 hex)."""
    if not prefix or not prefix.isidentifier():
        raise ValueError("prefix must be a non-empty identifier-like string")
    return f"{prefix}_{uuid.uuid4().hex}"
