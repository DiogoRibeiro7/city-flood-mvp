# Data model (MVP)

## assets
Generic registry for all physical things.
- `asset_type`: river_segment | node | pipe | outfall | rain_gauge | river_gauge | tank | pump
- `geom`: PostGIS geometry
- `props`: JSONB for flexible metadata

## telemetry_observation (Timescale hypertable)
- `asset_id`, `metric`, `ts`, `value`, `quality_flag`, `source`, `ingested_at`

## analytics_event
- event windows derived from telemetry (rain episode, overflow)

## analytics_hotspot_daily
- daily snapshot for UI: "top N pipes/nodes by overflow risk"

## asset_status_latest
- latest risk score per asset (cheap for dashboards)
