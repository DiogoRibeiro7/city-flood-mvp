from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.config.settings import settings
from floodmvp.models.db import TelemetryQaDaily
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


async def _qa_gaps(
    session: AsyncSession,
    city_id: str,
    start: dt.datetime,
    end: dt.datetime,
    granularity_minutes: int,
) -> None:
    granularity = f"{granularity_minutes} minutes"
    buckets_res = await session.execute(
        text(
            f"""
            WITH obs_filtered AS (
                SELECT obs.asset_id, obs.metric, obs.ts
                FROM telemetry_observation obs
                JOIN asset a ON a.asset_id = obs.asset_id
                WHERE a.city_id = :city_id
                  AND obs.ts >= :start
                  AND obs.ts < :end
                  AND obs.scenario_id IS NULL
            ),
            asset_spans AS (
                SELECT asset_id, metric, min(ts) AS min_ts, max(ts) AS max_ts
                FROM obs_filtered
                GROUP BY asset_id, metric
            ),
            buckets AS (
                SELECT
                    asset_id,
                    metric,
                    time_bucket('{granularity}'::interval, ts) AS bucket
                FROM obs_filtered
                GROUP BY asset_id, metric, bucket
            )
            SELECT
                s.metric,
                count(*) AS assets,
                sum(
                    greatest(
                        1,
                        floor(extract(epoch from (s.max_ts - s.min_ts)) / :gran_seconds)::int + 1
                    )
                ) AS buckets_expected,
                (SELECT count(*) FROM buckets b WHERE b.metric = s.metric) AS buckets_present
            FROM asset_spans s
            GROUP BY s.metric
            """
        ),
        {
            "city_id": city_id,
            "start": start,
            "end": end,
            "gran_seconds": granularity_minutes * 60,
        },
    )
    buckets_by_metric = {
        r[0]: (int(r[1]), int(r[2] or 0), int(r[3] or 0)) for r in buckets_res.all()
    }

    suspect_res = await session.execute(
        text(
            """
            SELECT obs.metric, count(*) AS suspect
            FROM telemetry_observation obs
            JOIN asset a ON a.asset_id = obs.asset_id
            WHERE a.city_id = :city_id
              AND obs.ts >= :start
              AND obs.ts < :end
              AND obs.quality_flag = 'suspect'
              AND obs.scenario_id IS NULL
            GROUP BY obs.metric
            """
        ),
        {"city_id": city_id, "start": start, "end": end},
    )
    suspect_by_metric = {r[0]: int(r[1]) for r in suspect_res.all()}

    day = start.date()

    await session.execute(
        delete(TelemetryQaDaily).where(
            TelemetryQaDaily.city_id == city_id, TelemetryQaDaily.day == day
        )
    )

    for metric, (assets, buckets_expected, buckets_present) in buckets_by_metric.items():
        gaps = max(0, buckets_expected - buckets_present)
        suspect_count = suspect_by_metric.get(metric, 0)
        session.add(
            TelemetryQaDaily(
                city_id=city_id,
                day=day,
                metric=metric,
                assets=assets,
                buckets_expected=buckets_expected,
                buckets_present=buckets_present,
                gaps=gaps,
                suspect_count=suspect_count,
            )
        )


async def main() -> None:
    city_id = "city_porto_mvp"
    now = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    start = now - dt.timedelta(days=settings.telemetry_gap_window_days)
    async with SessionLocal() as session:
        updated = await mark_suspect(session)
        await _qa_gaps(
            session,
            city_id=city_id,
            start=start,
            end=now,
            granularity_minutes=settings.telemetry_gap_granularity_minutes,
        )
        await session.commit()
    print(f"QA telemetry: marked {updated} rows as suspect")


if __name__ == "__main__":
    asyncio.run(main())
