"""Guarded in-container actions for the synthetic recovery drill; never application data."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from floodmvp.models.db import Base, City, ExportJob, JobQueue, TelemetryObservation
from floodmvp.observability.queue import collect_queue_snapshot
from floodmvp.storage.repos.jobs import enqueue_job, fetch_next_job
from scripts.database_test_support import validate_test_database_url
from scripts.seed_smoke import seed
from scripts.smoke_fixture import CITY_ID, END, RAIN_ID, START

EXPORT_ID = "recovery_export"
RETRY_ID = "recovery_retry"
STALE_ID = "recovery_stale_running"
PAUSE_MARKER = Path("/tmp/recovery-worker-entered.json")
TARGETS = {
    "source": ("db", "test_recovery_source"),
    "restored": ("restored-db", "test_recovery_restored"),
}


def require_recovery_database(database_url: str, app_env: str, project: str, target: str) -> None:
    """Require the exact runner-controlled target, not merely a database with a test suffix."""
    url = validate_test_database_url(database_url)
    if (
        target not in TARGETS
        or app_env != "test"
        or re.fullmatch(r"city-flood-recovery-[a-f0-9]{12}", project) is None
        or (url.host, url.database) != TARGETS[target]
        or url.port != 5432
        or url.username != "postgres"
        or url.drivername != "postgresql+asyncpg"
    ):
        raise ValueError("Recovery actions require the exact isolated Compose test target")


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def export_query(*, broken: bool = False) -> dict[str, Any]:
    return {
        "asset_ids": [RAIN_ID],
        "metric": "rain_mmph",
        "from": START.isoformat(),
        "to": END.isoformat(),
        "granularity": "1m",
        "agg": "missing_recovery_aggregate" if broken else "avg",
    }


async def prepare_export(session: AsyncSession, export_id: str, *, broken: bool = False) -> str:
    session.add(
        ExportJob(
            job_id=export_id,
            job_type="export_csv",
            status="queued",
            progress=0,
            query=export_query(broken=broken),
        )
    )
    queued = await enqueue_job(
        session,
        "export_csv",
        {"export_job_id": export_id},
        max_attempts=2,
        run_at=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10),
    )
    await session.commit()
    return queued.job_id


async def snapshot(session: AsyncSession) -> dict[str, Any]:
    """Canonical hashes of every mapped application table, migration/schema and extensions."""
    await session.execute(text("SET LOCAL timezone = 'UTC'"))
    tables: dict[str, Any] = {}
    for name in sorted([*Base.metadata.tables, "alembic_version"]):
        # Names come only from repository metadata, never a caller or database payload.
        if re.fullmatch(r"[a-z_]+", name) is None:
            raise ValueError("Unexpected repository table identifier")
        rows = (
            (
                await session.execute(
                    text(f'SELECT to_jsonb(t) FROM public."{name}" t ORDER BY to_jsonb(t)::text')
                )
            )
            .scalars()
            .all()
        )
        tables[name] = {"rows": len(rows), "sha256": digest(list(rows))}
    schema: dict[str, Any] = {}
    for key, sql in {
        "columns": "SELECT table_name,column_name,data_type,udt_name,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' AND table_name != 'spatial_ref_sys' ORDER BY table_name,ordinal_position",
        "constraints": "SELECT c.relname,p.conname,pg_get_constraintdef(p.oid) FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relname != 'spatial_ref_sys' ORDER BY 1,2",
        "indexes": "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' AND tablename != 'spatial_ref_sys' ORDER BY 1,2",
        "hypertables": "SELECT hypertable_schema,hypertable_name,num_dimensions FROM timescaledb_information.hypertables ORDER BY 1,2",
        "extensions": "SELECT extname,extversion FROM pg_extension ORDER BY extname",
    }.items():
        schema[key] = [list(row) for row in (await session.execute(text(sql))).all()]
    return {
        "tables": tables,
        "schema": schema,
        "sha256": digest({"tables": tables, "schema": schema}),
        "migration_head": await session.scalar(text("SELECT version_num FROM alembic_version")),
        "postgres_version": await session.scalar(text("SHOW server_version")),
    }


async def job_state(session: AsyncSession, export_id: str) -> dict[str, Any]:
    job = (
        await session.scalars(
            select(JobQueue).where(JobQueue.payload["export_job_id"].as_string() == export_id)
        )
    ).one()
    export = await session.get(ExportJob, export_id)
    assert export is not None
    # No waiting or lock stealing: release any acquired diagnostic lock on session exit.
    available = await session.scalar(
        select(JobQueue.job_id)
        .where(JobQueue.job_id == job.job_id)
        .with_for_update(skip_locked=True)
    )
    return {
        "job_id": job.job_id,
        "export_id": export_id,
        "status": job.status,
        "attempts": job.attempts,
        "scheduled_at": job.scheduled_at.isoformat(),
        "due": job.scheduled_at <= dt.datetime.now(dt.UTC),
        "lock_available": available is not None,
        "lock_metadata_cleared": job.locked_at is None and job.locked_by is None,
        "has_error": job.last_error is not None,
        "export_status": export.status,
        "row_count": export.row_count,
    }


async def backlog(session: AsyncSession) -> dict[str, Any]:
    await collect_queue_snapshot(session)
    from prometheus_client import REGISTRY

    if REGISTRY.get_sample_value("job_queue_collection_success") != 1:
        raise ValueError("Queue snapshot failed")
    return {
        "due_export_jobs": REGISTRY.get_sample_value(
            "job_queue_due_jobs", {"job_type": "export_csv"}
        ),
        "oldest_export_age_seconds": REGISTRY.get_sample_value(
            "job_queue_oldest_due_age_seconds", {"job_type": "export_csv"}
        ),
    }


async def action(name: str, sessions: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    if name == "seed":
        async with sessions() as session:
            seeded = await seed(session)
            queue_id = await prepare_export(session, EXPORT_ID)
        return {
            "seed": seeded,
            "queue_id": queue_id,
            "export_id": EXPORT_ID,
            "timestamp_fixture": "scheduled_at deliberately aged ten minutes",
        }
    if name == "checkpoint":
        async with sessions() as session:
            await session.execute(
                update(City)
                .where(City.city_id == CITY_ID)
                .values(name="Porto (synthetic recovery checkpoint)")
            )
            await session.commit()
        return {"protected_checkpoint_committed": True, "at": dt.datetime.now(dt.UTC).isoformat()}
    if name == "post-backup":
        now = dt.datetime.now(dt.UTC)
        async with sessions() as session:
            session.add(
                TelemetryObservation(
                    asset_id=RAIN_ID,
                    metric="rain_mmph",
                    ts=now,
                    value=42,
                    quality_flag="ok",
                    source="synthetic",
                    source_type="synthetic",
                    source_id=RAIN_ID,
                    lineage={"fixture": "recovery-post-backup-write"},
                )
            )
            await session.commit()
        return {"committed_observations_after_backup": 1, "timestamp": now.isoformat()}
    if name == "snapshot":
        async with sessions() as session:
            return await snapshot(session)
    if name == "require-empty":
        async with sessions() as session:
            count = await session.scalar(
                text(
                    "SELECT count(*) FROM pg_tables WHERE schemaname='public' AND tablename != 'spatial_ref_sys'"
                )
            )
            if count != 0:
                raise ValueError("Refusing restore into a nonempty application schema")
        return {"empty_application_schema": True}
    if name in {"job-state", "retry-state"}:
        async with sessions() as session:
            result = await job_state(session, EXPORT_ID if name == "job-state" else RETRY_ID)
        async with sessions() as session:
            result["backlog"] = await backlog(session)
        return result
    if name == "stale-running":
        old = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=10)
        async with sessions() as session:
            session.add(
                JobQueue(
                    job_id=STALE_ID,
                    job_type="export_csv",
                    status="running",
                    payload={},
                    attempts=1,
                    max_attempts=2,
                    scheduled_at=old,
                    locked_at=old,
                    locked_by="controlled-absent-worker",
                )
            )
            await session.commit()
            result = await backlog(session)
            status = await session.scalar(
                select(JobQueue.status).where(JobQueue.job_id == STALE_ID)
            )
            result.update(
                job_id=STALE_ID,
                status=status,
                fixture="deliberately aged committed running row",
                automatically_requeued=status != "running",
            )
        return result
    # Fault injection lives only in this guarded harness, never in the production worker.
    from floodmvp.jobs import queue_worker

    if name == "paused-worker":
        original = queue_worker._handle_export

        async def paused(session: AsyncSession, payload: dict[str, Any]) -> None:
            if not PAUSE_MARKER.exists():
                PAUSE_MARKER.write_text(
                    json.dumps(
                        {"export_id": payload["export_job_id"], "phase": "claimed_before_handler"}
                    ),
                    encoding="utf-8",
                )
                await asyncio.Event().wait()
            await original(session, payload)

        queue_worker._handle_export = paused
        await queue_worker.run_worker(0, True)
        return {"restarted_worker_drained_queue": True}
    if name == "retry-first":
        async with sessions() as session:
            await prepare_export(session, RETRY_ID, broken=True)
        await queue_worker.run_worker(0, True)
        async with sessions() as session:
            result = await job_state(session, RETRY_ID)
            if (
                result["status"] != "queued"
                or result["attempts"] != 1
                or not result["has_error"]
                or not result["lock_metadata_cleared"]
            ):
                raise ValueError("Failed SQL did not persist the expected retry state")
            if await fetch_next_job(session, "recovery-early-probe") is not None:
                raise ValueError("Retry became eligible before the immediate backoff check")
            # Repair only the controlled malformed query; preserve retry schedule and attempts.
            await session.execute(
                update(ExportJob).where(ExportJob.job_id == RETRY_ID).values(query=export_query())
            )
            await session.commit()
            result["early_claim_excluded"] = True
        return result
    raise ValueError("Unknown recovery action")


async def main(target: str, name: str) -> None:
    url = os.environ.get("DATABASE_URL", "")
    require_recovery_database(
        url, os.environ.get("APP_ENV", ""), os.environ.get("SMOKE_PROJECT", ""), target
    )
    allowed_source = {"seed", "checkpoint", "post-backup", "snapshot"}
    if (target == "source" and name not in allowed_source) or (
        target == "restored" and name in {"seed", "checkpoint", "post-backup"}
    ):
        raise ValueError("Action is not permitted for this recovery target")
    engine = create_async_engine(
        url, connect_args={"command_timeout": 30, "server_settings": {"timezone": "UTC"}}
    )
    try:
        result = await action(name, async_sessionmaker(engine, expire_on_commit=False))
        print(json.dumps(result, sort_keys=True, allow_nan=False), flush=True)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument(
        "action",
        choices=(
            "seed",
            "checkpoint",
            "post-backup",
            "snapshot",
            "require-empty",
            "job-state",
            "retry-state",
            "stale-running",
            "paused-worker",
            "retry-first",
        ),
    )
    args = parser.parse_args()
    asyncio.run(main(args.target, args.action))
