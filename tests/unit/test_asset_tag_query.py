from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects.postgresql import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.storage.repos.assets import list_assets


@pytest.mark.parametrize(
    ("tags", "unique_tags"),
    [
        ([("basin", "ne"), ("basin", "ne")], [("basin", "ne")]),
        (
            [("basin", "ne"), ("priority", "critical"), ("basin", "ne")],
            [("basin", "ne"), ("priority", "critical")],
        ),
    ],
)
@pytest.mark.asyncio
async def test_tag_query_counts_distinct_requested_filters(
    tags: list[tuple[str, str]], unique_tags: list[tuple[str, str]]
) -> None:
    """Duplicate requested tags must not increase the required match count."""
    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    assets = await list_assets(
        session,
        city_id="city_porto_mvp",
        asset_type=None,
        bbox=None,
        near=None,
        radius_m=None,
        tags=tags,
        limit=20,
        offset=0,
    )

    assert assets == []
    session.execute.assert_awaited_once()
    query = session.execute.await_args.args[0]
    compiled = query.compile(dialect=asyncpg.dialect())
    sql = str(compiled).lower()
    assert "having count(*)" in sql
    assert "concat" not in sql
    assert unique_tags in compiled.params.values()
    assert len(unique_tags) in compiled.params.values()
