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
        found = await assets_repo._list_pipes_by_nodes(
            session, {"node_1", "node_2"}, "upstream", "city_a"
        )
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
        assert " IN " in str(compiled)
    assert "ORDER BY asset.asset_id" in str(compiled)


@pytest.mark.parametrize("helper", ["pipes", "assets"])
@pytest.mark.asyncio
async def test_empty_network_lookup_avoids_database_access(helper: str) -> None:
    session = AsyncMock(spec=AsyncSession)

    if helper == "pipes":
        found = await assets_repo._list_pipes_by_nodes(session, set(), "upstream", "city_a")
    else:
        found = await assets_repo._list_assets_by_ids(session, [], "city_a")

    assert found == []
    session.execute.assert_not_awaited()


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
    monkeypatch.setattr(assets_repo, "_list_pipes_by_nodes", list_pipes)

    found = await assets_repo.traverse_network(session, "pipe_1", "upstream", 1)

    assert found == [adjacent_node]
    list_nodes.assert_any_await(session, {"node_1"}, "city_a")
    list_pipes.assert_awaited_once_with(session, {"node_1"}, "upstream", "city_a")


@pytest.mark.asyncio
async def test_branching_traversal_batches_each_depth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A broad layer issues one pipe query, not a query per frontier node."""
    session = AsyncMock(spec=AsyncSession)

    def node(asset_id: str) -> SimpleNamespace:
        return SimpleNamespace(asset_id=asset_id, city_id="city_a", asset_type="node")

    def pipe(asset_id: str, upstream: str, downstream: str) -> SimpleNamespace:
        return SimpleNamespace(
            asset_id=asset_id,
            city_id="city_a",
            asset_type="pipe",
            props={"upstream_node_id": upstream, "downstream_node_id": downstream},
        )

    starting_node = node("n0")
    first_pipes = [pipe("p1", "n0", "n1"), pipe("p2", "n0", "n2")]
    second_pipes = [pipe("p3", "n1", "n3")]
    get_asset = AsyncMock(return_value=starting_node)
    list_pipes = AsyncMock(side_effect=[first_pipes, second_pipes])
    list_nodes = AsyncMock(side_effect=[[node("n1"), node("n2")], [node("n3")]])
    monkeypatch.setattr(assets_repo, "get_asset", get_asset)
    monkeypatch.setattr(assets_repo, "_list_pipes_by_nodes", list_pipes)
    monkeypatch.setattr(assets_repo, "_list_assets_by_ids", list_nodes)

    found = await assets_repo.traverse_network(session, "n0", "downstream", 2)

    assert [asset.asset_id for asset in found] == ["p1", "p2", "n1", "n2", "p3", "n3"]
    assert list_pipes.await_count == 2
    assert list_pipes.await_args_list[0].args == (session, {"n0"}, "downstream", "city_a")
    assert list_pipes.await_args_list[1].args == (session, {"n1", "n2"}, "downstream", "city_a")
