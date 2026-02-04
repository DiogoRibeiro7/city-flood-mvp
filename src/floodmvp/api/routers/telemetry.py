from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.openapi_examples import RESP_INVALID_ARGUMENT, error_response
from floodmvp.common.errors import AppError
from floodmvp.common.time import parse_iso8601
from floodmvp.models.domain import ObservationsOut, ScenarioRunOut, TelemetryQaOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.telemetry import (
    get_observations,
    list_metrics,
    list_qa_daily,
    list_scenarios,
    resolve_scenario_id,
)

router = APIRouter(tags=["telemetry"])


@router.get(
    "/telemetry/scenarios",
    response_model=list[ScenarioRunOut],
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": [
                        {
                            "scenario_id": "scenario_123",
                            "name": "heavy_rain_high_river",
                            "start_ts": "2026-02-01T00:00:00Z",
                            "end_ts": "2026-02-02T00:00:00Z",
                        }
                    ]
                }
            }
        }
        ,
        400: RESP_INVALID_ARGUMENT,
    },
)
async def telemetry_scenarios(session: AsyncSession = Depends(get_session)) -> list[ScenarioRunOut]:
    rows = await list_scenarios(session)
    return [ScenarioRunOut(**r) for r in rows]


@router.get(
    "/telemetry/qa",
    response_model=list[TelemetryQaOut],
    responses={400: RESP_INVALID_ARGUMENT},
)
async def telemetry_qa(
    city_id: str = Query(...),
    day: str | None = Query(default=None, description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_session),
) -> list[TelemetryQaOut]:
    parsed_day = None
    if day:
        try:
            parsed_day = dt.date.fromisoformat(day)
        except ValueError as e:
            raise AppError(code="INVALID_ARGUMENT", message=str(e))
    rows = await list_qa_daily(session, city_id, parsed_day)
    return [
        TelemetryQaOut(
            city_id=r.city_id,
            day=r.day,
            metric=r.metric,
            assets=r.assets,
            buckets_expected=r.buckets_expected,
            buckets_present=r.buckets_present,
            gaps=r.gaps,
            suspect_count=r.suspect_count,
        )
        for r in rows
    ]


@router.get(
    "/assets/{asset_id}/metrics",
    response_model=list[str],
    responses={
        200: {"content": {"application/json": {"example": ["fill_ratio", "flow_m3s"]}}}
        ,
        404: error_response(code="SCENARIO_NOT_FOUND", message="Scenario not found"),
    },
)
async def metrics(
    asset_id: str,
    scenario_id: str | None = Query(default=None, description="scenario id or 'latest'"),
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    resolved = await resolve_scenario_id(session, scenario_id) if scenario_id else None
    if scenario_id and resolved is None:
        raise AppError(code="SCENARIO_NOT_FOUND", message="Scenario not found", status_code=404)
    return await list_metrics(session, asset_id, scenario_id=resolved)


@router.get(
    "/assets/{asset_id}/observations",
    response_model=ObservationsOut,
    responses={
        200: {
            "content": {
                "application/json": {
                    "example": {
                        "metric": "fill_ratio",
                        "series": [
                            {"ts": "2026-02-01T10:00:00Z", "value": 0.42},
                            {"ts": "2026-02-01T10:05:00Z", "value": 0.55},
                        ],
                        "request_id": "req_example",
                    }
                }
            }
        }
        ,
        400: error_response(
            code="INVALID_ARGUMENT", message="'to' must be after 'from'"
        ),
        404: error_response(code="SCENARIO_NOT_FOUND", message="Scenario not found"),
    },
)
async def observations(
    request: Request,
    asset_id: str,
    metric: str = Query(...),
    from_ts: str = Query(..., alias="from"),
    to_ts: str = Query(..., alias="to"),
    granularity: str = Query("5m", description="Timescale time_bucket interval, e.g. 1m,5m,1h"),
    agg: str = Query("avg", description="avg|min|max"),
    include_gaps: bool = Query(False, description="include empty buckets as null values"),
    scenario_id: str | None = Query(default=None, description="scenario id or 'latest'"),
    session: AsyncSession = Depends(get_session),
) -> ObservationsOut:
    start = parse_iso8601(from_ts)
    end = parse_iso8601(to_ts)
    if end <= start:
        raise AppError(code="INVALID_ARGUMENT", message="'to' must be after 'from'")

    resolved = await resolve_scenario_id(session, scenario_id) if scenario_id else None
    if scenario_id and resolved is None:
        raise AppError(code="SCENARIO_NOT_FOUND", message="Scenario not found", status_code=404)
    try:
        rows = await get_observations(
            session,
            asset_id,
            metric,
            start,
            end,
            granularity,
            agg,
            include_gaps=include_gaps,
            scenario_id=resolved,
        )
    except ValueError as e:
        raise AppError(code="INVALID_ARGUMENT", message=str(e))

    return ObservationsOut(
        metric=metric,
        series=[{"ts": t, "value": v} for t, v in rows],
        request_id=getattr(request.state, "request_id", "req_unknown"),
    )
