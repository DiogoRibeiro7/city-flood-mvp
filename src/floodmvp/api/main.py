from __future__ import annotations

import uuid
import asyncio
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from floodmvp.common.errors import AppError, as_error_payload, as_error_payload_raw
from floodmvp.common.logging import configure_logging, log_json
from floodmvp.config.settings import settings

from floodmvp.api.routers import health, cities, assets, telemetry, analytics, events, ingest


configure_logging()

app = FastAPI(title="City Flood MVP API", version="0.1.0")

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)
REQUEST_LATENCY = Histogram(
    "http_request_latency_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
)
HTTP_ERRORS = Counter(
    "http_requests_errors_total",
    "Total HTTP error responses",
    ["method", "path", "status_class"],
)


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


_RATE_LIMITS: dict[str, _TokenBucket] = {}

# MVP: permissive CORS for local web app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("x-request-id") or f"req_{uuid.uuid4().hex}"
    request.state.request_id = request_id
    # rate limiting (in-memory MVP)
    client_id = request.client.host if request.client else "unknown"
    bucket = _RATE_LIMITS.get(client_id)
    if bucket is None:
        bucket = _TokenBucket(settings.rate_limit_rps, settings.rate_limit_burst)
        _RATE_LIMITS[client_id] = bucket
    if not bucket.allow():
        return JSONResponse(
            status_code=429,
            content=as_error_payload_raw(
                code="RATE_LIMITED",
                message="Too many requests",
                details={},
                request_id=request_id,
            ),
            headers={"x-request-id": request_id},
        )

    # request size limit
    if request.headers.get("content-length"):
        try:
            size = int(request.headers["content-length"])
            if size > settings.request_max_bytes:
                return JSONResponse(
                    status_code=413,
                    content=as_error_payload_raw(
                        code="REQUEST_TOO_LARGE",
                        message="Request body too large",
                        details={"max_bytes": settings.request_max_bytes},
                        request_id=request_id,
                    ),
                    headers={"x-request-id": request_id},
                )
        except ValueError:
            pass
    else:
        body = await request.body()
        if len(body) > settings.request_max_bytes:
            return JSONResponse(
                status_code=413,
                content=as_error_payload_raw(
                    code="REQUEST_TOO_LARGE",
                    message="Request body too large",
                    details={"max_bytes": settings.request_max_bytes},
                    request_id=request_id,
                ),
                headers={"x-request-id": request_id},
            )

    start = time.perf_counter()
    try:
        response = await asyncio.wait_for(call_next(request), timeout=settings.request_timeout_s)
    except asyncio.TimeoutError:
        return JSONResponse(
            status_code=504,
            content=as_error_payload_raw(
                code="REQUEST_TIMEOUT",
                message="Request timed out",
                details={"timeout_s": settings.request_timeout_s},
                request_id=request_id,
            ),
            headers={"x-request-id": request_id},
        )
    duration = time.perf_counter() - start
    response.headers["x-request-id"] = request_id
    path = request.url.path
    method = request.method
    status_code = response.status_code
    REQUEST_COUNT.labels(method=method, path=path, status=str(status_code)).inc()
    REQUEST_LATENCY.labels(method=method, path=path).observe(duration)
    if status_code >= 400:
        status_class = "4xx" if status_code < 500 else "5xx"
        HTTP_ERRORS.labels(method=method, path=path, status_class=status_class).inc()
    log_json(
        logging.INFO,
        "request",
        request_id=request_id,
        method=method,
        path=path,
        status=status_code,
        latency_ms=round(duration * 1000, 2),
    )
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    request_id = getattr(request.state, "request_id", "req_unknown")
    return JSONResponse(status_code=exc.status_code, content=as_error_payload(exc, request_id))


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
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
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
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
    )


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


app.include_router(health.router, prefix="/v1")
app.include_router(cities.router, prefix="/v1")
app.include_router(assets.router, prefix="/v1")
app.include_router(telemetry.router, prefix="/v1")
app.include_router(ingest.router, prefix="/v1")
app.include_router(analytics.router, prefix="/v1")
app.include_router(events.router, prefix="/v1")
