# City Flood MVP (synthetic data) -- REST + Web App

[![CI](https://github.com/DiogoRibeiro7/city-flood-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/DiogoRibeiro7/city-flood-mvp/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/DiogoRibeiro7/city-flood-mvp)](LICENSE)

End-to-end MVP for a **city-level flood monitoring** web app:

- River + rain + stormwater pipes/collectors network
- Synthetic assets + synthetic telemetry
- Analytics (events + hotspots + status) with confidence scores + versioned runs
- Public **read** REST API for the web app
- Protected ingestion endpoint (kept for future real data)
- Report builder (CSV export job) + async job queue
- Saved views + shareable links in the UI

## Stack

- Backend: FastAPI + SQLAlchemy (async) + Alembic + Poetry
- DB: TimescaleDB HA (Postgres) + PostGIS
- Web: Vite + React + Leaflet + Recharts (Yarn)
- Local: Docker Compose

## Quickstart (local)

1. Copy env:

  ```bash
  cp .env.example .env
  ```

2. Start services:

  ```bash
  docker compose up -d --build
  ```

3. Seed synthetic assets + telemetry + analytics (multi-city by default):

  ```bash
  ./scripts/seed_all.sh
  ```

4. Reset the full demo environment (optional):

  ```bash
  ./scripts/reset_demo.sh
  ```

5. Open:
   - API: <http://localhost:8000/docs>
   - Web: <http://localhost:5173>

## Useful endpoints

- `GET /v1/cities`
- `GET /v1/cities/{city_id}/assets?bbox=minLon,minLat,maxLon,maxLat&type=pipe|node|river_segment`
- `GET /v1/assets/{asset_id}`
- `GET /v1/assets/{asset_id}/observations?metric=fill_ratio&from=...&to=...&granularity=5m&agg=avg`
- `GET /v1/assets/{asset_id}/observations:compare?metric=...&from=...&to=...&base_scenario_id=...&compare_scenario_id=...`
- `GET /v1/cities/{city_id}/status`
- `GET /v1/hotspots?city_id=...&metric=overflow_risk&top=20`
- `GET /v1/events?city_id=...&type=overflow&from=...&to=...`
- `GET /v1/analytics/runs`
- `GET /v1/analytics/runs/diff`
- `GET /v1/analytics/calibration/recommendations`
- `POST /v1/analytics/calibration/overrides`
- `POST /v1/analytics/jobs` (export CSV + report CSV)
- `GET /v1/analytics/jobs/{job_id}`
- `GET /v1/analytics/jobs/{job_id}/download`

## Notes

- Everything is **source-agnostic**: assets and telemetry have a unified schema so real data can be plugged later.
- PostGIS is installed in the Timescale HA image, but still must be enabled per DB via `CREATE EXTENSION postgis`.
- To limit seeding to specific cities, set `CITY_IDS` (comma-separated) before running seed scripts.
- For external data ingestion (CSV/JSON/NDJSON), see `docs/runbooks/ingest_adapters.md`.
- For rain gauge HTTP ingestion, see `docs/runbooks/ingest_adapters.md#rain-gauge-http-adapter-real-data-source`.
- For river level HTTP ingestion, see `docs/runbooks/ingest_adapters.md#river-level-http-adapter-real-data-source`.
- For synthetic JSON generators (rain + river), see `docs/runbooks/ingest_adapters.md#synthetic-generators-json-output`.
- Background jobs (exports + analytics) are queued; run the worker with `poetry run python -m floodmvp.jobs.queue_worker`.
- Queue admin endpoints: `GET /v1/jobs/queue`, `POST /v1/jobs/queue/{job_id}/retry`, `POST /v1/jobs/queue/{job_id}/cancel` (guarded by JWT admin role when configured, or `X-API-Key` when set).
- Periodic analytics scheduler: `poetry run python -m floodmvp.jobs.scheduler --interval-minutes 60`.
- JWT auth (optional): set `JWT_SECRET` (and optionally `JWT_ISSUER`, `JWT_AUDIENCE`, `JWT_ROLES_CLAIM`) to enforce roles on report/export jobs and queue admin APIs.
