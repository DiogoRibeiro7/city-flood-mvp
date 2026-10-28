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
- Retries with the same idempotency key and identical request return the prior
  response without inserting events again. Simultaneous retries are serialized.
- Reusing a key with a different request, including a changed sensor reading,
  returns HTTP 409 (`IDEMPOTENCY_CONFLICT`). Keys must be 1–128 characters.
- The server cleans idempotency rows older than 7 days.
- Invalid or missing bearer tokens return HTTP 401 with a Bearer challenge.
