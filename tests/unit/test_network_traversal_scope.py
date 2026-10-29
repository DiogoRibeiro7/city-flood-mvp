from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects.postgresql import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession

import floodmvp.storage.repos.assets as assets_repo


@pytest.mark.parametrize("helper", ["pipes", "assets"])
@pytest.mark.asyncio
async def test_network_lookup_is_scoped_to_start_city(helper: str) -> None:
    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.scalars.return_value.all.return_value = []
    session.execute.return_value = result

    if helper == "pipes":
        found = await assets_repo._list_pipes_by_node(session, "node_1", "upstream", "city_a")
    else:
        found = await assets_repo._list_assets_by_ids(session, {"node_1"}, "city_a")

    assert found == []
    session.execute.assert_awaited_once()
    query = session.execute.await_args.args[0]
    compiled = query.compile(dialect=asyncpg.dialect())
    assert "asset.city_id =" in str(compiled).lower()
    assert "city_a" in compiled.params.values()
    if helper == "pipes":
        assert " ->> " in str(compiled)
        assert "jsonb_extract_path_text" not in str(compiled)


@pytest.mark.asyncio
async def test_starting_from_pipe_includes_adjacent_node(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    starting_pipe = SimpleNamespace(
        asset_id="pipe_1",
        city_id="city_a",
        asset_type="pipe",
        props={"upstream_node_id": "node_1", "downstream_node_id": "node_2"},
    )
    adjacent_node = SimpleNamespace(asset_id="node_1", city_id="city_a", asset_type="node")
    get_asset = AsyncMock(return_value=starting_pipe)
    list_nodes = AsyncMock(side_effect=[[adjacent_node], []])
    list_pipes = AsyncMock(return_value=[])
    monkeypatch.setattr(assets_repo, "get_asset", get_asset)
    monkeypatch.setattr(assets_repo, "_list_assets_by_ids", list_nodes)
    monkeypatch.setattr(assets_repo, "_list_pipes_by_node", list_pipes)

    found = await assets_repo.traverse_network(session, "pipe_1", "upstream", 1)

    assert found == [adjacent_node]
    list_nodes.assert_any_await(session, {"node_1"}, "city_a")
    list_pipes.assert_awaited_once_with(session, "node_1", "upstream", "city_a")
