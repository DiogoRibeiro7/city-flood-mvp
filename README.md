# City Flood MVP (synthetic data) -- REST + Web App

End-to-end MVP for a **city-level flood monitoring** web app:

- River + rain + stormwater pipes/collectors network
- Synthetic assets + synthetic telemetry
- Basic analytics (events + hotspots + status)
- Public **read** REST API for the web app
- Protected ingestion endpoint (kept for future real data)

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

6. API: <http://localhost:8000/docs>
7. Web: <http://localhost:5173>

## Useful endpoints

- `GET /v1/cities`
- `GET /v1/cities/{city_id}/assets?bbox=minLon,minLat,maxLon,maxLat&type=pipe|node|river_segment`
- `GET /v1/assets/{asset_id}`
- `GET /v1/assets/{asset_id}/observations?metric=fill_ratio&from=...&to=...&granularity=5m&agg=avg`
- `GET /v1/cities/{city_id}/status`
- `GET /v1/hotspots?city_id=...&metric=overflow_risk⊤=20`
- `GET /v1/events?city_id=...&type=overflow&from=...&to=...`

## Notes

- Everything is **source-agnostic**: assets and telemetry have a unified schema so real data can be plugged later.
- PostGIS is installed in the Timescale HA image, but still must be enabled per DB via `CREATE EXTENSION postgis`.
- To limit seeding to specific cities, set `CITY_IDS` (comma-separated) before running seed scripts.
