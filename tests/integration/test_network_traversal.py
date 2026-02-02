from __future__ import annotations

import pytest
from geoalchemy2.elements import WKTElement
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.main import app
from floodmvp.models.db import Asset, City
from floodmvp.storage.db import get_session


@pytest.fixture()
async def app_client(db_session: AsyncSession) -> AsyncClient:
    async def _override_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upstream_downstream_traversal(app_client: AsyncClient, db_session: AsyncSession) -> None:
    city_id = "city_graph"
    db_session.add(City(city_id=city_id, name="Graph City", country="US"))
    db_session.add_all(
        [
            Asset(
                asset_id="n1",
                city_id=city_id,
                asset_type="node",
                name="Node 1",
                geom=WKTElement("POINT(-8.610 41.150)", srid=4326),
                props={},
            ),
            Asset(
                asset_id="n2",
                city_id=city_id,
                asset_type="node",
                name="Node 2",
                geom=WKTElement("POINT(-8.611 41.151)", srid=4326),
                props={},
            ),
            Asset(
                asset_id="n3",
                city_id=city_id,
                asset_type="node",
                name="Node 3",
                geom=WKTElement("POINT(-8.612 41.152)", srid=4326),
                props={},
            ),
            Asset(
                asset_id="p1",
                city_id=city_id,
                asset_type="pipe",
                name="Pipe 1",
                geom=WKTElement("LINESTRING(-8.610 41.150, -8.611 41.151)", srid=4326),
                props={"upstream_node_id": "n1", "downstream_node_id": "n2"},
            ),
            Asset(
                asset_id="p2",
                city_id=city_id,
                asset_type="pipe",
                name="Pipe 2",
                geom=WKTElement("LINESTRING(-8.611 41.151, -8.612 41.152)", srid=4326),
                props={"upstream_node_id": "n2", "downstream_node_id": "n3"},
            ),
        ]
    )
    await db_session.commit()

    res_up = await app_client.get("/v1/assets/n3/upstream?depth=2")
    assert res_up.status_code == 200
    upstream_ids = {a["asset_id"] for a in res_up.json()}
    assert upstream_ids == {"p2", "n2", "p1", "n1"}

    res_down = await app_client.get("/v1/assets/n1/downstream?depth=2")
    assert res_down.status_code == 200
    downstream_ids = {a["asset_id"] for a in res_down.json()}
    assert downstream_ids == {"p1", "n2", "p2", "n3"}
