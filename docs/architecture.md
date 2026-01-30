# Architecture (MVP)

## Components
- **DB**: Postgres + TimescaleDB extension + PostGIS
- **Backend**: FastAPI
- **Web**: React map + charts

## Data flow
1. `seed_assets` generates a synthetic city network (river + nodes + pipes + gauges).
2. `seed_telemetry` generates synthetic time series and writes to the Timescale hypertable.
3. `run_analytics` computes:
   - rain events
   - overflow episodes (fill_ratio threshold)
   - hotspots (top assets by overflow minutes)
   - city status summary

## Key design choice
- A unified telemetry table `(asset_id, metric, ts, value)` avoids schema churn when new sensors or metrics appear.
