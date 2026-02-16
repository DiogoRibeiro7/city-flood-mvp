# Data model (MVP)

## assets
Generic registry for all physical things.
- `asset_type`: river_segment | node | pipe | outfall | rain_gauge | river_gauge | tank | pump
- `geom`: PostGIS geometry
- `props`: JSONB for flexible metadata
Indexes:
- `asset.geom` GIST for bbox/near queries
- `(city_id, asset_type)` for filtering

## telemetry_observation (Timescale hypertable)
- `asset_id`, `metric`, `ts`, `value`, `quality_flag`, `source`, `ingested_at`
Indexes:
- PK `(asset_id, metric, ts)`
- `(asset_id, ts DESC)` and BRIN on `ts` for range scans
- `(asset_id, scenario_id, metric)` for per-scenario metric discovery

## analytics_event
- event windows derived from telemetry (rain episode, overflow)
- scoped to an `analytics_run` via `run_id` (versioned outputs)
- `confidence` captures reliability of detection (0..1)
Indexes:
- `(run_id)` and `(city_id, run_id, start_ts)` for event listing

## analytics_hotspot_daily
- daily snapshot for UI: "top N pipes/nodes by overflow risk"
- scoped to an `analytics_run` via `run_id` (versioned outputs)
- `confidence` captures reliability of score (0..1)
Indexes:
- `(run_id, metric, score)` for top-N queries

## asset_status_latest
- latest risk score per asset (cheap for dashboards)
Indexes:
- `(city_id, status)` for summary counts

## analytics_run
- audit trail for analytics runs (params + metrics + versioning)

## analytics_threshold_override
- calibration overrides per city/season
- fields: `city_id`, `season`, `thresholds`, `notes`, `created_at`

## telemetry_qa_daily
- daily telemetry QA summary (gaps + suspect counts)

## export_job_log
- job-level audit log entries (status transitions + errors)
