# API Security (MVP)

## Supported release boundary

Outside `APP_ENV=dev|development|local|test`, use **one dedicated tenant, one
database/export store, one API process and one API replica** per deployment.
Set `DEPLOYMENT_TENANT_ID` and either JWT or the legacy API key. All data routers
check admission before database dependencies. A signed foreign-tenant JWT is
rejected even if it carries an administrator role or a forged `X-Tenant-Id`.
This is deployment admission, not shared-database row isolation: never place
another tenant's data in the same store, and use distinct secrets per deployment.

JWT requires `exp` and `sub` outside local environments, plus a string tenant
claim exactly matching the deployment ID and a recognized role. Missing or
invalid JWTs return 401; rejected tenants/roles return 403. Missing deployment
identity or authentication configuration returns 503 on data routes. Set issuer
and audience restrictions for the issuing authority; they remain configurable.
Local demos keep their existing anonymous-read and privileged-operation behavior.
Health is public. Ingestion uses its separate deployment secret; JWT is not an
ingestion credential. Keep `/metrics` and worker metrics private at ingress;
the API does not authenticate Prometheus scrapes. Schema/docs expose structure,
not data, and should also stay private in restricted deployments.

The [security review](../releases/security-review.md) records the compatibility
change, attack cases, process measurements and remaining release blockers.

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
- **Do not run multiple API processes or replicas for this release.** The
  backend image explicitly starts `uvicorn --workers 1`; Compose declares one
  replica. Manual starts must also use `--workers 1`, regardless of
  `WEB_CONCURRENCY`. Do not use API autoscaling or overlapping rolling replicas.
  Queue workers do not run the HTTP limiter and are a separate concern.
- Two real Python processes each accept two requests for a configured burst of
  two, admitting four in total. Both IP and tenant quota tests reproduce this.
  A shared limiter is not implemented; restarts and LRU eviction also reset
  local buckets. These limits are abuse controls, not billing/security isolation.
- Configure only known reverse-proxy addresses as Uvicorn's trusted forwarded
  peers; never trust arbitrary client `X-Forwarded-For`. Prevent clients from
  bypassing the proxy. Without forwarded-header processing, all proxy traffic
  shares one per-IP bucket. See the [Uvicorn settings](https://uvicorn.dev/settings/).

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
- Outside local environments, missing both credentials or the deployment ID
  makes all data endpoints return HTTP 503 (`AUTH_NOT_CONFIGURED`).
- Anonymous access without configured credentials is retained for local demos
  only. Never deploy with a development `APP_ENV` on a public network.
- Protected operations:
  - Analytics/report job creation, status and downloads: `analyst` or `admin`.
  - Calibration overrides and job queue administration: `admin`.
  - List/read notes: `viewer`, `analyst` or `admin`.
  - Create notes: `analyst` or `admin`; delete notes: `admin`.
- The legacy API key has no role distinction; prefer JWT for production.
- Ordinary read endpoints require at least `viewer` outside local environments.
  Deployed data responses carry `Cache-Control: private, no-store`, overriding
  the asset endpoint's local-demo cache policy.
- All web data requests use a runtime JWT. **Apply token** saves it and reloads
  the application, discarding cached records and pending requests from the old
  identity. Apply an empty value to log out. The UI role selector controls
  presentation only; the server authorizes the signed roles.
- The demo retains JWTs in local storage. Same-origin JavaScript, including an
  XSS payload or extension, can read them; this is not a hardened login/session
  system. Never put JWT signing secrets, ingestion tokens or legacy keys in
  `VITE_*` variables: [Vite exposes them to client code](https://vite.dev/guide/env-and-mode).
  `VITE_API_BASE` is public configuration and must identify the intended API.

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
- Local asset responses use `Cache-Control: public, max-age=60`; deployed data
  responses use `private, no-store`, including rejected requests.
