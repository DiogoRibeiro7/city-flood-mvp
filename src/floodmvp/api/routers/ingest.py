from __future__ import annotations

import hashlib
import hmac
import math
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import BigInteger, delete, func, literal, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.api.openapi_examples import (
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
    if not settings.ingest_token:
        raise AppError(
            code="AUTH_NOT_CONFIGURED",
            message="Ingestion authentication is not configured",
            status_code=503,
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.removeprefix("Bearer ").strip()
    if not token or not hmac.compare_digest(token, settings.ingest_token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _validate_idempotency_key(key: str | None) -> str | None:
    """Normalise and validate the caller-provided key before database access."""
    if key is None:
        return None
    normalized = key.strip()
    if not normalized or len(normalized) > 128:
        raise AppError(
            code="INVALID_ARGUMENT",
            message="Idempotency-Key must contain between 1 and 128 characters",
        )
    return normalized


def _request_digest(payload: IngestRequest) -> str:
    """Fingerprint the validated request, including values and event timestamps."""
    return hashlib.sha256(payload.model_dump_json().encode("utf-8")).hexdigest()


def _replay_idempotent_response(
    device_id: str,
    stored: dict[str, Any],
    payload: IngestRequest,
    digest: str,
) -> IngestResponse:
    """Replay the original response only when the key represents the same request.

    Older records have no digest; their original replay behaviour is retained
    until the seven-day retention period expires.
    """
    stored_digest = stored.get("_request_digest")
    if device_id != payload.device_id or (stored_digest is not None and stored_digest != digest):
        raise AppError(
            code="IDEMPOTENCY_CONFLICT",
            message="Idempotency-Key was already used for a different request",
            status_code=409,
        )
    return IngestResponse(**stored)


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
        409: error_response(
            code="IDEMPOTENCY_CONFLICT",
            message="Idempotency-Key was already used for a different request",
        ),
    },
)
async def ingest_events_batch(
    payload: IngestRequest,
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> IngestResponse:
    _authorize(authorization)
    idempotency_key = _validate_idempotency_key(idempotency_key)

    await session.execute(
        delete(IngestIdempotency).where(
            IngestIdempotency.created_at < func.now() - text("interval '7 days'")
        )
    )

    if idempotency_key:
        digest = _request_digest(payload)
        # Lock by key for the transaction to serialize simultaneous retries.
        lock_id = int.from_bytes(
            hashlib.sha256(idempotency_key.encode("utf-8")).digest()[:8],
            byteorder="big",
            signed=True,
        )
        # Explicit BIGINT prevents asyncpg from binding a 64-bit hash as INTEGER.
        await session.execute(
            select(func.pg_advisory_xact_lock(literal(lock_id, type_=BigInteger())))
        )
        existing = await session.execute(
            select(IngestIdempotency).where(IngestIdempotency.idempotency_key == idempotency_key)
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            return _replay_idempotent_response(row.device_id, row.response, payload, digest)

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
            lineage = {"ingest": "api"}
            request_id = getattr(request.state, "request_id", None) if request else None
            if request_id:
                lineage["request_id"] = request_id
            insert_stmt = (
                insert(TelemetryObservation)
                .values(
                    asset_id=payload.device_id,
                    metric=event.type,
                    ts=event.ts,
                    value=float(event.value),
                    quality_flag=event.quality_flag or "ok",
                    source="ingest",
                    source_type="api",
                    source_id=payload.device_id,
                    lineage=lineage,
                )
                .on_conflict_do_nothing(index_elements=["asset_id", "metric", "ts"])
            )
            res = await session.execute(insert_stmt)
            rowcount = getattr(res, "rowcount", None)
            inserted = rowcount is None or rowcount > 0
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
                response={
                    **response.model_dump(mode="json"),
                    "_request_digest": _request_digest(payload),
                },
            )
        )

    await session.commit()
    return response
