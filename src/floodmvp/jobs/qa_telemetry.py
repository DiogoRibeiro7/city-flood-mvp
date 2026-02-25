from __future__ import annotations

import asyncio
import datetime as dt

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.config.cities import get_city_configs
from floodmvp.config.settings import settings
from floodmvp.models.db import TelemetryQaDaily
from floodmvp.storage.db import SessionLocal

METRIC_RULES = {
    "rain_mmph": {"delta": 80.0, "min": 0.0, "max": 250.0, "drift": 25.0},
    "water_level_m": {"delta": 2.0, "min": 0.0, "max": 15.0, "drift": 0.4},
    "fill_ratio": {"delta": 0.8, "min": 0.0, "max": 2.0, "drift": 0.25},
    "flow_m3s": {"delta": 5.0, "min": 0.0, "max": 50.0, "drift": 1.5},
    "water_depth_m": {"delta": 1.5, "min": 0.0, "max": 10.0, "drift": 0.3},
}

DRIFT_WINDOW_HOURS = 6


async def mark_outliers(
    session: AsyncSession, lookback_days: int
) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for metric, rules in METRIC_RULES.items():
        res = await session.execute(
            text(
                """
                WITH flagged AS (
                    SELECT obs.asset_id, obs.metric, obs.ts
                    FROM (
                        SELECT
                            obs.asset_id,
                            obs.metric,
                            obs.ts,
                            obs.value,
                            LAG(obs.value) OVER (PARTITION BY obs.asset_id, obs.metric ORDER BY obs.ts) AS prev
                        FROM telemetry_observation obs
                        WHERE obs.metric = :metric
                          AND obs.ts >= :start
                          AND obs.scenario_id IS NULL
                    ) t
                    WHERE
                        (prev IS NOT NULL AND abs(value - prev) > :delta)
                        OR value < :min_value
                        OR value > :max_value
                ),
                updated AS (
                    UPDATE telemetry_observation AS obs
                    SET quality_flag = 'suspect'
                    FROM flagged f
                    WHERE obs.asset_id = f.asset_id
                      AND obs.metric = f.metric
                      AND obs.ts = f.ts
                      AND obs.quality_flag = 'ok'
                    RETURNING obs.asset_id, obs.metric
                )
                SELECT a.city_id, u.metric, count(*) AS updated
                FROM updated u
                JOIN asset a ON a.asset_id = u.asset_id
                GROUP BY a.city_id, u.metric
                """
            ),
            {
                "metric": metric,
                "delta": rules["delta"],
                "min_value": rules["min"],
                "max_value": rules["max"],
                "start": dt.datetime.now(dt.UTC) - dt.timedelta(days=lookback_days),
            },
        )
        for city_id, metric_name, updated in res.all():
            key = (city_id, metric_name)
            counts[key] = counts.get(key, 0) + int(updated or 0)
    return counts


async def mark_drift(
    session: AsyncSession, window_hours: int
) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    now = dt.datetime.now(dt.UTC)
    mid = now - dt.timedelta(hours=window_hours)
    start = now - dt.timedelta(hours=window_hours * 2)
    for metric, rules in METRIC_RULES.items():
        drift = rules.get("drift")
        if drift is None:
            continue
        res = await session.execute(
            text(
                """
                WITH windowed AS (
                    SELECT
                        asset_id,
                        metric,
                        avg(value) FILTER (WHERE ts >= :mid AND ts < :now) AS avg_curr,
                        avg(value) FILTER (WHERE ts >= :start AND ts < :mid) AS avg_prev
                    FROM telemetry_observation
                    WHERE metric = :metric
                      AND ts >= :start
                      AND ts < :now
                      AND scenario_id IS NULL
                    GROUP BY asset_id, metric
                ),
                flagged AS (
                    SELECT asset_id, metric
                    FROM windowed
                    WHERE avg_prev IS NOT NULL
                      AND avg_curr IS NOT NULL
                      AND abs(avg_curr - avg_prev) > :drift
                ),
                updated AS (
                    UPDATE telemetry_observation AS obs
                    SET quality_flag = 'suspect'
                    FROM flagged f
                    WHERE obs.asset_id = f.asset_id
                      AND obs.metric = f.metric
                      AND obs.ts >= :mid
                      AND obs.ts < :now
                      AND obs.quality_flag = 'ok'
                    RETURNING obs.asset_id, obs.metric
                )
                SELECT a.city_id, u.metric, count(*) AS updated
                FROM updated u
                JOIN asset a ON a.asset_id = u.asset_id
                GROUP BY a.city_id, u.metric
                """
            ),
            {
                "metric": metric,
                "start": start,
                "mid": mid,
                "now": now,
                "drift": drift,
            },
        )
        for city_id, metric_name, updated in res.all():
            key = (city_id, metric_name)
            counts[key] = counts.get(key, 0) + int(updated or 0)
    return counts


async def mark_suspect(session: AsyncSession, lookback_days: int = 30) -> int:
    outlier_counts = await mark_outliers(session, lookback_days=lookback_days)
    drift_counts = await mark_drift(session, window_hours=DRIFT_WINDOW_HOURS)
    return sum(outlier_counts.values()) + sum(drift_counts.values())


async def _qa_gaps(
    session: AsyncSession,
    city_id: str,
    start: dt.datetime,
    end: dt.datetime,
    granularity_minutes: int,
    outlier_counts: dict[tuple[str, str], int],
    drift_counts: dict[tuple[str, str], int],
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
                outlier_count=outlier_counts.get((city_id, metric), 0),
                drift_count=drift_counts.get((city_id, metric), 0),
            )
        )


async def main() -> None:
    cities = get_city_configs()
    now = dt.datetime.now(dt.UTC).replace(second=0, microsecond=0)
    start = now - dt.timedelta(days=settings.telemetry_gap_window_days)
    async with SessionLocal() as session:
        outlier_counts = await mark_outliers(session, lookback_days=settings.telemetry_gap_window_days)
        drift_counts = await mark_drift(session, window_hours=DRIFT_WINDOW_HOURS)
        for city in cities:
            await _qa_gaps(
                session,
                city_id=city.city_id,
                start=start,
                end=now,
                granularity_minutes=settings.telemetry_gap_granularity_minutes,
                outlier_counts=outlier_counts,
                drift_counts=drift_counts,
            )
        await session.commit()
    outlier_total = sum(outlier_counts.values())
    drift_total = sum(drift_counts.values())
    print(f"QA telemetry: marked {outlier_total + drift_total} rows as suspect")


if __name__ == "__main__":
    asyncio.run(main())
