from __future__ import annotations

import math
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.openapi_examples import (
    RESP_FORBIDDEN_BEARER,
    RESP_UNAUTHORIZED_BEARER,
    error_response,
)
from floodmvp.common.errors import AppError
from floodmvp.config.settings import settings
from floodmvp.models.db import Asset, IngestIdempotency, TelemetryObservation
from floodmvp.models.domain import IngestEventResult, IngestRequest, IngestResponse
from floodmvp.storage.db import get_session

router = APIRouter(tags=["ingest"])


def _authorize(authorization: str | None) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if token != settings.ingest_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _is_finite_number(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


@router.post(
    "/telemetry/events:batch",
    response_model=IngestResponse,
    responses={
        401: RESP_UNAUTHORIZED_BEARER,
        403: RESP_FORBIDDEN_BEARER,
        400: {
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "INVALID_ARGUMENT",
                            "message": "type is required",
                            "details": {},
                            "request_id": "req_example",
                        }
                    }
                }
            }
        },
        404: error_response(
            code="ASSET_NOT_FOUND",
            message="Asset not found",
            details={"asset_id": "asset_missing"},
        ),
    },
)
async def ingest_events_batch(
    payload: IngestRequest,
    authorization: str | None = Header(default=None, alias="Authorization"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    _authorize(authorization)

    await session.execute(
        delete(IngestIdempotency).where(
            IngestIdempotency.created_at < func.now() - text("interval '7 days'")
        )
    )

    if idempotency_key:
        existing = await session.execute(
            select(IngestIdempotency).where(IngestIdempotency.idempotency_key == idempotency_key)
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            return IngestResponse(**row.response)

    asset_exists = await session.scalar(
        select(Asset.asset_id).where(Asset.asset_id == payload.device_id)
    )
    if asset_exists is None:
        raise AppError(
            code="ASSET_NOT_FOUND",
            message="Asset not found",
            details={"asset_id": payload.device_id},
            status_code=404,
        )

    results: list[IngestEventResult] = []
    accepted = 0
    rejected = 0

    for event in payload.events:
        reason = None
        if not event.type or not event.type.strip():
            reason = "type is required"
        elif not _is_finite_number(event.value):
            reason = "value must be a finite number"

        if reason is None:
            insert_stmt = (
                insert(TelemetryObservation)
                .values(
                    asset_id=payload.device_id,
                    metric=event.type,
                    ts=event.ts,
                    value=float(event.value),
                    quality_flag=event.quality_flag or "ok",
                    source="ingest",
                )
                .on_conflict_do_nothing(index_elements=["asset_id", "metric", "ts"])
            )
            res = await session.execute(insert_stmt)
            inserted = res.rowcount is None or res.rowcount > 0
            if inserted:
                accepted += 1
                results.append(
                    IngestEventResult(ts=event.ts, type=event.type, status="accepted")
                )
            else:
                rejected += 1
                results.append(
                    IngestEventResult(
                        ts=event.ts, type=event.type, status="rejected", reason="duplicate"
                    )
                )
        else:
            rejected += 1
            results.append(
                IngestEventResult(
                    ts=event.ts, type=event.type, status="rejected", reason=reason
                )
            )

    response = IngestResponse(
        device_id=payload.device_id,
        received=len(payload.events),
        accepted=accepted,
        rejected=rejected,
        results=results,
    )

    if idempotency_key:
        await session.execute(
            insert(IngestIdempotency)
            .values(
                idempotency_key=idempotency_key,
                device_id=payload.device_id,
                response=response.model_dump(mode="json"),
            )
            .on_conflict_do_nothing(index_elements=["idempotency_key"])
        )

    await session.commit()
    return response
