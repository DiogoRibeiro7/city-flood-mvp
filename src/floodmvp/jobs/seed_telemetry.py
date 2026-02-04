from __future__ import annotations

import asyncio
import datetime as dt

import os

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.generators.scenarios import SCENARIOS
from floodmvp.generators.telemetry import (
    generate_pipe_hydraulics_series,
    generate_rain_series,
    generate_river_level_series,
)
from floodmvp.models.db import Asset, TelemetryObservation
from floodmvp.storage.db import SessionLocal


async def main(scenario_id: str | None = None) -> None:
    city_id = "city_porto_mvp"
    end = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    days = int(os.environ.get("TELEMETRY_DAYS", "7"))
    start = end - dt.timedelta(days=days)
    scenario = os.environ.get("TELEMETRY_SCENARIO", "heavy_rain_high_river")
    if scenario not in SCENARIOS:
        raise ValueError(f"TELEMETRY_SCENARIO must be one of {sorted(SCENARIOS)}")

    async with SessionLocal() as session:
        # pick one rain gauge and one river gauge
        rain_gauge = (await session.execute(
            select(Asset).where(Asset.city_id == city_id).where(Asset.asset_type == "rain_gauge").limit(1)
        )).scalar_one()
        river_gauge = (await session.execute(
            select(Asset).where(Asset.city_id == city_id).where(Asset.asset_type == "river_gauge").limit(1)
        )).scalar_one()

        rain = generate_rain_series(rain_gauge.asset_id, start, end, scenario=scenario)
        river = generate_river_level_series(river_gauge.asset_id, rain, scenario=scenario)

        # upsert gauge telemetry
        await _upsert_series(session, rain, scenario_id=scenario_id)
        await _upsert_series(session, river, scenario_id=scenario_id)

        # subset of pipes for telemetry to keep DB smaller (UI still good)
        pipe_limit = int(os.environ.get("PIPE_TELEMETRY_LIMIT", "150"))
        pipes = (await session.execute(
            select(Asset)
            .where(Asset.city_id == city_id)
            .where(Asset.asset_type == "pipe")
            .limit(pipe_limit)
        )).scalars().all()

        rng = np.random.default_rng(42)
        for p in pipes:
            sens = float(rng.uniform(0.6, 1.6))
            diameter_m = float((p.props or {}).get("diameter_m", 0.6))
            capacity_m3s = float((p.props or {}).get("capacity_est_m3s", 0.15))
            series_list = generate_pipe_hydraulics_series(
                p.asset_id,
                rain,
                river,
                diameter_m=diameter_m,
                capacity_est_m3s=capacity_m3s,
                sensitivity=sens,
                scenario=scenario,
                seed=int(rng.integers(1, 10_000)),
            )
            for series in series_list:
                await _upsert_series(session, series, scenario_id=scenario_id)

        await session.commit()

    print(f"Seeded telemetry for city_id={city_id} ({start.isoformat()} -> {end.isoformat()})")


async def _upsert_series(session: AsyncSession, series, scenario_id: str | None = None) -> None:
    # naive upsert: insert with ON CONFLICT DO NOTHING
    # (fast enough for MVP)
    rows = [
        {
            "asset_id": series.asset_id,
            "metric": series.metric,
            "ts": ts,
            "value": float(val),
            "quality_flag": "ok",
            "source": "synthetic",
            "scenario_id": scenario_id,
        }
        for ts, val in zip(series.df["ts"].tolist(), series.df["value"].tolist())
    ]
    if not rows:
        return
    # Use SQLAlchemy core for ON CONFLICT; chunk to avoid bind param limits.
    from sqlalchemy.dialects.postgresql import insert

    chunk_size = 2000
    for start in range(0, len(rows), chunk_size):
        batch = rows[start : start + chunk_size]
        stmt = insert(TelemetryObservation).values(batch)
        stmt = stmt.on_conflict_do_nothing(index_elements=["asset_id", "metric", "ts"])
        await session.execute(stmt)


if __name__ == "__main__":
    asyncio.run(main())
