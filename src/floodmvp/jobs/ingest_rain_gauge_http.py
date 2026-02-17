from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.adapters.external_ingest import IngestRecord, load_asset_map, validate_records
from floodmvp.adapters.rain_gauge_http import (
    RainGaugeFetchConfig,
    apply_unit_conversion,
    fetch_rain_gauge_rows,
    normalize_rain_gauge_rows,
)
from floodmvp.models.db import Asset, TelemetryObservation
from floodmvp.storage.db import SessionLocal


async def _fetch_asset_lookup(session: AsyncSession) -> tuple[set[str], dict[str, str]]:
    res = await session.execute(select(Asset.asset_id, Asset.city_id))
    asset_ids: set[str] = set()
    city_by_asset: dict[str, str] = {}
    for asset_id, city_id in res.all():
        asset_ids.add(asset_id)
        city_by_asset[asset_id] = city_id
    return asset_ids, city_by_asset


async def _insert_records(
    session: AsyncSession, records: list[IngestRecord], chunk_size: int = 2000
) -> int:
    inserted = 0
    rows = [
        {
            "asset_id": r.asset_id,
            "metric": r.metric,
            "ts": r.ts,
            "value": r.value,
            "quality_flag": r.quality_flag,
            "source": r.source,
        }
        for r in records
    ]
    for start in range(0, len(rows), chunk_size):
        batch = rows[start : start + chunk_size]
        stmt = insert(TelemetryObservation).values(batch)
        stmt = stmt.on_conflict_do_nothing(index_elements=["asset_id", "metric", "ts"])
        res = await session.execute(stmt)
        rowcount = int(getattr(res, "rowcount", 0) or 0)
        if rowcount:
            inserted += rowcount
    return inserted


async def run() -> int:
    parser = argparse.ArgumentParser(description="Ingest rain gauge telemetry from HTTP")
    parser.add_argument("--url", required=True)
    parser.add_argument("--format", choices=["json", "csv"], required=True)
    parser.add_argument("--device-field", required=True)
    parser.add_argument("--ts-field", required=True)
    parser.add_argument("--value-field", required=True)
    parser.add_argument("--metric", default="rain_mmph")
    parser.add_argument("--units", default="mmph", choices=["mmph", "mm", "in", "inph"])
    parser.add_argument("--interval-minutes", type=int)
    parser.add_argument("--city-id")
    parser.add_argument("--asset-map")
    parser.add_argument("--header", action="append", default=[])
    parser.add_argument("--source", default="external")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report")

    args = parser.parse_args()

    headers = None
    if args.header:
        headers = {}
        for h in args.header:
            if ":" not in h:
                raise ValueError("--header must be in 'Name: Value' format")
            name, value = h.split(":", 1)
            headers[name.strip()] = value.strip()

    config = RainGaugeFetchConfig(
        url=args.url,
        format=args.format,
        device_field=args.device_field,
        ts_field=args.ts_field,
        value_field=args.value_field,
        metric=args.metric,
        headers=headers,
    )

    rows = fetch_rain_gauge_rows(config)
    rows = normalize_rain_gauge_rows(rows, config, metric_override=args.metric)
    apply_unit_conversion(rows, args.units, args.interval_minutes)

    asset_map = load_asset_map(Path(args.asset_map)) if args.asset_map else {}

    async with SessionLocal() as session:
        allowed_asset_ids, city_by_asset = await _fetch_asset_lookup(session)
        records, stats = validate_records(
            rows,
            asset_map=asset_map,
            allowed_asset_ids=allowed_asset_ids,
            city_by_asset=city_by_asset,
            city_id=args.city_id,
            source=args.source,
        )

        inserted = 0
        if not args.dry_run and records:
            inserted = await _insert_records(session, records)
            await session.commit()

    report = {
        "received": stats.received,
        "accepted": stats.accepted,
        "rejected": stats.rejected,
        "reasons": stats.reasons,
        "inserted": inserted,
    }

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
