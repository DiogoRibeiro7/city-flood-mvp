"""Transactional provider ingestion in the guarded disposable PostgreSQL DB."""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import replace
from pathlib import Path

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from floodmvp.adapters.noaa_ghcnh import METRIC, GHCNhError, GHCNhRequest, acquire
from floodmvp.models.db import Asset, City, DatasetImport, TelemetryObservation
from floodmvp.storage.repos.noaa_ghcnh import persist_batch

MANIFEST = Path(__file__).resolve().parents[1] / "fixtures/real_sources/noaa_ghcnh/provenance.json"


def batch():
    return acquire(
        GHCNhRequest(
            "POMU0068545",
            "porto_gauge",
            dt.datetime(2010, 1, 1, tzinfo=dt.UTC),
            dt.datetime(2010, 1, 12, tzinfo=dt.UTC),
        ),
        fixture_manifest=MANIFEST,
    )


async def seed(session: AsyncSession, *, mapped: bool = True) -> None:
    session.add(City(city_id="test_porto", name="Test-only Porto mapping", country="PT"))
    await session.flush()
    session.add(
        Asset(
            asset_id="porto_gauge",
            city_id="test_porto",
            asset_type="rain_gauge",
            name="Porto / Pedras Rubras",
            geom=WKTElement("POINT(-8.68 41.23)", srid=4326),
            props={"source": "noaa_ghcnh", "station_id": "POMU0068545"} if mapped else {},
        )
    )
    await session.commit()


async def test_rerun_preserves_rows_and_provenance(db_session: AsyncSession) -> None:
    await seed(db_session)
    original = batch()
    async with db_session.begin():
        first = await persist_batch(db_session, original, "test_porto")
    async with db_session.begin():
        second = await persist_batch(db_session, batch(), "test_porto")
    assert first["inserted"] == 2 and first["existing"] == 0
    assert second["inserted"] == 0 and second["existing"] == 2
    assert first["dataset_version"] == second["dataset_version"]
    stored = (
        await db_session.scalars(select(TelemetryObservation).order_by(TelemetryObservation.ts))
    ).all()
    assert len(stored) == 2
    assert {r.import_id for r in stored} == {first["import_id"]}
    assert {r.metric for r in stored} == {METRIC}
    assert {r.quality_flag for r in stored} == {"unverified"}
    assert {r.source_id for r in stored} == {"POMU0068545"}
    assert stored[0].lineage == original.records[0].lineage
    assert stored[0].ts == original.records[0].ts
    audit = await db_session.get(DatasetImport, second["import_id"])
    assert audit is not None and audit.validation_report == second
    assert audit.records_received == 6 and audit.records_rejected == 4
    assert audit.completed_at is not None


async def test_upstream_revision_rolls_back_new_rows_and_audit(db_session: AsyncSession) -> None:
    await seed(db_session)
    async with db_session.begin():
        await persist_batch(db_session, batch(), "test_porto")
    revised = batch()
    # Controlled mutations: a new row followed by a revised existing value.
    revised.records = [
        replace(revised.records[0], ts=dt.datetime(2010, 1, 5, tzinfo=dt.UTC)),
        replace(revised.records[1], value=999.0),
    ]
    with pytest.raises(GHCNhError, match="stored observation differs"):
        async with db_session.begin():
            await persist_batch(db_session, revised, "test_porto")
    assert await db_session.scalar(select(func.count()).select_from(TelemetryObservation)) == 2
    assert await db_session.scalar(select(func.count()).select_from(DatasetImport)) == 1
    row = await db_session.get(TelemetryObservation, ("porto_gauge", METRIC, revised.records[1].ts))
    assert row is not None and row.value == pytest.approx(2 / 6)


@pytest.mark.parametrize("city,mapped", [("wrong_city", True), ("test_porto", False)])
async def test_city_and_explicit_station_mapping_are_required(
    db_session: AsyncSession, city: str, mapped: bool
) -> None:
    await seed(db_session, mapped=mapped)
    with pytest.raises(GHCNhError):
        async with db_session.begin():
            await persist_batch(db_session, batch(), city)
    assert await db_session.scalar(select(func.count()).select_from(DatasetImport)) == 0
    assert await db_session.scalar(select(func.count()).select_from(TelemetryObservation)) == 0


async def test_changed_download_with_identical_observations_retains_original_lineage(
    db_session: AsyncSession,
) -> None:
    await seed(db_session)
    async with db_session.begin():
        first = await persist_batch(db_session, batch(), "test_porto")
    revised_file = batch()
    # Controlled example: an upstream change outside the requested window.
    revised_file.sources[0]["sha256"] = "a" * 64
    async with db_session.begin():
        replay = await persist_batch(db_session, revised_file, "test_porto")
    assert replay["inserted"] == 0 and replay["existing"] == 2
    assert replay["dataset_version"] != first["dataset_version"]
    row = await db_session.scalar(select(TelemetryObservation).limit(1))
    assert row is not None and row.lineage["chunk"]["sha256"] != "a" * 64


async def test_concurrent_reruns_insert_once(db_session: AsyncSession) -> None:
    await seed(db_session)
    maker = async_sessionmaker(db_session.bind, expire_on_commit=False)

    async def write():
        async with maker.begin() as session:
            return await persist_batch(session, batch(), "test_porto")

    results = await asyncio.gather(write(), write())
    assert sorted(r["inserted"] for r in results) == [0, 2]
    assert await db_session.scalar(select(func.count()).select_from(TelemetryObservation)) == 2
    assert await db_session.scalar(select(func.count()).select_from(DatasetImport)) == 2
