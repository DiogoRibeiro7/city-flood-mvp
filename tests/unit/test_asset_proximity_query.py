from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects.postgresql import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.storage.repos.assets import list_assets


@pytest.mark.asyncio
async def test_near_search_uses_geography_on_both_geometries() -> None:
    """A metre-based radius must not use latitude-distorted EPSG:3857."""
    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    nearby = await list_assets(
        session,
        city_id="city_porto_mvp",
        asset_type=None,
        bbox=None,
        near=(-8.61, 41.15),
        radius_m=500,
        tags=None,
        limit=20,
        offset=0,
    )

    assert nearby == []
    session.execute.assert_awaited_once()
    query = session.execute.await_args.args[0]
    compiled = query.compile(dialect=asyncpg.dialect())
    sql = str(compiled).lower()
    assert "st_dwithin" in sql
    assert sql.count(" as geography(") == 2
    assert "st_transform" not in sql
    assert 500 in compiled.params.values()
