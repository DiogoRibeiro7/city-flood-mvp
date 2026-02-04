# City Flood MVP — Roadmap

## Repo analysis (current state)
- Backend: FastAPI app in `src/floodmvp/api` with routers for cities, assets, telemetry, analytics, ingest, and health.
- Storage: Async SQLAlchemy + TimescaleDB + PostGIS; migrations in `infra/db/migrations` and DB init in `infra/db/init.sql`.
- Data generation: Synthetic network + telemetry + scenarios under `src/floodmvp/generators` and jobs in `src/floodmvp/jobs`.
- Analytics: Rain events, overflow events, hotspots, and city status in `src/floodmvp/analytics`.
- Web: Vite + React + Leaflet + Recharts app under `web/` consuming public REST endpoints.
- Ops: Docker Compose for local stack; observability configs for Prometheus + Grafana in `infra/observability`.
- Tests: Unit + integration tests in `tests/` covering generators, analytics, ingest, exports, and telemetry QA.

## Roadmap

### Milestone 0 — Baseline validation (1–2 days)
- [ ] Confirm local stack boots end-to-end (`docker compose up -d --build`).
- [ ] Run seed scripts and verify data lands in Timescale/PostGIS.
- [ ] Run API smoke tests + web UI manual check (map loads, basic queries work).
- [ ] Capture initial performance baselines (seed time, API p95 for key endpoints).

### Milestone 1 — Data model hardening (3–5 days)
- [ ] Review migrations for production readiness (extensions, indexes, retention policies).
- [ ] Add/verify spatial indexes for asset geometry + bbox queries.
- [ ] Validate telemetry hypertable + continuous aggregate policies (if used).
- [ ] Define schema contracts in `docs/data-model.md` for assets, telemetry, and analytics outputs.

### Milestone 2 — API robustness (3–5 days)
- [ ] Validate request/response envelopes and consistent error handling.
- [ ] Add pagination + filtering for assets and events endpoints.
- [ ] Tighten ingest security (token rotation guidance, rate limits, idempotency behavior).
- [ ] Expand OpenAPI to include examples for all public endpoints.

### Milestone 3 — Analytics accuracy + auditability (4–7 days)
- [ ] Define thresholds and event definitions in config (not hard-coded).
- [ ] Add QA metrics for telemetry gaps and event detection.
- [ ] Create reproducible analytics runs (scenario inputs, run metadata, output versioning).
- [ ] Add export job status/traceability (job logs and failure reasons).

### Milestone 4 — Web UX iteration (4–7 days)
- [x] Refine map layers (asset types, status overlays, hotspots).
- [x] Add interactive time range controls for telemetry + events.
- [x] Improve loading/error states and performance (query caching, bbox debouncing).
- [x] Document UI workflows for demo readiness.

### Milestone 5 — Observability + ops (2–4 days)
- [x] Validate Prometheus scrape + Grafana dashboards.
- [x] Add API latency and DB query metrics where missing.
- [x] Document runbooks for backup/restore, retention, and scaling.

### Milestone 6 — Release readiness (2–3 days)
- [ ] Establish CI (lint, typecheck, tests) and tighten pre-commit.
- [ ] Add reproducible demo dataset and a single command to reset the environment.
- [ ] Produce a short demo script + screenshots for stakeholders.

## Open questions / decisions
- Do we need multi-city datasets in the default seed, or keep one canonical city?
- What level of realism is required for telemetry distributions and event definitions?
- What SLA/latency targets should the API meet for the demo?
- Which endpoints must remain stable for external consumers?
