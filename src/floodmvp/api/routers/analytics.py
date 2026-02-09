from __future__ import annotations

import datetime as dt
import pathlib

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.openapi_examples import (
    RESP_FORBIDDEN_API_KEY,
    RESP_INVALID_ARGUMENT,
    RESP_UNAUTHORIZED_API_KEY,
)
from floodmvp.common.errors import AppError
from floodmvp.common.ids import new_id
from floodmvp.config.settings import settings
from floodmvp.models.db import ExportJob
from floodmvp.models.domain import (
    AnalyticsRunOut,
    CityStatusOut,
    CitySummaryOut,
    ExportJobOut,
    ExportJobLogOut,
    ExportJobRequest,
    HotspotOut,
)
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.analytics import (
    add_export_job_log,
    create_export_job,
    get_city_status,
    get_city_summary,
    get_export_job,
    list_export_job_logs,
    list_hotspots,
    list_analytics_runs,
    run_export_csv,
    update_export_job,
)

router = APIRouter(tags=["analytics"])


def _require_analytics_key(x_api_key: str | None) -> None:
    if not settings.analytics_api_key:
        return
    if not x_api_key:
        raise AppError(code="UNAUTHORIZED", message="Missing API key", status_code=401)
    if x_api_key != settings.analytics_api_key:
        raise AppError(code="FORBIDDEN", message="Invalid API key", status_code=403)


def _export_job_out(job: ExportJob, logs: list[ExportJobLogOut]) -> ExportJobOut:
    return ExportJobOut(
        job_id=job.job_id,
        job_type=job.job_type,
        status=job.status,
        progress=float(job.progress),
        file_path=job.file_path,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        row_count=job.row_count,
        created_at=job.created_at,
        updated_at=job.updated_at,
        logs=logs,
    )


@router.get(
    "/cities/{city_id}/status",
    response_model=CityStatusOut,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "city_id": "city_porto_mvp",
                        "risk": "low",
                        "active_events": 0,
                        "hotspots": 0,
                        "updated_at": "2026-02-02T12:23:13Z",
                        "request_id": "req_example",
                    }
                }
            }
        }
        ,
        400: RESP_INVALID_ARGUMENT,
    },
)
async def city_status(
    request: Request,
    city_id: str,
    session: AsyncSession = Depends(get_session),
) -> CityStatusOut:
    out = await get_city_status(session, city_id)
    out["request_id"] = getattr(request.state, "request_id", "req_unknown")
    return CityStatusOut(**out)


@router.get(
    "/cities/{city_id}/summary",
    response_model=CitySummaryOut,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "city_id": "city_porto_mvp",
                        "now": "2026-02-02T12:00:00Z",
                        "rain_mmph": 3.2,
                        "river_level_m": 1.8,
                        "status_counts": {"normal": 120, "watch": 5, "warning": 1},
                    }
                }
            }
        }
        ,
        400: RESP_INVALID_ARGUMENT,
    },
)
async def city_summary(
    city_id: str,
    minutes: int = Query(15, ge=1, le=1440),
    session: AsyncSession = Depends(get_session),
) -> CitySummaryOut:
    out = await get_city_summary(session, city_id, minutes)
    return CitySummaryOut(**out)


