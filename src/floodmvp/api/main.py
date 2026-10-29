from __future__ import annotations

import asyncio
import hmac
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.exceptions import HTTPException as StarletteHTTPException

from floodmvp.api.routers import (
    analytics,
    assets,
    cities,
    events,
    health,
    ingest,
    jobs,
    notes,
    telemetry,
)
from floodmvp.common.auth import extract_tenant, try_decode_token
from floodmvp.common.errors import AppError, as_error_payload, as_error_payload_raw
from floodmvp.common.logging import configure_logging, log_json
from floodmvp.config.settings import settings
from floodmvp.observability.metrics import (
    HTTP_ERRORS,
    REQUEST_COUNT,
    REQUEST_LATENCY,
    TENANT_HTTP_ERRORS,
    TENANT_REQUEST_COUNT,
    TENANT_REQUEST_LATENCY,
)

configure_logging()

app = FastAPI(title="City Flood MVP API", version="0.1.0")


class _TokenBucket:
    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.updated_at = time.monotonic()

    def allow(self) -> bool:
        now = time.monotonic()
        elapsed = now - self.updated_at
        self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
        self.updated_at = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


_RATE_LIMITS: OrderedDict[str, _TokenBucket] = OrderedDict()
_TENANT_LIMITS: OrderedDict[str, _TokenBucket] = OrderedDict()


def _get_bucket(
    cache: OrderedDict[str, _TokenBucket],
    key: str,
    *,
    rate: float,
    burst: int,
) -> _TokenBucket:
    """Reuse recently seen limits while bounding per-process memory usage.

    Evict the least-recently used bucket if the configured capacity is reached.
    A returning, evicted client starts with a fresh bucket.
    """
    bucket = cache.get(key)
    if bucket is not None:
        cache.move_to_end(key)
        return bucket

    while len(cache) >= settings.rate_limit_bucket_capacity:
        cache.popitem(last=False)

    bucket = _TokenBucket(rate, burst)
    cache[key] = bucket
    return bucket


# MVP: permissive CORS for local web app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _resolve_tenant_id(request: Request) -> str:
    """Derive metric/quota identity from verified credentials, never client labels."""
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        claims = try_decode_token(token)
        if claims:
            tenant = extract_tenant(claims)
            if tenant:
                return tenant
            return "authenticated"
    api_key = request.headers.get("x-api-key")
    if (
        not settings.jwt_secret
        and api_key
        and settings.analytics_api_key
        and hmac.compare_digest(api_key, settings.analytics_api_key)
    ):
        return "analytics-key"
    return "public"


def _finish_request(
    request: Request,
    response: Response,
    *,
    request_id: str,
    tenant_id: str,
    started_at: float,
) -> Response:
    """Record one response, including middleware-level rejections and timeouts."""
    duration = time.perf_counter() - started_at
    response.headers["x-request-id"] = request_id
    path = request.url.path
    # Raw URLs contain user-controlled IDs: keep Prometheus label cardinality bounded.
    # Requests rejected before routing have no matched route and use a fixed label.
    route_path = getattr(request.scope.get("route"), "path", None)
    metrics_path = route_path if isinstance(route_path, str) else "<unmatched>"
    method = request.method
    status_code = response.status_code
    REQUEST_COUNT.labels(method=method, path=metrics_path, status=str(status_code)).inc()
    REQUEST_LATENCY.labels(method=method, path=metrics_path).observe(duration)
    TENANT_REQUEST_COUNT.labels(
        tenant=tenant_id, method=method, path=metrics_path, status=str(status_code)
    ).inc()
    TENANT_REQUEST_LATENCY.labels(tenant=tenant_id, method=method, path=metrics_path).observe(
        duration
    )
    if status_code >= 400:
        status_class = "4xx" if status_code < 500 else "5xx"
        HTTP_ERRORS.labels(method=method, path=metrics_path, status_class=status_class).inc()
        TENANT_HTTP_ERRORS.labels(
            tenant=tenant_id, method=method, path=metrics_path, status_class=status_class
        ).inc()
    log_json(
        logging.INFO,
        "request",
        request_id=request_id,
        method=method,
        path=path,
        status=status_code,
        latency_ms=round(duration * 1000, 2),
        tenant_id=tenant_id,
    )
    return response


