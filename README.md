# City Flood MVP

[![CI](https://github.com/DiogoRibeiro7/city-flood-mvp/actions/workflows/ci.yml/badge.svg)](https://github.com/DiogoRibeiro7/city-flood-mvp/actions/workflows/ci.yml)
[![License](https://img.shields.io/github/license/DiogoRibeiro7/city-flood-mvp)](LICENSE)
[![Release](https://img.shields.io/github/v/release/DiogoRibeiro7/city-flood-mvp)](https://github.com/DiogoRibeiro7/city-flood-mvp/releases)
[![Last Commit](https://img.shields.io/github/last-commit/DiogoRibeiro7/city-flood-mvp)](https://github.com/DiogoRibeiro7/city-flood-mvp/commits/develop)
[![Issues](https://img.shields.io/github/issues/DiogoRibeiro7/city-flood-mvp)](https://github.com/DiogoRibeiro7/city-flood-mvp/issues)
[![Stars](https://img.shields.io/github/stars/DiogoRibeiro7/city-flood-mvp)](https://github.com/DiogoRibeiro7/city-flood-mvp/stargazers)
[![Python](https://img.shields.io/badge/Python-3.12--3.14-blue)](docs/releases/version-policy.md)
[![Node](https://img.shields.io/badge/Node-24-green)](docs/releases/version-policy.md)

City Flood MVP is a synthetic **city-scale flood monitoring demonstration**. It models drainage networks (pipes, rivers, gauges), generates telemetry, runs event and hotspot analytics, and presents the results in a web UI. Generic file and HTTP adapters already support external telemetry. Their presence does not establish a validated real-world data integration, and the analytics confidence scores are heuristic scores rather than calibrated flood probabilities.

The next targets are `v0.9.0-rc1` and an evidence-backed `v1.0.0` demonstration.
See the [versioned roadmap](ROADMAP.md), [implementation audit](docs/releases/implementation-audit.md),
and [release acceptance gates](docs/releases/v1-acceptance.md) for observed checks
and unresolved gaps. Municipal production readiness, tenant data isolation, and
achieved operational service levels have not been demonstrated.

The [Portuguese source assessment](docs/data/real-source-assessment.md) selects
a licensed historical Porto rainfall archive and records a small real fixture.
The [NOAA ingestion CLI](docs/runbooks/noaa_ghcnh.md) now supports bounded
historical downloads, offline previews and atomic reruns with provenance.
The [quality report](docs/runbooks/noaa_ghcnh_quality.md) describes missing data,
sampling, freshness, availability on an assumed grid and clipped interval
support from a checksummed live archive download.
Its six-hour mean rates remain separate from the 15-minute detector. The
[event evaluation protocol](docs/evaluation/event-protocol.md) provides tested
matching and scoring functions, with explicit label and timing requirements.
The [Porto case study](docs/case-studies/porto-2010/report.md) now reproduces
acquisition, validation, database ingestion/replay, interval analytics, tables,
figures and an observation timeline with [one command](docs/runbooks/noaa_case_study.md).
It is descriptive: independent real-event labels remain unavailable and no
prediction accuracy is established.

The [observability runbook](docs/runbooks/observability.md) defines proposed
API, ingestion, queue and analytics objectives, with worker scraping, bounded
metrics, tested alert examples and diagnostic dashboards. Operational attainment
and recovery objectives remain unverified.

## What’s included

- Multi-city synthetic assets + telemetry + analytics
- Event and hotspot analytics with confidence scores
- Versioned analytics runs + run diff API
- Calibration recommendations + threshold overrides (per city/season)
- Scenario comparison API (`observations:compare`)
- Report builder (CSV export job) + async job queue
- UI with map, incident timeline, drill-downs, saved views, shareable links
- Optional JWT role enforcement for reports, queue administration and field notes

## Stack

- Backend: FastAPI + SQLAlchemy (async) + Alembic + Poetry
- DB: TimescaleDB (Postgres) + PostGIS
- Web: Vite + React + Leaflet + Recharts (Yarn)
- Infra: Docker Compose

## Quickstart (local)

1. Copy env file

```bash
cp .env.example .env
```

The `.env` file contains local settings and credentials, and is intentionally
excluded from version control. The values in `.env.example` are for local demos
only; replace the default database password and ingestion token before exposing
the stack to other users or networks.

2. Start services

```bash
docker compose up -d --build db backend web
```

3. Seed synthetic assets + telemetry + analytics

```bash
bash ./scripts/seed_all.sh
docker compose up -d --build worker prometheus grafana
```

Start the worker after the seed script has applied migrations. The API and
worker share the exports volume; the worker metrics port stays inside Compose.

4. Open

- API docs: http://localhost:8000/docs
- Web UI: http://localhost:5173

## Tests

To build, migrate, seed and verify the full stack in disposable resources:

```bash
python -m scripts.smoke_stack
```

Requires Python 3.12+ and Docker Compose; no application `.env` or pre-started
services are needed. See the [smoke runbook](docs/runbooks/smoke.md) for isolation,
failure injection, diagnostics, cleanup and the shared CI/manual workflow.
The [candidate checklist](docs/releases/rc-checklist.md) records release checks,
artifact commands and the current no-go decision; the [version policy](docs/releases/version-policy.md)
defines the tested runtime matrix. No candidate has been tagged or published.

```bash
poetry run pytest -q tests/unit
```

The integration tests recreate application tables and therefore require a
**separate disposable PostgreSQL/TimescaleDB database** with PostGIS available.
They are skipped locally unless `TEST_DATABASE_URL` is set. Its database name
must start with `test_` or end with `_test`; the fixture never falls back to
the application `DATABASE_URL`.

```bash
TEST_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/floodmvp_test \
  poetry run pytest -q tests/integration
```

The separate migration suite runs `poetry run pytest -q tests/migrations` with
the same test URL. It creates fresh child databases and needs `CREATEDB` and
extension privileges. See the [migration runbook](docs/runbooks/migrations.md)
for schema checks, seeded upgrades, known differences and deployment steps.

GitHub Actions provisions an isolated database for both database suites as
part of the backend job. Never point `TEST_DATABASE_URL` at a database
containing data that you need to preserve.

## Authentication and deployment boundary

Local demos permit anonymous ordinary reads. Outside local environments, all
data routes require authentication and a configured `DEPLOYMENT_TENANT_ID`.
Use one dedicated database and export store per tenant; a city filter is not
tenant isolation. To use JWT, set:

- `JWT_SECRET`
- `JWT_ISSUER` (optional)
- `JWT_AUDIENCE` (optional)
- `JWT_ROLES_CLAIM` (optional, default `roles`)
- `DEPLOYMENT_TENANT_ID` (required outside local environments)
- `JWT_TENANT_CLAIM` (optional, default `tenant`)

Deployed JWTs need `exp`, `sub`, an admitted role and a string tenant claim
matching `DEPLOYMENT_TENANT_ID` exactly. The legacy API key is accepted only
when JWT is disabled and grants full access to that dedicated deployment.
Missing deployment/authentication configuration returns 503; unauthenticated
data reads return 401 and foreign-tenant tokens return 403. Health remains
public; ingestion uses its separate secret. Keep metrics on a private network.

Roles used:

- `viewer`: read-only UI
- `analyst`: report/export jobs + note creation
- `admin`: calibration overrides, job queue administration + note deletion

Note list/detail reads require `viewer`, `analyst` or `admin` when JWT auth is
enabled. If JWT is disabled, the configured `X-API-Key` is accepted instead.
Anonymous note reads remain available only for local demos without credentials.
The web UI sends the runtime JWT on all data requests. Paste it in the JWT
field and select **Apply token** to reload data and discard the previous
identity's caches. Apply an empty token to log out. Do not embed credentials
in `VITE_*` variables or client-side code; the demo stores its token in browser
local storage, which is accessible to same-origin scripts.

## Key endpoints

- `GET /v1/cities`
- `GET /v1/cities/{city_id}/assets?bbox=minLon,minLat,maxLon,maxLat&type=pipe|node|river_segment`
- `GET /v1/assets/{asset_id}`
- `GET /v1/assets/{asset_id}/observations?metric=fill_ratio&from=...&to=...&granularity=5m&agg=avg`
- `GET /v1/assets/{asset_id}/observations:compare?metric=...&from=...&to=...&base_scenario_id=...&compare_scenario_id=...`
- `GET /v1/cities/{city_id}/status`
- `GET /v1/cities/{city_id}/summary?minutes=15`
- `GET /v1/hotspots?city_id=...&metric=overflow_risk&top=20`
- `GET /v1/events?city_id=...&type=overflow&from=...&to=...`
- `GET /v1/notes?city_id=...` (authenticated outside local development)
- `GET /v1/notes/{note_id}` (authenticated outside local development)
- `GET /v1/analytics/runs`
- `GET /v1/analytics/runs/diff`
- `GET /v1/analytics/calibration/recommendations`
- `GET /v1/analytics/calibration/overrides` (admin authentication outside local development)
- `POST /v1/analytics/calibration/overrides` (admin authentication outside local development)
- `POST /v1/analytics/jobs` (export CSV + report CSV)
- `GET /v1/analytics/jobs/{job_id}`
- `GET /v1/analytics/jobs/{job_id}/download`
- `GET /v1/jobs/queue`
- `POST /v1/jobs/queue/{job_id}/retry`
- `POST /v1/jobs/queue/{job_id}/cancel`

## Ops notes

- Per-IP and per-tenant request quotas are in-memory and process-local. Tenant
  attribution comes from verified JWT claims or the configured API key;
  client-supplied `X-Tenant-Id` headers are ignored for quotas and metrics.
- The target release requires **one API process and one API replica** per
  dedicated deployment. The container explicitly starts `uvicorn --workers 1`.
  Multiple API processes/replicas, including overlapping rollout replicas, are
  unsupported until a shared limiter is implemented and measured. Queue workers
  are separate from this API-process constraint.
- PostGIS is installed in the Timescale image but must be enabled per DB (`CREATE EXTENSION postgis`).
- To limit seeding to specific cities, set `CITY_IDS` (comma-separated).
- Background jobs are queued; run the worker with:

```bash
poetry run python -m floodmvp.jobs.queue_worker
```

- Periodic analytics scheduler:

```bash
poetry run python -m floodmvp.jobs.scheduler --interval-minutes 60
```

## Data adapters

See `docs/runbooks/ingest_adapters.md` for external ingestion contracts and adapters.

## Deployment reference

See `docs/deployment/reference.md` for single-tenant and multi-tenant deployment guidance.

## IaC + secrets

See `docs/deployment/iac_and_secrets.md` for IaC structure and secrets management guidance.

## Backup/restore

Run `poetry run python -m scripts.recovery_drill` for a disposable synthetic
backup/restore, worker interruption/restart, retry and stale-job detection drill.
See [the recovery runbook](docs/deployment/backup_restore_drills.md) for safeguards,
measured evidence, proposed RTO/RPO targets and manual incident actions.

## Security review

See `docs/deployment/security_checklist.md` for the security checklist and compliance notes.
For deployments outside local development, set `APP_ENV=prod`, a dedicated
`DEPLOYMENT_TENANT_ID`, and `JWT_SECRET` (recommended) or `ANALYTICS_API_KEY`.
Data endpoints return 503 if deployment/authentication configuration is missing.
The demo Compose ports bind only to loopback; remote access requires explicit
deployment configuration. The default `APP_ENV=dev` is for
local demonstrations only. Ingestion also requires a separate, non-default
`INGEST_TOKEN` in production; startup rejects the documented demo credential.
See the [security review and measured quota boundary](docs/releases/security-review.md).