@router.get(
    "/hotspots",
    response_model=list[HotspotOut],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [{"asset_id": "pipe_123", "score": 42.5, "details": {}}]
                }
            }
        }
        ,
        400: RESP_INVALID_ARGUMENT,
    },
)
async def hotspots(
    city_id: str = Query(...),
    metric: str = Query("overflow_risk"),
    top: int = Query(20, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[HotspotOut]:
    rows = await list_hotspots(session, city_id, metric, top)
    return [HotspotOut(asset_id=r.asset_id, score=float(r.score), details=r.details or {}) for r in rows]


@router.get(
    "/analytics/runs",
    response_model=list[AnalyticsRunOut],
    responses={400: RESP_INVALID_ARGUMENT},
)
async def analytics_runs(
    city_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[AnalyticsRunOut]:
    rows = await list_analytics_runs(session, city_id=city_id, limit=limit)
    return [
        AnalyticsRunOut(
            run_id=r.run_id,
            city_id=r.city_id,
            start_ts=r.start_ts,
            end_ts=r.end_ts,
            status=r.status,
            version=r.version,
            params=r.params or {},
            metrics=r.metrics or {},
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.post(
    "/analytics/jobs",
    response_model=ExportJobOut,
    responses={
        401: RESP_UNAUTHORIZED_API_KEY,
        403: RESP_FORBIDDEN_API_KEY,
        400: {
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "INVALID_ARGUMENT",
                            "message": "asset_ids must not be empty",
                            "details": {},
                            "request_id": "req_example",
                        }
                    }
                }
            }
        },
    },
)
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
    if not payload.query.asset_ids and not payload.query.city_id:
        raise AppError(code="INVALID_ARGUMENT", message="asset_ids or city_id must be provided")

    job_id = new_id("job")
    await create_export_job(
        session,
        job=ExportJob(
            job_id=job_id,
            job_type=payload.type,
            status="running",
            progress=0.0,
            query=payload.query.model_dump(by_alias=True),
            started_at=dt.datetime.now(dt.timezone.utc),
        ),
    )
    await add_export_job_log(
        session,
        job_id=job_id,
        level="info",
        message="Export job created",
        details={"type": payload.type},
    )

    try:
        await add_export_job_log(
            session,
            job_id=job_id,
            level="info",
            message="Export job started",
        )
        file_path, row_count = await run_export_csv(session, job_id, payload.query)
        await update_export_job(
            session,
            job_id,
            status="completed",
            progress=1.0,
            file_path=file_path,
            completed_at=dt.datetime.now(dt.timezone.utc),
            row_count=row_count,
        )
        await add_export_job_log(
            session,
            job_id=job_id,
            level="info",
            message="Export job completed",
            details={"file_path": file_path, "row_count": row_count},
        )
    except Exception as e:  # noqa: BLE001
        await update_export_job(
            session,
            job_id,
            status="failed",
            progress=1.0,
            error_message=str(e),
            completed_at=dt.datetime.now(dt.timezone.utc),
        )
        await add_export_job_log(
            session,
            job_id=job_id,
            level="error",
            message="Export job failed",
            details={"error": str(e)},
        )
        await session.commit()
        raise

    await session.commit()
    saved = await get_export_job(session, job_id)
    assert saved is not None
    log_rows = await list_export_job_logs(session, job_id)
    logs = [
        ExportJobLogOut(
            ts=r.created_at,
            level=r.level,
            message=r.message,
            details=r.details or {},
        )
        for r in log_rows
    ]
    return _export_job_out(saved, logs)


@router.get(
    "/analytics/jobs/{job_id}",
    response_model=ExportJobOut,
    responses={
        401: RESP_UNAUTHORIZED_API_KEY,
        403: RESP_FORBIDDEN_API_KEY,
        404: {
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "JOB_NOT_FOUND",
                            "message": "Job not found",
                            "details": {"job_id": "job_missing"},
                            "request_id": "req_example",
                        }
                    }
                }
            }
        },
    },
)
async def get_job(
    job_id: str,
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_session),
) -> ExportJobOut:
    _require_analytics_key(x_api_key)
    job = await get_export_job(session, job_id)
    if job is None:
        raise AppError(code="JOB_NOT_FOUND", message="Job not found", status_code=404)
    log_rows = await list_export_job_logs(session, job_id)
    logs = [
        ExportJobLogOut(
            ts=r.created_at,
            level=r.level,
            message=r.message,
            details=r.details or {},
        )
        for r in log_rows
    ]
    return _export_job_out(job, logs)


@router.get(
    "/analytics/jobs/{job_id}/download",
    responses={
        401: RESP_UNAUTHORIZED_API_KEY,
        403: RESP_FORBIDDEN_API_KEY,
        400: {
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "JOB_NOT_READY",
                            "message": "Job not completed",
                            "details": {},
                            "request_id": "req_example",
                        }
                    }
                }
            }
        },
        404: {
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "JOB_NOT_FOUND",
                            "message": "Job not found",
                            "details": {"job_id": "job_missing"},
                            "request_id": "req_example",
                        }
                    }
                }
            }
        },
    },
)
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
