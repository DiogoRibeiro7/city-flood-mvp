"""Controlled cases verify metric meaning, not achieved operational service levels."""

import datetime as dt
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request
from prometheus_client import REGISTRY
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.routers import ingest
from floodmvp.jobs import queue_worker
from floodmvp.models.domain import IngestEventIn, IngestEventResult, IngestRequest, IngestResponse
from floodmvp.observability import metrics, queue

NOW = dt.datetime(2026, 11, 1, tzinfo=dt.UTC)


def sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0


def test_committed_ingest_separates_duplicates_invalid_and_timestamp_anomalies():
    results = [
        IngestEventResult(ts=NOW - dt.timedelta(seconds=300), type="a", status="accepted"),
        IngestEventResult(ts=NOW - dt.timedelta(days=3), type="a", status="accepted"),
        IngestEventResult(ts=NOW + dt.timedelta(seconds=1), type="private-id", status="accepted"),
        IngestEventResult(ts=NOW.replace(tzinfo=None), type="a", status="accepted"),
        IngestEventResult(ts=NOW, type="a", status="rejected", reason="duplicate"),
        IngestEventResult(ts=NOW, type="a", status="rejected", reason="arbitrary user detail"),
    ]
    before = {
        o: sample("ingest_events_total", outcome=o) for o in ("accepted", "duplicate", "invalid")
    }
    bucket = sample("ingest_event_delay_seconds_bucket", le="300.0")
    count = sample("ingest_event_delay_seconds_count")
    anomalies = {
        r: sample("ingest_timestamp_anomalies_total", reason=r) for r in ("future", "naive")
    }
    metrics.record_ingest_commit(
        IngestResponse(
            device_id="private-device", received=6, accepted=4, rejected=2, results=results
        ),
        NOW,
    )
    assert sample("ingest_events_total", outcome="accepted") - before["accepted"] == 4
    assert sample("ingest_events_total", outcome="duplicate") - before["duplicate"] == 1
    assert sample("ingest_events_total", outcome="invalid") - before["invalid"] == 1
    assert sample("ingest_event_delay_seconds_bucket", le="300.0") - bucket == 1
    assert sample("ingest_event_delay_seconds_count") - count == 2
    for reason in anomalies:
        assert sample("ingest_timestamp_anomalies_total", reason=reason) - anomalies[reason] == 1
    assert sample("ingest_last_commit_timestamp_seconds") == NOW.timestamp()


def test_retry_is_not_a_terminal_completion_and_unknown_types_are_bounded():
    duration = sample("job_completion_latency_seconds_count", job_type="other", outcome="failed")
    retried = sample("job_queue_retried_total", job_type="other")
    metrics.record_job_commit("unbounded-private-type", "queued", NOW, NOW)
    assert sample("job_queue_retried_total", job_type="other") == retried + 1
    assert (
        sample("job_completion_latency_seconds_count", job_type="other", outcome="failed")
        == duration
    )
    bucket = sample(
        "job_completion_latency_seconds_bucket", job_type="other", outcome="failed", le="900.0"
    )
    metrics.record_job_commit(
        "unbounded-private-type", "failed", NOW, NOW + dt.timedelta(seconds=700)
    )
    assert (
        sample(
            "job_completion_latency_seconds_bucket", job_type="other", outcome="failed", le="900.0"
        )
        == bucket + 1
    )
    assert metrics.tenant_label("tenant-private-123") == "authenticated"


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_fails", [False, True])
async def test_worker_records_outcome_only_after_commit(monkeypatch, commit_fails):
    session = AsyncMock(spec=AsyncSession)
    session.__aenter__.return_value = session
    nested = AsyncMock()
    session.begin_nested = Mock(return_value=nested)
    job = SimpleNamespace(
        job_type="analytics_run",
        payload={},
        attempts=1,
        max_attempts=3,
        scheduled_at=NOW,
        created_at=NOW,
        status="running",
    )
    monkeypatch.setattr(queue_worker, "SessionLocal", Mock(return_value=session))
    monkeypatch.setattr(queue_worker, "fetch_next_job", AsyncMock(side_effect=[job, None]))
    monkeypatch.setattr(queue_worker, "_handle_analytics", AsyncMock())

    async def success(_session, current):
        current.status = "completed"

    monkeypatch.setattr(queue_worker, "mark_job_success", success)
    observed = Mock()
    monkeypatch.setattr(queue_worker, "record_job_commit", observed)
    if commit_fails:
        session.commit.side_effect = RuntimeError("controlled commit failure")
        with pytest.raises(RuntimeError, match="commit failure"):
            await queue_worker.run_worker(0, True)
        observed.assert_not_called()
    else:
        await queue_worker.run_worker(0, True)
        assert observed.call_args.args[:3] == ("analytics_run", "completed", NOW)
        assert session.commit.await_count == 2


@pytest.mark.asyncio
async def test_failed_queue_collection_marks_cached_values_unusable():
    queue.QUEUE_DUE.labels(job_type="analytics_run").set(42)
    session = AsyncMock(spec=AsyncSession)
    session.execute.side_effect = RuntimeError("controlled database outage")
    await queue.collect_queue_snapshot(session)
    assert sample("job_queue_collection_success") == 0
    assert sample("job_queue_due_jobs", job_type="analytics_run") == 42


@pytest.mark.asyncio
async def test_empty_successful_queue_collection_resets_all_known_types():
    session = AsyncMock(spec=AsyncSession)
    result = Mock()
    result.all.return_value = []
    session.execute.return_value = result
    await queue.collect_queue_snapshot(session)
    assert sample("job_queue_collection_success") == 1
    for kind in metrics.JOB_TYPES:
        assert sample("job_queue_due_jobs", job_type=kind) == 0
        assert sample("job_queue_oldest_due_age_seconds", job_type=kind) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("commit_fails", [False, True])
async def test_ingest_publishes_results_only_after_commit(monkeypatch, commit_fails):
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = "asset-test"
    session.execute.return_value = SimpleNamespace(rowcount=1)
    observed = Mock()
    monkeypatch.setattr(ingest, "record_ingest_commit", observed)
    payload = IngestRequest(
        device_id="asset-test",
        sent_at=NOW,
        events=[IngestEventIn(ts=NOW, type="rain_mmph", value=1)],
    )
    request = Request({"type": "http", "headers": []})
    if commit_fails:
        session.commit.side_effect = RuntimeError("controlled commit failure")
        with pytest.raises(RuntimeError, match="commit failure"):
            await ingest.ingest_events_batch(
                payload, request, "Bearer dev-ingest-token", None, session
            )
        observed.assert_not_called()
    else:

        def record(response, now):
            assert session.commit.await_count == 1
            assert response.accepted == 1

        observed.side_effect = record
        await ingest.ingest_events_batch(payload, request, "Bearer dev-ingest-token", None, session)
        observed.assert_called_once()
