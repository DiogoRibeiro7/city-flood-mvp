from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from floodmvp.common.ids import new_id
from floodmvp.models.db import Asset, DatasetImport, TelemetryObservation
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
    session: AsyncSession, records: list[IngestRecord], import_id: str | None, chunk_size: int = 2000
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
            "source_type": r.source_type,
            "source_id": r.source_id,
            "lineage": r.lineage,
            "import_id": import_id,
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
    parser.add_argument("--source-type", default="http")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report")
    parser.add_argument("--dataset-version")
    parser.add_argument("--import-id")

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
    raw_payload = json.dumps(rows, sort_keys=True).encode("utf-8")

    dataset_version = args.dataset_version
    if not dataset_version:
        dataset_version = hashlib.sha256(raw_payload).hexdigest()
    import_id = args.import_id or new_id("import")

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
            source_type=args.source_type,
            lineage_base={
                "dataset_version": dataset_version,
                "import_id": import_id,
                "source_uri": args.url,
                "format": args.format,
            },
        )

        report = {
            "import_id": import_id,
            "dataset_version": dataset_version,
            "received": stats.received,
            "accepted": stats.accepted,
            "rejected": stats.rejected,
            "reasons": stats.reasons,
            "inserted": 0,
        }

        import_row = DatasetImport(
            import_id=import_id,
            city_id=args.city_id,
            source=args.source,
            source_uri=args.url,
            format=args.format,
            dataset_version=dataset_version,
            status="validated",
            records_received=stats.received,
            records_accepted=stats.accepted,
            records_rejected=stats.rejected,
            inserted_rows=0,
            validation_report=report,
        )
        session.add(import_row)

        inserted = 0
        if not args.dry_run and records:
            inserted = await _insert_records(session, records, import_id=import_id)
            import_row.status = "ingested"
            import_row.inserted_rows = inserted
            report["inserted"] = inserted
            import_row.validation_report = report
        await session.commit()

    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
