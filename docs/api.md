# API (MVP)

Base: `/v1`

Endpoints with `from` and `to` query parameters accept ISO 8601 timestamps
(including UTC `Z` and explicit time-zone offsets). Invalid timestamps return
HTTP 400 (`INVALID_ARGUMENT`); time windows must have `to` after `from`.

## OpenAPI snapshot
- Generate: `python scripts/export_openapi.py`
- Output: `docs/openapi/public.yaml`

The public snapshot includes every live route, including the comparison,
calibration, queue and notes endpoints. CI tests compare it with the current
FastAPI schema and verify that endpoint-specific error codes are preserved.
Regenerate the snapshot whenever an endpoint or its documented responses change.

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
- `GET /assets/{asset_id}/upstream?depth=2`
- `GET /assets/{asset_id}/downstream?depth=2`

Repeatable `tag=key:value` filters require every distinct tag to match (AND
semantics). Repeating an identical filter does not change the results.

Network traversal is limited to assets in the starting asset's city. When the
starting asset is a pipe, its immediately adjacent node in the requested
direction is included; the starting pipe itself is not repeated in the result.
Each depth level returns pipes, then nodes, ordered by asset ID. Frontiers are
queried in batches to avoid per-node database round trips on branching networks.
For either direction, an unknown starting asset returns HTTP 404
(`ASSET_NOT_FOUND`), while a known asset with no connections returns HTTP 200
with an empty array.

Asset searches using `near=lon,lat&radius_m=500` measure `radius_m` in geodesic
metres (PostGIS geography), not projected Web Mercator metres.
Both `bbox` and `near` require finite WGS84 coordinates: longitudes from -180
to 180 and latitudes from -90 to 90. Bounding boxes must have `minLon < maxLon`
and `minLat < maxLat`; extents that cross the antimeridian are not supported.
The search radius must be finite and between 1 and 50,000 metres. Invalid
spatial parameters return HTTP 400 (`INVALID_ARGUMENT`).

## Telemetry
- `GET /assets/{asset_id}/metrics`
- `GET /assets/{asset_id}/observations?metric=...&from=...&to=...&granularity=5m&agg=avg`
- `GET /assets/{asset_id}/observations:compare?metric=...&from=...&to=...&granularity=5m&agg=avg&base_scenario_id=...&compare_scenario_id=...`

Both observation endpoints accept positive bucket widths in seconds, minutes,
hours or days (for example `5m`, `1h`, `1d`), up to 30 days. Invalid widths
return HTTP 400 (`INVALID_ARGUMENT`). The database receives validated, typed
PostgreSQL intervals for raw and gap-filled aggregation queries.
Gap-filled queries use PostgreSQL `generate_series` with TimescaleDB `time_bucket`
to include empty buckets as nulls; they work with the OSS image and are capped
at 10,000 buckets per request.

The optional `scenario_id` filter accepts an existing scenario ID or `latest`.
The comparison endpoint requires two existing scenarios. An unknown ID, or
`latest` when no scenarios have been created, returns HTTP 404
(`SCENARIO_NOT_FOUND`); an existing scenario with no matching telemetry returns
an empty result with HTTP 200.

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
