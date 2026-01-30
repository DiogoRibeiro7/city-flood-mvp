# API (MVP)

Base: `/v1`

## Assets
- `GET /cities`
- `GET /cities/{city_id}`
- `GET /cities/{city_id}/assets?bbox=minLon,minLat,maxLon,maxLon&type=pipe|node|river_segment`
- `GET /assets/{asset_id}`

## Telemetry
- `GET /assets/{asset_id}/metrics`
- `GET /assets/{asset_id}/observations?metric=...&from=...&to=...&granularity=5m&agg=avg`

## Analytics
- `GET /cities/{city_id}/status`
- `GET /hotspots?city_id=...&metric=overflow_risk&top=20`
- `GET /events?city_id=...&type=overflow&from=...&to=...`

## Protected ingestion (kept for future)
- `POST /telemetry/events:batch` with header `Authorization: Bearer <INGEST_TOKEN>`
