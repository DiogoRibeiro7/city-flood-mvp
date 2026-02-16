from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.adapters.external_ingest import (
    load_asset_map,
    parse_csv,
    parse_json,
    parse_ndjson,
    validate_records,
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


async def _insert_records(session: AsyncSession, records, chunk_size: int = 2000) -> int:
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
        if res.rowcount:
            inserted += int(res.rowcount)
    return inserted


async def run() -> int:
    parser = argparse.ArgumentParser(description="Ingest external telemetry from CSV/JSON/NDJSON")
    parser.add_argument("--format", choices=["csv", "json", "ndjson"], required=True)
    parser.add_argument("--path", help="Path to file, or '-' for stdin (ndjson only)")
    parser.add_argument("--city-id", help="Limit ingestion to a city_id")
    parser.add_argument("--asset-map", help="Asset map file (json/csv/tsv)")
    parser.add_argument("--source", default="external", help="source tag to store")
    parser.add_argument("--default-device-id", help="Fallback device_id for records missing it")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", help="Write JSON report to this path")

    args = parser.parse_args()

    if args.format != "ndjson" and not args.path:
        print("--path is required for csv/json", file=sys.stderr)
        return 2

    asset_map = load_asset_map(Path(args.asset_map)) if args.asset_map else {}

    if args.format == "csv":
        rows = parse_csv(Path(args.path), default_device_id=args.default_device_id)
    elif args.format == "json":
        rows = parse_json(Path(args.path))
    else:
        if args.path and args.path != "-":
            rows = parse_ndjson(Path(args.path).read_text(encoding="utf-8").splitlines())
        else:
            rows = parse_ndjson(sys.stdin)

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
