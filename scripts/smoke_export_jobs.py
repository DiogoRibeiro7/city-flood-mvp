"""Verify queued CSV jobs and failed-SQL recovery against a seeded database.

Run in the backend container after the database has been migrated and seeded.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
from typing import Any, cast

import httpx
from sqlalchemy import select

from floodmvp.common.ids import new_id
from floodmvp.jobs.queue_worker import run_worker
from floodmvp.models.db import Asset, ExportJob, JobQueue, TelemetryObservation
from floodmvp.storage.db import SessionLocal
from floodmvp.storage.repos.jobs import enqueue_job


def _json_object(response: httpx.Response, status: int = 200) -> dict[str, Any]:
    """Check the status and JSON object shape of an API response."""
    if response.status_code != status:
        raise AssertionError(
            f"Expected HTTP {status}, got {response.status_code}: {response.text}"
        )
    body: object = response.json()
    if not isinstance(body, dict):
        raise AssertionError("Expected a JSON object")
    return cast(dict[str, Any], body)


async def _seeded_observation() -> tuple[str, str, dt.datetime]:
    """Choose a real seeded observation so exports must contain data rows."""
    async with SessionLocal() as session:
        row = (
            await session.execute(
                select(Asset.city_id, TelemetryObservation.asset_id, TelemetryObservation.ts)
                .select_from(TelemetryObservation)
                .join(Asset, Asset.asset_id == TelemetryObservation.asset_id)
                .where(TelemetryObservation.metric == "rain_mmph")
                .where(TelemetryObservation.scenario_id.is_(None))
                .order_by(TelemetryObservation.ts.desc())
                .limit(1)
            )
        ).first()
    if row is None:
        raise AssertionError("Seeded database has no rain measurements to export")
    return row[0], row[1], row[2]


async def _process_and_test_sql_failure(query: dict[str, Any]) -> None:
    """Process valid jobs, then ensure a PostgreSQL error is recorded as failed."""
    await run_worker(poll_seconds=0, once=True)

    async with SessionLocal() as session:
        queued_jobs = (
            await session.execute(
                select(JobQueue).where(JobQueue.job_type.in_(["export_csv", "report_csv"]))
            )
        ).scalars().all()
    unfinished = [
        {
            "type": job.job_type,
            "status": job.status,
            "attempts": job.attempts,
            "error": job.last_error,
        }
        for job in queued_jobs
        if job.status != "completed"
    ]
    if unfinished:
        raise AssertionError(f"Worker did not finish the valid jobs: {unfinished}")

    bad_id = new_id("job")
    async with SessionLocal() as session:
        session.add(
            ExportJob(
                job_id=bad_id,
                job_type="export_csv",
                status="queued",
                progress=0.0,
                query={**query, "agg": "missing_aggregate_function"},
            )
        )
        queued_job = await enqueue_job(
            session,
            job_type="export_csv",
            payload={"export_job_id": bad_id},
            max_attempts=1,
        )
        await session.commit()

    # A SQL error aborts the savepoint, not the transaction tracking retries.
    await run_worker(poll_seconds=0, once=True)
    async with SessionLocal() as session:
        export = await session.get(ExportJob, bad_id)
        queue_row = await session.get(JobQueue, queued_job.job_id)
    if export is None or export.status != "failed":
        raise AssertionError("Failed SQL did not mark the export as failed")
    if queue_row is None or queue_row.status != "failed" or queue_row.attempts != 1:
        raise AssertionError("Failed SQL did not persist the queue failure and attempt")


async def _create(client: httpx.AsyncClient, job_type: str, query: dict[str, Any]) -> str:
    """Queue a job using the public API and assert its asynchronous status."""
    response = _json_object(
        await client.post("/v1/analytics/jobs", json={"type": job_type, "query": query})
    )
    if response["status"] != "queued" or response["file_path"] is not None:
        raise AssertionError(f"Job was not queued correctly: {response}")
    return str(response["job_id"])


async def _run_smoke_test() -> None:
    """Use one event loop for the API calls and asyncpg connection pool."""
    city_id, asset_id, ts = await _seeded_observation()
    start = ts - dt.timedelta(minutes=5)
    end = ts + dt.timedelta(minutes=5)
    query = {
        "asset_ids": [asset_id],
        "metric": "rain_mmph",
        "from": start.isoformat(),
        "to": end.isoformat(),
        "granularity": "5m",
        "agg": "avg",
    }
    report_query = {"city_id": city_id, "from": start.isoformat(), "to": end.isoformat()}

    api_key = os.environ.get("ANALYTICS_API_KEY", "")
    headers = {"X-API-Key": api_key} if api_key else {}
    async with httpx.AsyncClient(
        base_url=os.environ.get("API_BASE_URL", "http://localhost:8000"),
        headers=headers,
        timeout=20.0,
    ) as client:
        export_id = await _create(client, "export_csv", query)
        report_id = await _create(client, "report_csv", report_query)

        await _process_and_test_sql_failure(query)

        export = _json_object(await client.get(f"/v1/analytics/jobs/{export_id}"))
        report = _json_object(await client.get(f"/v1/analytics/jobs/{report_id}"))
        for result in (export, report):
            if result["status"] != "completed" or not result["file_path"]:
                raise AssertionError(f"Queued job did not finish: {result}")

        csv = await client.get(f"/v1/analytics/jobs/{export_id}/download")
        if csv.status_code != 200 or asset_id not in csv.text:
            raise AssertionError(f"CSV download missing seeded measurements: {csv.text}")
        report_csv = await client.get(f"/v1/analytics/jobs/{report_id}/download")
        if report_csv.status_code != 200 or f'meta,city_id,"{city_id}"' not in report_csv.text:
            raise AssertionError(f"Report download is incorrect: {report_csv.text}")

    print("Queued export/report jobs and PostgreSQL retry recovery smoke test passed.")


def main() -> None:
    """Run the database-backed smoke test with one async event loop."""
    asyncio.run(_run_smoke_test())


if __name__ == "__main__":
    main()
