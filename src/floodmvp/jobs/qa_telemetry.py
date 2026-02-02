from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.storage.db import SessionLocal


METRIC_RULES = {
    "rain_mmph": {"delta": 80.0, "min": 0.0, "max": 250.0},
    "water_level_m": {"delta": 2.0, "min": 0.0, "max": 15.0},
    "fill_ratio": {"delta": 0.8, "min": 0.0, "max": 2.0},
    "flow_m3s": {"delta": 5.0, "min": 0.0, "max": 50.0},
    "water_depth_m": {"delta": 1.5, "min": 0.0, "max": 10.0},
}


async def mark_suspect(session: AsyncSession, lookback_days: int = 30) -> int:
    total = 0
    for metric, rules in METRIC_RULES.items():
        res = await session.execute(
            text(
                """
                WITH flagged AS (
                    SELECT asset_id, metric, ts
                    FROM (
                        SELECT
                            asset_id,
                            metric,
                            ts,
                            value,
                            LAG(value) OVER (PARTITION BY asset_id, metric ORDER BY ts) AS prev
                        FROM telemetry_observation
                        WHERE metric = :metric
                          AND ts >= :start
                    ) t
                    WHERE
                        (prev IS NOT NULL AND abs(value - prev) > :delta)
                        OR value < :min_value
                        OR value > :max_value
                )
                UPDATE telemetry_observation AS obs
                SET quality_flag = 'suspect'
                FROM flagged f
                WHERE obs.asset_id = f.asset_id
                  AND obs.metric = f.metric
                  AND obs.ts = f.ts
                  AND obs.quality_flag = 'ok'
                """
            ),
            {
                "metric": metric,
                "delta": rules["delta"],
                "min_value": rules["min"],
                "max_value": rules["max"],
                "start": dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=lookback_days),
            },
        )
        total += res.rowcount or 0
    return total


async def main() -> None:
    async with SessionLocal() as session:
        updated = await mark_suspect(session)
        await session.commit()
    print(f"QA telemetry: marked {updated} rows as suspect")


if __name__ == "__main__":
    asyncio.run(main())
