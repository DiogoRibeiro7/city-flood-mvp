from __future__ import annotations

import datetime as dt

import pytest
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.jobs.qa_telemetry import mark_suspect
from floodmvp.models.db import Asset, City, TelemetryObservation


@pytest.mark.asyncio
async def test_qa_marks_suspect_spikes(db_session: AsyncSession) -> None:
    city_id = "city_qa"
    asset_id = "rain_qa"
    db_session.add(City(city_id=city_id, name="QA City", country="US"))
    db_session.add(
        Asset(
            asset_id=asset_id,
            city_id=city_id,
            asset_type="rain_gauge",
            name="Rain",
            geom=WKTElement("POINT(-8.610 41.150)", srid=4326),
            props={},
        )
    )
    start = dt.datetime(2026, 1, 1, 0, 0, tzinfo=dt.UTC)
    db_session.add_all(
        [
            TelemetryObservation(
                asset_id=asset_id,
                metric="rain_mmph",
                ts=start,
                value=5.0,
                quality_flag="ok",
                source="synthetic",
            ),
            TelemetryObservation(
                asset_id=asset_id,
                metric="rain_mmph",
                ts=start + dt.timedelta(minutes=5),
                value=200.0,
                quality_flag="ok",
                source="synthetic",
            ),
        ]
    )
    await db_session.commit()

    updated = await mark_suspect(db_session, lookback_days=365)
    await db_session.commit()
    assert updated >= 1

    row = await db_session.scalar(
        select(TelemetryObservation).where(
            TelemetryObservation.asset_id == asset_id,
            TelemetryObservation.metric == "rain_mmph",
            TelemetryObservation.ts == start + dt.timedelta(minutes=5),
        )
    )
    assert row is not None
    assert row.quality_flag == "suspect"