async def _body_exceeds_limit(request: Request, max_bytes: int) -> bool:
    """Read at most the configured body size, regardless of declared length.

    Content-Length is an early rejection hint, not proof of the actual body size.
    Cache accepted streamed bodies so Starlette can replay them to the endpoint.
    """
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            if int(declared_length) > max_bytes:
                return True
        except ValueError:
            # Malformed or unreliable declarations must still be checked on the wire.
            pass

    total = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        if len(chunk) > max_bytes - total:
            return True
        total += len(chunk)
        chunks.append(chunk)

    # Starlette's BaseHTTPMiddleware uses this cache to forward a body consumed
    # by an upstream middleware. Without it, downstream JSON parsing sees EOF.
    request._body = b"".join(chunks)
    return False


@app.middleware("http")
async def add_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started_at = time.perf_counter()
    deadline = asyncio.get_running_loop().time() + settings.request_timeout_s
    response: Response
    request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"
    request.state.request_id = request_id
    tenant_id = _resolve_tenant_id(request)
    request.state.tenant_id = tenant_id
    # rate limiting (in-memory MVP)
    client_id = request.client.host if request.client else "unknown"
    bucket = _get_bucket(
        _RATE_LIMITS,
        client_id,
        rate=settings.rate_limit_rps,
        burst=settings.rate_limit_burst,
    )
    if not bucket.allow():
        response = JSONResponse(
            status_code=429,
            content=as_error_payload_raw(
                code="RATE_LIMITED",
                message="Too many requests",
                details={},
                request_id=request_id,
            ),
        )
        return _finish_request(
            request, response, request_id=request_id, tenant_id=tenant_id, started_at=started_at
        )

    if settings.tenant_quota_rps > 0 and settings.tenant_quota_burst > 0:
        tenant_bucket = _get_bucket(
            _TENANT_LIMITS,
            tenant_id,
            rate=settings.tenant_quota_rps,
            burst=settings.tenant_quota_burst,
        )
        if not tenant_bucket.allow():
            response = JSONResponse(
                status_code=429,
                content=as_error_payload_raw(
                    code="TENANT_RATE_LIMITED",
                    message="Tenant request quota exceeded",
                    details={"tenant_id": tenant_id},
                    request_id=request_id,
                ),
            )
            return _finish_request(
                request, response, request_id=request_id, tenant_id=tenant_id, started_at=started_at
            )

    try:
        # A single deadline covers both streamed uploads and the downstream
        # handler. Resetting the timer after the upload permits slow clients to
        # hold connections open for longer than REQUEST_TIMEOUT_S.
        async with asyncio.timeout_at(deadline):
            if await _body_exceeds_limit(request, settings.request_max_bytes):
                response = JSONResponse(
                    status_code=413,
                    content=as_error_payload_raw(
                        code="REQUEST_TOO_LARGE",
                        message="Request body too large",
                        details={"max_bytes": settings.request_max_bytes},
                        request_id=request_id,
                    ),
                )
            else:
                response = await call_next(request)
    except TimeoutError:
        response = JSONResponse(
            status_code=504,
            content=as_error_payload_raw(
                code="REQUEST_TIMEOUT",
                message="Request timed out",
                details={"timeout_s": settings.request_timeout_s},
                request_id=request_id,
            ),
        )
    return _finish_request(
        request, response, request_id=request_id, tenant_id=tenant_id, started_at=started_at
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    return JSONResponse(status_code=exc.status_code, content=as_error_payload(exc, request_id))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    return JSONResponse(
        status_code=400,
        content=as_error_payload_raw(
            code="INVALID_ARGUMENT",
            message="Validation error",
            details={"errors": exc.errors()},
            request_id=request_id,
        ),
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    code_map = {
        400: "INVALID_ARGUMENT",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
    }
    code = code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed"
    return JSONResponse(
        status_code=exc.status_code,
        content=as_error_payload_raw(code=code, message=message, details={}, request_id=request_id),
        headers=exc.headers,
    )


@app.get("/metrics")
async def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(health.router, prefix="/v1")
app.include_router(cities.router, prefix="/v1")
app.include_router(assets.router, prefix="/v1")
app.include_router(telemetry.router, prefix="/v1")
app.include_router(ingest.router, prefix="/v1")
app.include_router(jobs.router, prefix="/v1")
app.include_router(analytics.router, prefix="/v1")
app.include_router(events.router, prefix="/v1")
app.include_router(notes.router, prefix="/v1")
