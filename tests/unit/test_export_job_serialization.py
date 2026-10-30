"""Guard the JSON serialization contract between the API and job worker."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.routers import analytics
from floodmvp.common.errors import AppError
from floodmvp.common.time import parse_bucket_interval
from floodmvp.config.settings import settings
from floodmvp.models.db import ExportJob
from floodmvp.models.domain import (
    ExportCsvRequest,
    ExportJobQuery,
    ReportCsvRequest,
    ReportJobQuery,
)

NOW = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("5m", dt.timedelta(minutes=5)),
        ("5 minutes", dt.timedelta(minutes=5)),
        ("1h", dt.timedelta(hours=1)),
        ("1d", dt.timedelta(days=1)),
    ],
)
def test_bucket_interval_parses_supported_units(value: str, expected: dt.timedelta) -> None:
    assert parse_bucket_interval(value) == expected


@pytest.mark.parametrize("value", ["", "0m", "5 months", "1h; DROP TABLE telemetry", "31d"])
def test_bucket_interval_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        parse_bucket_interval(value)


class _SessionStub:
    """Only the commit operation is needed by the mocked job endpoint."""

    async def commit(self) -> None:
        return None


@pytest.mark.asyncio
async def test_create_job_rejects_invalid_granularity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)
    payload = ExportCsvRequest(
        type="export_csv",
        query=ExportJobQuery(
            asset_ids=["pipe_1"],
            metric="fill_ratio",
            granularity="bad-interval",
            **{"from": NOW, "to": NOW + dt.timedelta(days=1)},
        ),
    )

    with pytest.raises(AppError) as exc_info:
        await analytics.create_job(payload, None, None, cast(AsyncSession, _SessionStub()))

    assert exc_info.value.status_code == 400
    assert exc_info.value.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_download_completed_job_with_missing_csv_returns_not_found(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing artifact is distinct from an unknown or unfinished export job."""
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)
    job = ExportJob(
        job_id="job_missing_csv",
        job_type="export_csv",
        status="completed",
        progress=1.0,
        query={},
        file_path=str(tmp_path / "deleted.csv"),
    )

    async def fake_get_export_job(session: AsyncSession, job_id: str) -> ExportJob | None:
        assert job_id == job.job_id
        return job

    monkeypatch.setattr(analytics, "get_export_job", fake_get_export_job)

    with pytest.raises(AppError) as exc_info:
        await analytics.download_job(job.job_id, None, None, cast(AsyncSession, _SessionStub()))

    assert exc_info.value.status_code == 404
    assert exc_info.value.code == "JOB_FILE_NOT_FOUND"
    assert exc_info.value.details == {"job_id": job.job_id}


@pytest.mark.asyncio
@pytest.mark.parametrize("job_type", ["export_csv", "report_csv"])
async def test_job_creation_stores_json_serializable_query(
    monkeypatch: pytest.MonkeyPatch, job_type: str
) -> None:
    """JSON persistence must preserve datetime values for the worker's model."""
    monkeypatch.setattr(settings, "jwt_secret", None)
    monkeypatch.setattr(settings, "analytics_api_key", None)

    saved: ExportJob | None = None

    async def fake_create_export_job(session: AsyncSession, job: ExportJob) -> None:
        nonlocal saved
        saved = job
        job.created_at = NOW
        job.updated_at = NOW

    async def fake_enqueue_job(session: AsyncSession, **kwargs: Any) -> None:
        return None

    async def fake_add_log(session: AsyncSession, **kwargs: Any) -> None:
        return None

    async def fake_get_export_job(session: AsyncSession, job_id: str) -> ExportJob | None:
        return saved

    async def fake_list_logs(session: AsyncSession, job_id: str) -> list[Any]:
        return []

    monkeypatch.setattr(analytics, "create_export_job", fake_create_export_job)
    monkeypatch.setattr(analytics, "enqueue_job", fake_enqueue_job)
    monkeypatch.setattr(analytics, "add_export_job_log", fake_add_log)
    monkeypatch.setattr(analytics, "get_export_job", fake_get_export_job)
    monkeypatch.setattr(analytics, "list_export_job_logs", fake_list_logs)

    if job_type == "export_csv":
        payload = ExportCsvRequest(
            type="export_csv",
            query=ExportJobQuery(
                asset_ids=["pipe_1"], metric="fill_ratio", **{"from": NOW, "to": NOW + dt.timedelta(days=1)}
            ),
        )
    else:
        payload = ReportCsvRequest(
            type="report_csv",
            query=ReportJobQuery(
                city_id="city_porto_mvp", **{"from": NOW, "to": NOW + dt.timedelta(days=1)}
            ),
        )

    response = await analytics.create_job(payload, None, None, cast(AsyncSession, _SessionStub()))

    assert response.status == "queued"
    assert saved is not None
    # SQLAlchemy's JSON serializer must accept the value without a custom encoder.
    json.dumps(saved.query)
    assert isinstance(saved.query["from"], str)
    assert isinstance(saved.query["to"], str)
    parsed = (ExportJobQuery if job_type == "export_csv" else ReportJobQuery).model_validate(
        saved.query
    )
    assert parsed.from_ts == NOW
    assert parsed.to_ts == NOW + dt.timedelta(days=1)
