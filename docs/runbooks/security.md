# API Security (MVP)

## Browser origins (CORS)
- Local development (`APP_ENV=dev|development|local|test`) permits all browser
  origins by default so the Vite demo works from `http://localhost:5173`.
- Other environments deny cross-origin browser access by default. Set
  `CORS_ALLOWED_ORIGINS=https://dashboard.example.com,https://admin.example.com`
  to allow specific origins. Include the scheme and port (when applicable),
  without paths or a trailing slash.
- A wildcard origin (`*`) is rejected outside local development. Credentials
  are not enabled in the CORS middleware. Browser CORS checks do not replace
  endpoint authorization or restrict non-browser HTTP clients.

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
- The API rejects declared oversize bodies before reading them and enforces
  the limit against the actual streamed bytes, including absent, invalid or
  understated `Content-Length` headers. Accepted bodies are replayed to their
  endpoints for normal JSON parsing. This limit is per API process.
- Request timeout: 10s (`REQUEST_TIMEOUT_S`). A single deadline covers
  receiving the request body and waiting for the endpoint's response headers.
  A slow or stalled upload returns HTTP 504 with the normal request ID, log
  entry, and HTTP error metrics. Streaming response bodies after headers are
  sent are not covered by this deadline.

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
- The documented `dev-ingest-token` is for local use only. For staging and
  production, set `INGEST_TOKEN` to a unique secret (for example one generated
  with `openssl rand -hex 32`). Non-local application startup rejects a missing
  token or the development token. The endpoint also checks this at request
  time, failing closed if configuration changes without restarting.
- Rotate tokens regularly; never embed in client-side code.
- Prefer server-to-server usage behind TLS and allowlist by IP when possible.
- Use `Idempotency-Key` to safely retry batches (7-day retention).
- Rate limits apply globally; keep batch sizes reasonable to avoid 413s.

## Cache headers
- Assets endpoints return `Cache-Control: public, max-age=60`.
