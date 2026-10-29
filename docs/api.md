# API (MVP)

Base: `/v1`

Endpoints with `from` and `to` query parameters accept ISO 8601 timestamps
(including UTC `Z` and explicit time-zone offsets). Invalid timestamps return
HTTP 400 (`INVALID_ARGUMENT`); time windows must have `to` after `from`.

## OpenAPI snapshot
- Generate: `python scripts/export_openapi.py`
- Output: `docs/openapi/public.yaml`

## Timescale policies
- See `docs/runbooks/timescale.md` for retention + continuous aggregate details.

## Observability
- Metrics: `GET /metrics`
- See `docs/runbooks/observability.md`

## Security
- See `docs/runbooks/security.md`

## Assets
- `GET /cities`
- `GET /cities/{city_id}`
- `GET /cities/{city_id}/assets?bbox=minLon,minLat,maxLon,maxLat&type=pipe|node|river_segment`
- `GET /cities/{city_id}/assets?near=lon,lat&radius_m=500`
- `GET /cities/{city_id}/assets?tag=basin:basin_ne&tag=priority:critical`
- `GET /assets/{asset_id}`

Repeatable `tag=key:value` filters require every distinct tag to match (AND
semantics). Repeating an identical filter does not change the results.

Asset searches using `near=lon,lat&radius_m=500` measure `radius_m` in geodesic
metres (PostGIS geography), not projected Web Mercator metres.

## Telemetry
- `GET /assets/{asset_id}/metrics`
- `GET /assets/{asset_id}/observations?metric=...&from=...&to=...&granularity=5m&agg=avg`
- `GET /assets/{asset_id}/observations:compare?metric=...&from=...&to=...&granularity=5m&agg=avg&base_scenario_id=...&compare_scenario_id=...`

Both observation endpoints accept positive bucket widths in seconds, minutes,
hours or days (for example `5m`, `1h`, `1d`), up to 30 days. Invalid widths
return HTTP 400 (`INVALID_ARGUMENT`). The database receives validated, typed
PostgreSQL intervals for raw and gap-filled aggregation queries.

## Analytics
- `GET /cities/{city_id}/status`
- `GET /hotspots?city_id=...&metric=overflow_risk&top=20&run_id=...` (includes `confidence`)
- `GET /events?city_id=...&type=overflow&from=...&to=...&run_id=...` (includes `confidence`)
- `GET /analytics/runs?city_id=...`
- `GET /analytics/runs/diff?city_id=...&base_run_id=...&compare_run_id=...`
- `GET /analytics/calibration/recommendations?city_id=...&from=...&to=...&seasonality=all|monthly`
- `GET /analytics/calibration/overrides?city_id=...` (admin authentication outside local development; private, non-cacheable)
- `POST /analytics/calibration/overrides` (admin authentication outside local development)
- `POST /analytics/jobs` (export CSV + report CSV)
- `GET /analytics/jobs/{job_id}` (job status + logs)
- `GET /analytics/jobs/{job_id}/download`

CSV exports and reports run asynchronously. `POST /analytics/jobs` returns a
job with `status: "queued"` and no download path. Start the background worker
with `python -m floodmvp.jobs.queue_worker`, then poll the job endpoint until
its status is `completed` or `failed`. Download is available only after the job
has completed. Failed tasks are retried with backoff up to their configured
attempt limit; the worker records the final error in the job status and logs.
Export granularity accepts positive seconds, minutes, hours or days (for
example `5m`, `1h`, `1d`), up to 30 days. The worker passes this value to
PostgreSQL as a typed interval.

## Protected ingestion (kept for future)
- `POST /telemetry/events:batch` with header `Authorization: Bearer <INGEST_TOKEN>`

Request body:
```
{
  "device_id": "asset_id",
  "sent_at": "ISO8601",
  "events": [
    { "ts": "ISO8601", "type": "fill_ratio", "value": 0.7, "quality_flag": "ok" }
  ]
}
```

Notes:
- `type` maps to telemetry `metric`
- Supports `Idempotency-Key` header (7-day retention)
