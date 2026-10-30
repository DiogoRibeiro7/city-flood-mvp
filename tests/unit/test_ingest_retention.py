"""Check that ingestion retention uses a bounded, non-blocking SQL statement."""

from __future__ import annotations

from typing import Any, cast

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.storage.repos.ingest import prune_expired_idempotency


class _ResultStub:
    rowcount = 2


class _SessionStub:
    def __init__(self) -> None:
        self.statement: Any = None

    async def execute(self, statement: Any) -> _ResultStub:
        self.statement = statement
        return _ResultStub()


@pytest.mark.asyncio
async def test_prune_uses_bounded_skip_locked_delete() -> None:
    session = _SessionStub()

    removed = await prune_expired_idempotency(cast(AsyncSession, session), batch_size=2)

    assert removed == 2
    assert session.statement is not None
    sql = str(session.statement.compile(dialect=postgresql.dialect()))
    assert "DELETE FROM ingest_idempotency" in sql
    assert "LIMIT" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "created_at < now()" in sql


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [0, -1, True, 1.5, "10"])
async def test_prune_rejects_non_positive_or_non_integer_batch_size(batch_size: Any) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        await prune_expired_idempotency(cast(AsyncSession, _SessionStub()), batch_size=batch_size)
