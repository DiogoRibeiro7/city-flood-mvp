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
from floodmvp.common.time import parse_iso8601
from floodmvp.config.settings import settings
from floodmvp.models.db import ExportJob
from floodmvp.models.domain import (
    AnalyticsRunOut,
    AnalyticsRunDiffOut,
    AnalyticsEventDiffSummary,
    AnalyticsHotspotDiffSummary,
    CalibrationRecommendationOut,
    CalibrationOverrideIn,
    CalibrationOverrideOut,
    CalibrationThresholds,
    CityStatusOut,
    CitySummaryOut,
    ExportJobOut,
    ExportJobLogOut,
    ExportJobRequest,
    EventOut,
    HotspotOut,
    HotspotDiffItem,
)
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.analytics import (
    add_export_job_log,
    calibration_recommendations,
    create_export_job,
    create_threshold_override,
    get_city_status,
    get_city_summary,
    get_export_job,
    diff_analytics_runs,
    list_export_job_logs,
    list_hotspots,
    list_analytics_runs,
    list_threshold_overrides,
)
from floodmvp.storage.repos.jobs import enqueue_job

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


def _validate_season(season: str) -> None:
    if season == "all":
        return
    if not season.startswith("month-") or len(season) != 8:
        raise AppError(code="INVALID_ARGUMENT", message="season must be 'all' or 'month-01'..'month-12'")
    try:
        month = int(season.split("-", 1)[1])
    except ValueError as exc:
        raise AppError(code="INVALID_ARGUMENT", message="season must be 'all' or 'month-01'..'month-12'") from exc
    if month < 1 or month > 12:
        raise AppError(code="INVALID_ARGUMENT", message="season must be 'all' or 'month-01'..'month-12'")


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
    run_id: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[HotspotOut]:
    rows = await list_hotspots(session, city_id, metric, top, run_id=run_id)
    return [
        HotspotOut(
            asset_id=r.asset_id,
            score=float(r.score),
            confidence=float(r.confidence),
            details=r.details or {},
        )
        for r in rows
    ]


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


@router.get(
    "/analytics/calibration/recommendations",
    response_model=CalibrationRecommendationOut,
    responses={400: RESP_INVALID_ARGUMENT},
)
async def analytics_calibration_recommendations(
    city_id: str = Query(...),
    from_ts: str | None = Query(default=None, alias="from"),
    to_ts: str | None = Query(default=None, alias="to"),
    seasonality: str = Query("all", description="all | monthly"),
    session: AsyncSession = Depends(get_session),
) -> CalibrationRecommendationOut:
    if seasonality not in {"all", "monthly"}:
        raise AppError(code="INVALID_ARGUMENT", message="seasonality must be 'all' or 'monthly'")
    now = dt.datetime.now(dt.timezone.utc).replace(second=0, microsecond=0)
    if to_ts:
        end = parse_iso8601(to_ts)
    else:
        end = now
    if from_ts:
        start = parse_iso8601(from_ts)
    else:
        start = end - dt.timedelta(days=30)
    if end <= start:
        raise AppError(code="INVALID_ARGUMENT", message="'to' must be after 'from'")

    base = {
        "rain_event_threshold_mmph": settings.rain_event_threshold_mmph,
        "rain_event_min_duration_minutes": settings.rain_event_min_duration_minutes,
        "overflow_fill_threshold": settings.overflow_fill_threshold,
        "overflow_min_duration_minutes": settings.overflow_min_duration_minutes,
        "risk_fill_watch": settings.risk_fill_watch,
        "risk_fill_warning": settings.risk_fill_warning,
    }
    thresholds = await calibration_recommendations(
        session, city_id, start, end, seasonality, base
    )
    typed_thresholds = {k: CalibrationThresholds(**v) for k, v in thresholds.items()}
    return CalibrationRecommendationOut(
        city_id=city_id,
        from_ts=start,
        to_ts=end,
        seasonality=seasonality,
        thresholds=typed_thresholds,
    )


