from __future__ import annotations

import pytest
from geoalchemy2.elements import WKTElement
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.main import app
from floodmvp.models.db import Asset, City
from floodmvp.storage.db import get_session


@pytest.fixture()
async def app_client(db_session: AsyncSession) -> AsyncClient:
    async def _override_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upstream_downstream_traversal(app_client: AsyncClient, db_session: AsyncSession) -> None:
    city_id = "city_graph"
    db_session.add(City(city_id=city_id, name="Graph City", country="US"))
    await db_session.flush()
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


@pytest.mark.asyncio
async def test_pipe_endpoints_and_cross_city_links(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Traversal includes direct pipe endpoints without escaping the starting city."""
    city_a = "city_graph_scope_a"
    city_b = "city_graph_scope_b"
    db_session.add_all(
        [
            City(city_id=city_a, name="Graph A", country="PT"),
            City(city_id=city_b, name="Graph B", country="PT"),
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Asset(
                asset_id=asset_id,
                city_id=city_id,
                asset_type="node",
                name=asset_id,
                geom=WKTElement("POINT(-8.61 41.15)", srid=4326),
                props={},
            )
            for asset_id, city_id in [
                ("scope_n1", city_a),
                ("scope_n2", city_a),
                ("scope_other_node", city_b),
            ]
        ]
    )
    await db_session.flush()
    db_session.add_all(
        [
            Asset(
                asset_id="scope_pipe",
                city_id=city_a,
                asset_type="pipe",
                name="Pipe A",
                geom=WKTElement("LINESTRING(-8.61 41.15, -8.62 41.16)", srid=4326),
                props={"upstream_node_id": "scope_n1", "downstream_node_id": "scope_n2"},
            ),
            Asset(
                asset_id="scope_foreign_pipe",
                city_id=city_b,
                asset_type="pipe",
                name="Cross-city pipe",
                geom=WKTElement("LINESTRING(-8.61 41.15, -8.62 41.16)", srid=4326),
                props={
                    "upstream_node_id": "scope_other_node",
                    "downstream_node_id": "scope_n2",
                },
            ),
            Asset(
                asset_id="scope_bridge",
                city_id=city_a,
                asset_type="pipe",
                name="Pipe with foreign endpoint",
                geom=WKTElement("LINESTRING(-8.61 41.15, -8.62 41.16)", srid=4326),
                props={
                    "upstream_node_id": "scope_n2",
                    "downstream_node_id": "scope_other_node",
                },
            ),
        ]
    )
    await db_session.commit()

    up_from_pipe = await app_client.get("/v1/assets/scope_pipe/upstream?depth=1")
    assert up_from_pipe.status_code == 200
    assert {a["asset_id"] for a in up_from_pipe.json()} == {"scope_n1"}

    upstream = await app_client.get("/v1/assets/scope_n2/upstream?depth=1")
    assert upstream.status_code == 200
    assert {a["asset_id"] for a in upstream.json()} == {"scope_pipe", "scope_n1"}

    downstream = await app_client.get("/v1/assets/scope_n2/downstream?depth=1")
    assert downstream.status_code == 200
    # The same-city pipe may appear, but its other-city endpoint must not.
    assert {a["asset_id"] for a in downstream.json()} == {"scope_bridge"}


@pytest.mark.asyncio
async def test_branching_network_returns_stable_layers_without_cycle_duplicates(
    app_client: AsyncClient, db_session: AsyncSession
) -> None:
    """Batched traversal keeps depth order and emits shared nodes only once."""
    city_id = "city_graph_branching"
    db_session.add(City(city_id=city_id, name="Branching City", country="PT"))
    await db_session.flush()

    nodes = [
        Asset(
            asset_id=f"branch_n{index}",
            city_id=city_id,
            asset_type="node",
            name=f"Node {index}",
            geom=WKTElement("POINT(-8.61 41.15)", srid=4326),
            props={},
        )
        for index in range(4)
    ]
    links = [
        ("branch_pz", "branch_n0", "branch_n2"),
        ("branch_pa", "branch_n0", "branch_n1"),
        ("branch_pb", "branch_n1", "branch_n3"),
        ("branch_pc", "branch_n2", "branch_n3"),
        ("branch_pd", "branch_n3", "branch_n0"),
    ]
    pipes = [
        Asset(
            asset_id=pipe_id,
            city_id=city_id,
            asset_type="pipe",
            name=pipe_id,
            geom=WKTElement("LINESTRING(-8.61 41.15, -8.62 41.16)", srid=4326),
            props={"upstream_node_id": upstream, "downstream_node_id": downstream},
        )
        for pipe_id, upstream, downstream in links
    ]
    db_session.add_all([*nodes, *pipes])
    await db_session.commit()

    expected_ids = [
        "branch_pa", "branch_pz", "branch_n1", "branch_n2",
        "branch_pb", "branch_pc", "branch_n3", "branch_pd",
    ]
    for _ in range(2):
        response = await app_client.get("/v1/assets/branch_n0/downstream?depth=3")
        assert response.status_code == 200
        assert [row["asset_id"] for row in response.json()] == expected_ids
