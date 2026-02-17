from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.config.cities import get_city_config
from floodmvp.config.settings import settings
from floodmvp.jobs.run_analytics import run_city_analytics
from floodmvp.models.domain import ExportJobQuery
from floodmvp.observability.metrics import JOB_PROCESSING_DURATION, JOB_QUEUE_AGE
from floodmvp.storage.db import SessionLocal
from floodmvp.storage.repos.analytics import (
    add_export_job_log,
    apply_threshold_overrides,
    get_export_job,
    run_export_csv,
    update_export_job,
)
from floodmvp.storage.repos.jobs import (
    build_worker_id,
    fetch_next_job,
    mark_job_failed,
    mark_job_success,
)


def _backoff_seconds(attempt: int) -> int:
    return int(min(300, 5 * (2 ** max(0, attempt - 1))))


async def _handle_export(session: AsyncSession, payload: dict[str, Any]) -> None:
    job_id = payload.get("export_job_id")
    if not isinstance(job_id, str) or not job_id:
        raise ValueError("export_job_id is required")

    job = await get_export_job(session, job_id)
    if job is None:
        raise ValueError(f"Export job {job_id} not found")

    await update_export_job(
        session,
        job_id,
        status="running",
        progress=0.0,
        started_at=dt.datetime.now(dt.UTC),
    )
    await add_export_job_log(session, job_id=job_id, level="info", message="Export job started")
    file_path, row_count = await run_export_csv(session, job_id, ExportJobQuery(**job.query))
    await update_export_job(
        session,
        job_id,
        status="completed",
        progress=1.0,
        file_path=file_path,
        completed_at=dt.datetime.now(dt.UTC),
        row_count=row_count,
    )
    await add_export_job_log(
        session,
        job_id=job_id,
        level="info",
        message="Export job completed",
        details={"file_path": file_path, "row_count": row_count},
    )


async def _handle_analytics(session: AsyncSession, payload: dict[str, Any]) -> None:
    city_id = payload.get("city_id")
    if not isinstance(city_id, str):
        raise ValueError("city_id is required")
    city = get_city_config(city_id)
    if city is None:
        raise ValueError(f"Unknown city_id {city_id}")

    now = dt.datetime.now(dt.UTC).replace(second=0, microsecond=0)
    start = now - dt.timedelta(days=settings.analytics_window_days)
    thresholds = {
        "rain_event_threshold_mmph": city.analytics.rain_event_threshold_mmph
        or settings.rain_event_threshold_mmph,
        "rain_event_min_duration_minutes": city.analytics.rain_event_min_duration_minutes
        or settings.rain_event_min_duration_minutes,
        "overflow_fill_threshold": city.analytics.overflow_fill_threshold
        or settings.overflow_fill_threshold,
        "overflow_min_duration_minutes": city.analytics.overflow_min_duration_minutes
        or settings.overflow_min_duration_minutes,
        "risk_fill_watch": city.analytics.risk_fill_watch or settings.risk_fill_watch,
        "risk_fill_warning": city.analytics.risk_fill_warning or settings.risk_fill_warning,
    }
    thresholds = await apply_threshold_overrides(session, city.city_id, thresholds, now)
    await run_city_analytics(session, city, now, start, thresholds)


async def run_worker(poll_seconds: float, once: bool) -> None:
    worker_id = build_worker_id()
    while True:
        async with SessionLocal() as session:
            job = await fetch_next_job(session, worker_id)
            if job is None:
                await session.commit()
                if once:
                    return
                await asyncio.sleep(poll_seconds)
                continue
            now = dt.datetime.now(dt.UTC)
            queue_age = (now - job.scheduled_at).total_seconds()
            JOB_QUEUE_AGE.labels(job_type=job.job_type).observe(max(0.0, queue_age))
            started = time.perf_counter()
            try:
                if job.job_type == "export_csv":
                    await _handle_export(session, job.payload)
                elif job.job_type == "analytics_run":
                    await _handle_analytics(session, job.payload)
                else:
                    raise ValueError(f"Unknown job_type {job.job_type}")
                await mark_job_success(session, job)
                await session.commit()
            except Exception as exc:  # noqa: BLE001
                backoff = _backoff_seconds(job.attempts)
                if job.job_type == "export_csv":
                    export_job_id = (job.payload or {}).get("export_job_id")
                    if export_job_id and job.attempts >= job.max_attempts:
                        await update_export_job(
                            session,
                            export_job_id,
                            status="failed",
                            progress=1.0,
                            error_message=str(exc),
                            completed_at=dt.datetime.now(dt.UTC),
                        )
                        await add_export_job_log(
                            session,
                            job_id=export_job_id,
                            level="error",
                            message="Export job failed",
                            details={"error": str(exc)},
                        )
                await mark_job_failed(session, job, str(exc), backoff)
                await session.commit()
            finally:
                duration = time.perf_counter() - started
                JOB_PROCESSING_DURATION.labels(job_type=job.job_type).observe(duration)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run job queue worker")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll", type=float, default=2.0)
    args = parser.parse_args()

    asyncio.run(run_worker(args.poll, args.once))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