@router.get(
    "/analytics/calibration/overrides",
    response_model=list[CalibrationOverrideOut],
    responses={400: RESP_INVALID_ARGUMENT},
)
async def analytics_calibration_overrides(
    city_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> list[CalibrationOverrideOut]:
    rows = await list_threshold_overrides(session, city_id, limit=limit)
    return [
        CalibrationOverrideOut(
            override_id=r.override_id,
            city_id=r.city_id,
            season=r.season,
            thresholds=CalibrationThresholds(**(r.thresholds or {})),
            notes=r.notes,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post(
    "/analytics/calibration/overrides",
    response_model=CalibrationOverrideOut,
    responses={400: RESP_INVALID_ARGUMENT},
)
async def analytics_calibration_override_create(
    payload: CalibrationOverrideIn,
    session: AsyncSession = Depends(get_session),
) -> CalibrationOverrideOut:
    _validate_season(payload.season)
    row = await create_threshold_override(
        session,
        city_id=payload.city_id,
        season=payload.season,
        thresholds=payload.thresholds.model_dump(),
        notes=payload.notes,
    )
    await session.commit()
    return CalibrationOverrideOut(
        override_id=row.override_id,
        city_id=row.city_id,
        season=row.season,
        thresholds=CalibrationThresholds(**(row.thresholds or {})),
        notes=row.notes,
        created_at=row.created_at,
    )


@router.get(
    "/analytics/runs/diff",
    response_model=AnalyticsRunDiffOut,
    responses={400: RESP_INVALID_ARGUMENT},
)
async def analytics_runs_diff(
    city_id: str = Query(...),
    base_run_id: str = Query(...),
    compare_run_id: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    session: AsyncSession = Depends(get_session),
) -> AnalyticsRunDiffOut:
    try:
        diff = await diff_analytics_runs(session, base_run_id, compare_run_id, limit=limit)
    except ValueError as exc:
        raise AppError(code="INVALID_ARGUMENT", message=str(exc))
    if diff["city_id"] != city_id:
        raise AppError(code="INVALID_ARGUMENT", message="run_id does not match city_id")

    events = AnalyticsEventDiffSummary(
        base_count=diff["events"]["base_count"],
        compare_count=diff["events"]["compare_count"],
        added=[
            EventOut(
                event_id=e.event_id,
                event_type=e.event_type,
                severity=e.severity,
                confidence=float(e.confidence),
                start_ts=e.start_ts,
                end_ts=e.end_ts,
                asset_ids=list(e.asset_ids),
                summary=e.summary,
            )
            for e in diff["events"]["added"]
        ],
        removed=[
            EventOut(
                event_id=e.event_id,
                event_type=e.event_type,
                severity=e.severity,
                confidence=float(e.confidence),
                start_ts=e.start_ts,
                end_ts=e.end_ts,
                asset_ids=list(e.asset_ids),
                summary=e.summary,
            )
            for e in diff["events"]["removed"]
        ],
    )

    hotspots = AnalyticsHotspotDiffSummary(
        base_count=diff["hotspots"]["base_count"],
        compare_count=diff["hotspots"]["compare_count"],
        changed=[
            HotspotDiffItem(**row) for row in diff["hotspots"]["changed"]
        ],
        added=[
            HotspotDiffItem(**row) for row in diff["hotspots"]["added"]
        ],
        removed=[
            HotspotDiffItem(**row) for row in diff["hotspots"]["removed"]
        ],
    )

    return AnalyticsRunDiffOut(
        city_id=diff["city_id"],
        base_run_id=diff["base_run_id"],
        compare_run_id=diff["compare_run_id"],
        base_version=diff["base_version"],
        compare_version=diff["compare_version"],
        metrics_delta=diff["metrics_delta"],
        events=events,
        hotspots=hotspots,
    )


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
            status="queued",
            progress=0.0,
            query=payload.query.model_dump(by_alias=True),
        ),
    )
    await add_export_job_log(
        session,
        job_id=job_id,
        level="info",
        message="Export job queued",
        details={"type": payload.type},
    )
    await enqueue_job(session, job_type="export_csv", payload={"export_job_id": job_id})
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
