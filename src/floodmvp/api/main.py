from __future__ import annotations

import uuid
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from floodmvp.common.errors import AppError, as_error_payload
from floodmvp.common.logging import configure_logging

from floodmvp.api.routers import health, cities, assets, telemetry, analytics, events


configure_logging()

app = FastAPI(title="City Flood MVP API", version="0.1.0")

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
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    request_id = getattr(request.state, "request_id", "req_unknown")
    return JSONResponse(status_code=400, content=as_error_payload(exc, request_id))


app.include_router(health.router, prefix="/v1")
app.include_router(cities.router, prefix="/v1")
app.include_router(assets.router, prefix="/v1")
app.include_router(telemetry.router, prefix="/v1")
app.include_router(analytics.router, prefix="/v1")
app.include_router(events.router, prefix="/v1")
