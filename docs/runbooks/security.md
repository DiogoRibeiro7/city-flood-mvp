# API Security (MVP)

## Rate limiting
- In-memory token bucket per client IP.
- Defaults: 5 rps with burst 20.
- Tunable via `RATE_LIMIT_RPS` and `RATE_LIMIT_BURST`.
- Per-client and per-tenant bucket caches use a least-recently-used cap
  (`RATE_LIMIT_BUCKET_CAPACITY`, default 4096 entries each, per process).
- Tenant quotas use a verified JWT tenant claim, or a shared `analytics-key`
  identity for requests with the configured API key. A valid JWT without a
  tenant claim is counted as `authenticated`; other traffic as `public`.
  Untrusted `X-Tenant-Id` request headers do not select quota buckets.
- Prometheus HTTP metrics use route templates instead of concrete request
  paths; unknown URLs are grouped under `<unmatched>`.
- Limits are process-local. Use an external rate limiter for consistent limits
  across multiple API replicas.

## Request limits
- Max request size: 1 MB (`REQUEST_MAX_BYTES`).
- Request timeout: 10s (`REQUEST_TIMEOUT_S`).

## API keys (analytics)
- Privileged endpoints require JWT authentication when `JWT_SECRET` is set.
  JWT roles are checked server-side. The legacy `X-API-Key` is accepted only
  when JWT is not configured.
- Outside `APP_ENV=dev|development|local|test`, missing both credentials makes
  privileged endpoints return HTTP 503 (`AUTH_NOT_CONFIGURED`). This avoids
  silently exposing administrative operations in staging or production.
- Anonymous access without configured credentials is retained for local demos
  only. Never deploy with a development `APP_ENV` on a public network.
- Protected operations:
  - Analytics/report job creation, status and downloads: `analyst` or `admin`.
  - Calibration overrides and job queue administration: `admin`.
  - List/read notes: `viewer`, `analyst` or `admin`.
  - Create notes: `analyst` or `admin`; delete notes: `admin`.
- The legacy API key has no role distinction; prefer JWT for production.
- Other read endpoints remain public. Note list/detail responses carry
  `Cache-Control: private, no-store` to avoid caching note content.
- Note reads and writes from the web UI use a configured JWT. Keep the legacy
  API key server-side; never expose it in a browser bundle.

## Ingest endpoint (protected)
- Endpoint: `POST /v1/telemetry/events:batch`
- Requires `Authorization: Bearer <INGEST_TOKEN>`.
- Rotate tokens regularly; never embed in client-side code.
- Prefer server-to-server usage behind TLS and allowlist by IP when possible.
- Use `Idempotency-Key` to safely retry batches (7-day retention).
- Rate limits apply globally; keep batch sizes reasonable to avoid 413s.

## Cache headers
- Assets endpoints return `Cache-Control: public, max-age=60`.
