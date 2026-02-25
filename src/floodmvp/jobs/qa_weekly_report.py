from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path

from sqlalchemy import func, select

from floodmvp.config.settings import settings
from floodmvp.models.db import TelemetryQaDaily
from floodmvp.storage.db import SessionLocal


def _default_output_path(days: int) -> Path:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    return Path(settings.export_dir) / f"qa_weekly_{days}d_{stamp}.csv"


async def _fetch_summary(days: int) -> list[dict[str, object]]:
    end_day = dt.date.today()
    start_day = end_day - dt.timedelta(days=days)
    async with SessionLocal() as session:
        res = await session.execute(
            select(
                TelemetryQaDaily.city_id,
                TelemetryQaDaily.metric,
                func.sum(TelemetryQaDaily.assets).label("assets"),
                func.sum(TelemetryQaDaily.buckets_expected).label("expected"),
                func.sum(TelemetryQaDaily.buckets_present).label("present"),
                func.sum(TelemetryQaDaily.gaps).label("gaps"),
                func.sum(TelemetryQaDaily.suspect_count).label("suspect"),
                func.sum(TelemetryQaDaily.outlier_count).label("outliers"),
                func.sum(TelemetryQaDaily.drift_count).label("drift"),
            )
            .where(TelemetryQaDaily.day >= start_day, TelemetryQaDaily.day < end_day)
            .group_by(TelemetryQaDaily.city_id, TelemetryQaDaily.metric)
            .order_by(TelemetryQaDaily.city_id, TelemetryQaDaily.metric)
        )
        rows = []
        for row in res.all():
            expected = int(row.expected or 0)
            present = int(row.present or 0)
            coverage = round((present / expected) * 100, 2) if expected else 0.0
            rows.append(
                {
                    "city_id": row.city_id,
                    "metric": row.metric,
                    "assets": int(row.assets or 0),
                    "buckets_expected": expected,
                    "buckets_present": present,
                    "gaps": int(row.gaps or 0),
                    "suspect_count": int(row.suspect or 0),
                    "outlier_count": int(row.outliers or 0),
                    "drift_count": int(row.drift or 0),
                    "coverage_pct": coverage,
                }
            )
        return rows


async def main() -> None:
    parser = argparse.ArgumentParser(description="Weekly telemetry QA report")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()

    out_path = Path(args.out) if args.out else _default_output_path(args.days)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows = await _fetch_summary(args.days)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "city_id",
                "metric",
                "assets",
                "buckets_expected",
                "buckets_present",
                "gaps",
                "suspect_count",
                "outlier_count",
                "drift_count",
                "coverage_pct",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote QA weekly report to {out_path}")


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
