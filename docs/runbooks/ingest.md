# Ingestion Runbook

## Overview
The ingestion endpoint accepts batched telemetry events with idempotency support:

- Endpoint: `POST /v1/telemetry/events:batch`
- Auth header: `Authorization: Bearer <INGEST_TOKEN>`
- Optional: `Idempotency-Key` header (retained for 7 days)

## Example request
```
curl -X POST "$API_BASE/v1/telemetry/events:batch" \
  -H "Authorization: Bearer $INGEST_TOKEN" \
  -H "Idempotency-Key: demo-001" \
  -H "Content-Type: application/json" \
  -d '{
    "device_id": "asset_id",
    "sent_at": "2026-01-30T12:00:00Z",
    "events": [
      { "ts": "2026-01-30T11:59:00Z", "type": "fill_ratio", "value": 0.7, "quality_flag": "ok" }
    ]
  }'
```

## Expected response
```
{
  "device_id": "asset_id",
  "received": 1,
  "accepted": 1,
  "rejected": 0,
  "results": [
    { "ts": "2026-01-30T11:59:00Z", "type": "fill_ratio", "status": "accepted" }
  ]
}
```

## Operational notes
- `device_id` must match an existing `asset.asset_id`.
- Duplicate idempotency keys return the prior response without re-inserting.
- The server cleans idempotency rows older than 7 days.
