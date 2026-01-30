from __future__ import annotations

import asyncio
import datetime as dt

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.generators.telemetry import (
    generate_pipe_fill_ratio_series,
    generate_rain_series,
    generate_river_level_series,
)
from floodmvp.models.db import Asset, TelemetryObservation
from floodmvp.storage.db import SessionLocal


async def main() -> None:
    city_id = "city_porto_mvp"
    end = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    start = end - dt.timedelta(days=7)

    async with SessionLocal() as session:
        # pick one rain gauge and one river gauge
        rain_gauge = (await session.execute(
            select(Asset).where(Asset.city_id == city_id).where(Asset.asset_type == "rain_gauge").limit(1)
        )).scalar_one()
        river_gauge = (await session.execute(
            select(Asset).where(Asset.city_id == city_id).where(Asset.asset_type == "river_gauge").limit(1)
        )).scalar_one()

        rain = generate_rain_series(rain_gauge.asset_id, start, end, scenario="heavy_rain_high_river")
        river = generate_river_level_series(river_gauge.asset_id, rain, scenario="heavy_rain_high_river")

        # upsert gauge telemetry
        await _upsert_series(session, rain)
        await _upsert_series(session, river)

        # subset of pipes for telemetry to keep DB smaller (UI still good)
        pipes = (await session.execute(
            select(Asset).where(Asset.city_id == city_id).where(Asset.asset_type == "pipe").limit(250)
        )).scalars().all()

        rng = np.random.default_rng(42)
        for p in pipes:
            sens = float(rng.uniform(0.6, 1.6))
            fill = generate_pipe_fill_ratio_series(p.asset_id, rain, river, sensitivity=sens, seed=int(rng.integers(1, 10_000)))
            await _upsert_series(session, fill)

        await session.commit()

    print(f"Seeded telemetry for city_id={city_id} ({start.isoformat()} -> {end.isoformat()})")


async def _upsert_series(session: AsyncSession, series) -> None:
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
        }
        for ts, val in zip(series.df["ts"].tolist(), series.df["value"].tolist())
    ]
    if not rows:
        return
    # Use SQLAlchemy core for ON CONFLICT
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(TelemetryObservation).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["asset_id", "metric", "ts"])
    await session.execute(stmt)


if __name__ == "__main__":
    asyncio.run(main())
