# API Security (MVP)

## Rate limiting
- In-memory token bucket per client IP.
- Defaults: 5 rps with burst 20.
- Tunable via `RATE_LIMIT_RPS` and `RATE_LIMIT_BURST`.

## Request limits
- Max request size: 1 MB (`REQUEST_MAX_BYTES`).
- Request timeout: 10s (`REQUEST_TIMEOUT_S`).

## API keys (analytics)
- Heavy analytics endpoints require `X-API-Key` when `ANALYTICS_API_KEY` is set.
- Endpoints: `/v1/analytics/jobs`, `/v1/analytics/jobs/{job_id}/download`.

## Ingest endpoint (protected)
- Endpoint: `POST /v1/telemetry/events:batch`
- Requires `Authorization: Bearer <INGEST_TOKEN>`.
- Rotate tokens regularly; never embed in client-side code.
- Prefer server-to-server usage behind TLS and allowlist by IP when possible.
- Use `Idempotency-Key` to safely retry batches (7-day retention).
- Rate limits apply globally; keep batch sizes reasonable to avoid 413s.

## Cache headers
- Assets endpoints return `Cache-Control: public, max-age=60`.
