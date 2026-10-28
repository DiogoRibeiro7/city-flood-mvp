"""Guard the JSON serialization contract between the API and job worker."""

from __future__ import annotations

import datetime as dt
import json
from typing import Any, cast

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.routers import analytics
from floodmvp.config.settings import settings
from floodmvp.models.db import ExportJob
from floodmvp.models.domain import (
    ExportCsvRequest,
    ExportJobQuery,
    ReportCsvRequest,
    ReportJobQuery,
)

NOW = dt.datetime(2026, 2, 1, tzinfo=dt.UTC)


class _SessionStub:
    """Only the commit operation is needed by the mocked job endpoint."""

    async def commit(self) -> None:
        return None


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
