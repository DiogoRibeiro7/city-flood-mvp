"""Atomic GHCNh writes with explicit station mapping and revision conflicts."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.adapters.noaa_ghcnh import METRIC, SOURCE, GHCNhBatch, GHCNhError
from floodmvp.common.ids import new_id
from floodmvp.models.db import Asset, DatasetImport, TelemetryObservation


async def persist_batch(session: AsyncSession, batch: GHCNhBatch, city_id: str) -> dict[str, Any]:
    """Caller must own a transaction and roll it back on every exception.

    The metric encodes the fixed six-hour interval. Concurrent runs serialize
    on the asset; conflict checks also protect against other ingestion paths.
    Retrieval metadata may change on replay, but revised observations require
    an explicit operator decision instead of silent overwrites or skips.
    """
    await session.execute(text("SET LOCAL lock_timeout = '5s'"))
    await session.execute(text("SET LOCAL statement_timeout = '30s'"))
    asset = await session.scalar(
        select(Asset).where(Asset.asset_id == batch.request.asset_id).with_for_update()
    )
    if asset is None or asset.city_id != city_id:
        raise GHCNhError("asset does not exist in the requested city")
    if (
        asset.props.get("source") != SOURCE
        or asset.props.get("station_id") != batch.request.station_id
    ):
        raise GHCNhError(
            "asset props must explicitly map source and station_id to this NOAA station"
        )

    report = batch.report()
    import_id = new_id("import")
    report.update(import_id=import_id, city_id=city_id, asset_validation="verified", dry_run=False)
    audit = DatasetImport(
        import_id=import_id,
        city_id=city_id,
        source=SOURCE,
        source_uri=batch.sources[0]["url"] if len(batch.sources) == 1 else None,
        format="psv",
        dataset_version=batch.dataset_version,
        status="ingested",
        records_received=batch.stats.received,
        records_accepted=batch.stats.accepted,
        records_rejected=batch.stats.rejected,
        inserted_rows=0,
        validation_report=dict(report),
    )
    session.add(audit)
    await session.flush()
    inserted = 0
    for start in range(0, len(batch.records), 500):
        records = batch.records[start : start + 500]
        values = [
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
        statement = (
            insert(TelemetryObservation)
            .values(values)
            .on_conflict_do_nothing(index_elements=["asset_id", "metric", "ts"])
            .returning(TelemetryObservation.ts)
        )
        inserted += len((await session.execute(statement)).all())
        stored = (
            await session.scalars(
                select(TelemetryObservation)
                .where(
                    TelemetryObservation.asset_id == batch.request.asset_id,
                    TelemetryObservation.metric == METRIC,
                    TelemetryObservation.ts.in_([r.ts for r in records]),
                )
                .execution_options(populate_existing=True)
            )
        ).all()
        by_timestamp = {row.ts: row for row in stored}
        for record in records:
            row = by_timestamp.get(record.ts)
            if row is None or (
                row.value != record.value
                or row.source != SOURCE
                or row.source_id != record.source_id
                or row.quality_flag != record.quality_flag
                or row.lineage.get("observation_fingerprint")
                != record.lineage["observation_fingerprint"]
            ):
                raise GHCNhError(
                    f"stored observation differs at {record.ts.isoformat()}; entire import rolled back; review upstream revision or asset mapping"
                )
    report.update(status="ingested", inserted=inserted, existing=len(batch.records) - inserted)
    audit.inserted_rows = inserted
    audit.validation_report = dict(report)
    audit.completed_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return report
