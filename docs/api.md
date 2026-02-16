# API (MVP)

Base: `/v1`

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
- `GET /cities/{city_id}/assets?bbox=minLon,minLat,maxLon,maxLon&type=pipe|node|river_segment`
- `GET /assets/{asset_id}`

## Telemetry
- `GET /assets/{asset_id}/metrics`
- `GET /assets/{asset_id}/observations?metric=...&from=...&to=...&granularity=5m&agg=avg`
- `GET /assets/{asset_id}/observations:compare?metric=...&from=...&to=...&granularity=5m&agg=avg&base_scenario_id=...&compare_scenario_id=...`

## Analytics
- `GET /cities/{city_id}/status`
- `GET /hotspots?city_id=...&metric=overflow_risk&top=20&run_id=...` (includes `confidence`)
- `GET /events?city_id=...&type=overflow&from=...&to=...&run_id=...` (includes `confidence`)
- `GET /analytics/runs?city_id=...`
- `GET /analytics/runs/diff?city_id=...&base_run_id=...&compare_run_id=...`
- `GET /analytics/calibration/recommendations?city_id=...&from=...&to=...&seasonality=all|monthly`
- `GET /analytics/calibration/overrides?city_id=...`
- `POST /analytics/calibration/overrides`
- `POST /analytics/jobs` (export CSV)
- `GET /analytics/jobs/{job_id}` (job status + logs)
- `GET /analytics/jobs/{job_id}/download`

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
