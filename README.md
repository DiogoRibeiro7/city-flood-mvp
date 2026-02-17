# City Flood MVP

[![CI](https://github.com/DiogoRibeiro7/city-flood-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/DiogoRibeiro7/city-flood-mvp/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/DiogoRibeiro7/city-flood-mvp)](LICENSE)
[![Release](https://img.shields.io/github/v/release/DiogoRibeiro7/city-flood-mvp)](https://github.com/DiogoRibeiro7/city-flood-mvp/releases)
[![Last Commit](https://img.shields.io/github/last-commit/DiogoRibeiro7/city-flood-mvp)](https://github.com/DiogoRibeiro7/city-flood-mvp/commits/develop)
[![Issues](https://img.shields.io/github/issues/DiogoRibeiro7/city-flood-mvp)](https://github.com/DiogoRibeiro7/city-flood-mvp/issues)
[![Stars](https://img.shields.io/github/stars/DiogoRibeiro7/city-flood-mvp)](https://github.com/DiogoRibeiro7/city-flood-mvp/stargazers)
[![Python](https://img.shields.io/badge/Python-3.12-blue)](https://www.python.org/downloads/release/python-3120/)
[![Node](https://img.shields.io/badge/Node-20-green)](https://nodejs.org/en/blog/release/v20.0.0)

City Flood MVP is an end-to-end, synthetic **city-scale flood monitoring** system that mirrors the workflow of a real municipal flood ops stack. It models multi-asset drainage networks (pipes, rivers, gauges), generates realistic telemetry, runs analytics to detect events and hotspots with confidence scores, and presents everything in a decision-ready web UI. The API is designed to remain source-agnostic so you can plug in real telemetry adapters later without changing the data model or analytics pipeline.

## What’s included

- Multi-city synthetic assets + telemetry + analytics
- Event and hotspot analytics with confidence scores
- Versioned analytics runs + run diff API
- Calibration recommendations + threshold overrides (per city/season)
- Scenario comparison API (`observations:compare`)
- Report builder (CSV export job) + async job queue
- UI with map, incident timeline, drill-downs, saved views, shareable links
- Optional JWT role enforcement for report/export jobs and queue admin APIs

## Stack

- Backend: FastAPI + SQLAlchemy (async) + Alembic + Poetry
- DB: TimescaleDB (Postgres) + PostGIS
- Web: Vite + React + Leaflet + Recharts (Yarn)
- Infra: Docker Compose

## Quickstart (local)

1. Copy env file

```bash
cp .env.example .env
```

2. Start services

```bash
docker compose up -d --build
```

3. Seed synthetic assets + telemetry + analytics

```bash
bash ./scripts/seed_all.sh
```

4. Open

- API docs: http://localhost:8000/docs
- Web UI: http://localhost:5173

## Auth (optional)

JWT role enforcement is disabled by default. To enable, set:

- `JWT_SECRET`
- `JWT_ISSUER` (optional)
- `JWT_AUDIENCE` (optional)
- `JWT_ROLES_CLAIM` (optional, default `roles`)

Roles used:

- `viewer`: read-only UI
- `analyst`: report/export jobs
- `admin`: calibration overrides + job queue admin APIs

## Key endpoints

- `GET /v1/cities`
- `GET /v1/cities/{city_id}/assets?bbox=minLon,minLat,maxLon,maxLat&type=pipe|node|river_segment`
- `GET /v1/assets/{asset_id}`
- `GET /v1/assets/{asset_id}/observations?metric=fill_ratio&from=...&to=...&granularity=5m&agg=avg`
- `GET /v1/assets/{asset_id}/observations:compare?metric=...&from=...&to=...&base_scenario_id=...&compare_scenario_id=...`
- `GET /v1/cities/{city_id}/status`
- `GET /v1/cities/{city_id}/summary?minutes=15`
- `GET /v1/hotspots?city_id=...&metric=overflow_risk&top=20`
- `GET /v1/events?city_id=...&type=overflow&from=...&to=...`
- `GET /v1/analytics/runs`
- `GET /v1/analytics/runs/diff`
- `GET /v1/analytics/calibration/recommendations`
- `POST /v1/analytics/calibration/overrides`
- `POST /v1/analytics/jobs` (export CSV + report CSV)
- `GET /v1/analytics/jobs/{job_id}`
- `GET /v1/analytics/jobs/{job_id}/download`
- `GET /v1/jobs/queue`
- `POST /v1/jobs/queue/{job_id}/retry`
- `POST /v1/jobs/queue/{job_id}/cancel`

## Ops notes

- PostGIS is installed in the Timescale image but must be enabled per DB (`CREATE EXTENSION postgis`).
- To limit seeding to specific cities, set `CITY_IDS` (comma-separated).
- Background jobs are queued; run the worker with:

```bash
poetry run python -m floodmvp.jobs.queue_worker
```

- Periodic analytics scheduler:

```bash
poetry run python -m floodmvp.jobs.scheduler --interval-minutes 60
```

## Data adapters

See `docs/runbooks/ingest_adapters.md` for external ingestion contracts and adapters.
