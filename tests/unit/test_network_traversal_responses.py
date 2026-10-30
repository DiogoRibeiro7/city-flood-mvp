from __future__ import annotations

from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import floodmvp.api.routers.assets as assets_router
import floodmvp.storage.repos.assets as assets_repo
from floodmvp.api.main import app
from floodmvp.storage.db import get_session


@pytest.fixture()
async def client() -> AsyncIterator[AsyncClient]:
    """Exercise the route error envelope without a database connection."""

    async def _override_session() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[get_session] = _override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as api:
            yield api
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.asyncio
async def test_unknown_network_start_is_distinct_from_empty_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock(spec=AsyncSession)
    get_asset = AsyncMock(return_value=None)
    monkeypatch.setattr(assets_repo, "get_asset", get_asset)

    found = await assets_repo.traverse_network(session, "missing_asset", "upstream", 3)

    assert found is None
    get_asset.assert_awaited_once_with(session, "missing_asset")
    session.execute.assert_not_awaited()


@pytest.mark.parametrize("direction", ["upstream", "downstream"])
@pytest.mark.asyncio
async def test_unknown_asset_network_endpoint_returns_structured_404(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
) -> None:
    traverse = AsyncMock(return_value=None)
    monkeypatch.setattr(assets_router, "traverse_network", traverse)

    response = await client.get(f"/v1/assets/missing_asset/{direction}")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "ASSET_NOT_FOUND"
    assert error["details"] == {"asset_id": "missing_asset"}
    assert error["request_id"]
    traverse.assert_awaited_once_with(None, "missing_asset", direction, 3)
    assert (
        "404" in app.openapi()["paths"][f"/v1/assets/{{asset_id}}/{direction}"]["get"]["responses"]
    )


@pytest.mark.parametrize("direction", ["upstream", "downstream"])
@pytest.mark.asyncio
async def test_existing_asset_with_no_connections_returns_empty_list(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
    direction: str,
) -> None:
    traverse = AsyncMock(return_value=[])
    monkeypatch.setattr(assets_router, "traverse_network", traverse)

    response = await client.get(f"/v1/assets/isolated_node/{direction}")

    assert response.status_code == 200
    assert response.json() == []
    traverse.assert_awaited_once_with(None, "isolated_node", direction, 3)
