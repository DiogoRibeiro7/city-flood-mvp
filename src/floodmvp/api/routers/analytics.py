from __future__ import annotations

import pathlib

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.errors import AppError
from floodmvp.common.ids import new_id
from floodmvp.config.settings import settings
from floodmvp.models.db import ExportJob
from floodmvp.models.domain import CityStatusOut, CitySummaryOut, ExportJobOut, ExportJobRequest, HotspotOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.analytics import (
    create_export_job,
    get_city_status,
    get_city_summary,
    get_export_job,
    list_hotspots,
    run_export_csv,
    update_export_job,
)

router = APIRouter(tags=["analytics"])


def _require_analytics_key(x_api_key: str | None) -> None:
    if not settings.analytics_api_key:
        return
    if not x_api_key or x_api_key != settings.analytics_api_key:
        raise AppError(code="UNAUTHORIZED", message="Invalid API key", status_code=401)


@router.get("/cities/{city_id}/status", response_model=CityStatusOut)
async def city_status(
    request: Request,
    city_id: str,
    session: AsyncSession = Depends(get_session),
) -> CityStatusOut:
    out = await get_city_status(session, city_id)
    out["request_id"] = getattr(request.state, "request_id", "req_unknown")
    return CityStatusOut(**out)


@router.get("/cities/{city_id}/summary", response_model=CitySummaryOut)
async def city_summary(
    city_id: str,
    minutes: int = Query(15, ge=1, le=1440),
    session: AsyncSession = Depends(get_session),
) -> CitySummaryOut:
    out = await get_city_summary(session, city_id, minutes)
    return CitySummaryOut(**out)


@router.get("/hotspots", response_model=list[HotspotOut])
async def hotspots(
    city_id: str = Query(...),
    metric: str = Query("overflow_risk"),
    top: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[HotspotOut]:
    rows = await list_hotspots(session, city_id, metric, top)
    return [HotspotOut(asset_id=r.asset_id, score=float(r.score), details=r.details or {}) for r in rows]


@router.post("/analytics/jobs", response_model=ExportJobOut)
async def create_job(
    payload: ExportJobRequest,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> ExportJobOut:
    _require_analytics_key(x_api_key)
    if payload.query.from_ts >= payload.query.to_ts:
        raise AppError(code="INVALID_ARGUMENT", message="'to' must be after 'from'")
    if payload.query.agg not in {"avg", "min", "max"}:
        raise AppError(code="INVALID_ARGUMENT", message="agg must be one of ['avg','min','max']")
    if not payload.query.asset_ids:
        raise AppError(code="INVALID_ARGUMENT", message="asset_ids must not be empty")

    job_id = new_id("job")
    await create_export_job(
        session,
        job=ExportJob(
            job_id=job_id,
            job_type=payload.type,
            status="running",
            progress=0.0,
            query=payload.query.model_dump(by_alias=True),
        ),
    )

    try:
        file_path = await run_export_csv(session, job_id, payload.query)
        await update_export_job(session, job_id, status="completed", progress=1.0, file_path=file_path)
    except Exception as e:  # noqa: BLE001
        await update_export_job(session, job_id, status="failed", progress=1.0, error_message=str(e))
        await session.commit()
        raise

    await session.commit()
    saved = await get_export_job(session, job_id)
    assert saved is not None
    return ExportJobOut(
        job_id=saved.job_id,
        job_type=saved.job_type,
        status=saved.status,
        progress=float(saved.progress),
        file_path=saved.file_path,
        error_message=saved.error_message,
        created_at=saved.created_at,
        updated_at=saved.updated_at,
    )


@router.get("/analytics/jobs/{job_id}/download")
async def download_job(
    job_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    _require_analytics_key(x_api_key)
    job = await get_export_job(session, job_id)
    if job is None:
        raise AppError(code="JOB_NOT_FOUND", message="Job not found", status_code=404)
    if job.status != "completed" or not job.file_path:
        raise AppError(code="JOB_NOT_READY", message="Job not completed", status_code=400)
    filename = pathlib.Path(job.file_path).name
    return FileResponse(job.file_path, filename=filename)
