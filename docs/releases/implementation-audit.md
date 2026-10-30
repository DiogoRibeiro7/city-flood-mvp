# Implementation and verification audit

Audit date: 2026-10-30. Baseline: `develop` at
`5b4a600b1c4e73638284b54113de53e3339f7ca2`.
Both the remote default and integration branch were verified as `develop`.
The local checkout was 92 commits behind; this audit uses the fetched baseline.
The open PRs returned by the GitHub review were dependency/action updates, not
evidence that the release work below had been completed. They were not merged
or included in this audit.

## Status meanings

- **Implemented and tested:** the described behavior has implementation and
  relevant automated assertions that passed in this audit. Scope and limitations
  still apply; this does not imply a complete workflow or operational validation.
- **Implemented but unverified:** a substantive code or documentation path was
  inspected, but the relevant end-to-end behavior was not established here.
- **Incomplete:** part exists, but a required part or verification gate is
  demonstrably missing or failing.
- **Absent:** no implementation/evidence for the capability was found in the
  inspected source, tests, CI, scripts, or runbooks. A future design is not code.

Commands and actual results are recorded in
[v1-acceptance.md](v1-acceptance.md#baseline-verification-record).
The subsequent [API contract audit](api-contract-audit.md) records prompt 3
findings and fixes against the merged prompt 2 baseline.
The [migration verification follow-up](../runbooks/migrations.md) records prompt 4
schema comparisons, seeded upgrade evidence and the ORM timestamp-default fix.
The inventory distinguishes deterministic software assertions from observed
hydrological or operational evidence.

## Current feature inventory

Paths below are relative to the repository root; source paths without another
prefix are under `src/floodmvp/`.

| Capability | Status | Inspected implementation and verification boundary |
| --- | --- | --- |
| Synthetic networks and telemetry generators | Implemented and tested | `generators/city_network.py`, `generators/telemetry.py`; `tests/unit/test_generators.py` checks counts, seeded repeatability and ordered timestamps. `test_realism.py` checks rainfall disaggregation totals. The seed CLI uses the current time, so a reproducible full-stack dataset still needs a fixed window. |
| Asset filtering and network traversal | Implemented and tested | `storage/repos/assets.py`; unit tests for spatial validation, proximity, tags and network scoping/responses; integration tests for geodesic distance, branching, cycles and cross-city links. City consistency is not proof of tenant authorization. |
| Observation and scenario APIs | Implemented and tested | `api/routers/telemetry.py`, `storage/repos/telemetry.py`; timestamp, interval, gap, and scenario-reference tests. A full scenario comparison UI journey remains unverified. |
| Rain/overflow detection and coverage | Implemented and tested | `analytics/threshold_events.py`, rain/overflow modules, `jobs/run_analytics.py`; `test_threshold_events.py` checks gaps, duplicates and duration; `test_analytics_coverage.py` checks distinct buckets. No independent flood-event accuracy evaluation exists. Confidence combines heuristic coverage and signal terms. |
| Analytics runs, diffs and calibration | Implemented but unverified | `api/routers/analytics.py`, `storage/repos/analytics.py`, migrations 0013-0015. Validation and access-control tests cover calibration inputs; the full run/diff/recommendation workflow and its scientific calibration were not established. |
| Authenticated ingest and idempotency | Implemented and tested | `api/routers/ingest.py`, `storage/repos/ingest.py`; unit and PostgreSQL tests cover auth, replay, changed payloads and bounded expiry cleanup. `scripts/smoke_ingest_idempotency.py` adds a seeded-API concurrency check, separate from this test evidence. |
| Queued CSV exports and lock lifecycle | Implemented and tested | `jobs/queue_worker.py`, `storage/repos/jobs.py`; serialization, reference, CSV and PostgreSQL lock tests. `scripts/smoke_export_jobs.py` exercises export/report completion and failed-SQL recovery against a seeded API; a standalone orchestration/restart drill is still missing. |
| Full-stack start, seed, worker and scheduler | Incomplete | Compose starts DB/API/web/Prometheus/Grafana, but no worker or scheduler service. README lists manual commands. `scripts/seed_all.sh` migrates/seeds/runs analytics; baseline and smoke scripts do not together provide an isolated, deterministic, rerunnable orchestrator with cleanup. |
| Schema migration verification | Incomplete | Eighteen chained Alembic revisions, ending at `0018_ingest_expiry`. Integration fixtures instead use ORM `drop_all/create_all`, so their success does not prove migration/model equivalence, Timescale policies or safe upgrades. Fresh-migration evidence is tracked separately in the acceptance record. |
| Public OpenAPI snapshot and error envelopes | Implemented and tested | `scripts/export_openapi.py`, `docs/openapi/public.yaml`; `test_public_openapi_export.py` compares the generated schema, routes and response codes and checks cache immutability. Timestamp/error-envelope tests add request-level assertions; exhaustive pagination/filter contract coverage remains to audit. |
| JWT/API-key roles, CORS and request limits | Implemented and tested | `common/auth.py`, `api/main.py`, privileged-access, ingestion-auth, CORS, body-limit, quota and observability tests. Privileged requests fail closed outside local environments when unconfigured. These checks do not establish tenant-owned row access or distributed quotas. |
| Tenant data isolation and distributed quota enforcement | Incomplete | Verified JWT/API-key tenant attribution feeds process-local quotas/metrics. `request.state.tenant_id` is assigned in middleware, but role authorization and city query filters do not bind all row access to that identity. Shared-database tenant hosting in the deployment reference is a design option. |
| Map, timeline, drill-downs and saved views | Implemented but unverified | `web/src/pages/App.tsx`, `web/src/api.ts` implement the flows. Build/type checks do not verify interactions. Playwright capture scripts wait for map content and take screenshots, with optional hotspot interactions; they are not comprehensive assertions or accessibility tests. |
| Portuguese real-data experiment and evaluation | Absent | No selected provider assessment, permitted station fixture, quality report, independent event labels, evaluation protocol or one-command historical case study found. Generic adapters and the ERA5-assisted generator do not establish those deliverables. |
| Release provenance and final gate evidence | Absent | No release acceptance record existed before this PR; package/web metadata remain `0.1.0`, and Poetry author metadata is a placeholder. A changelog, version policy and verified citation details remain release tasks. |

## Reconciliation of every 2026 H1 milestone item

The previous checkboxes mixed implementation, plans and operational claims.
These entries supersede them without treating existing files as proof of success.

| Historical item | Previous state | Current status | Evidence and remaining work |
| --- | --- | --- | --- |
| A: pilot cities, onboarding, acceptance | Checked | Implemented but unverified | `docs/pilot.md` defines three synthetic city configurations and acceptance targets. No actual stakeholder sign-off, 30-day coverage or seven-day export evidence was found. |
| A: daily ops runbook | Checked | Implemented but unverified | `docs/runbooks.md` contains queue inspection, alert triage and incident steps. No recorded operator exercise or incident recovery evidence. |
| A: API usage and tenant quotas | Checked | Implemented and tested | Middleware and `test_request_limits.py`/`test_request_observability.py` cover authenticated attribution, spoofed headers, bounded quota buckets and metric labels. Quotas remain process-local, not shared across workers; metric cardinality across tenants still needs review. |
| A: weekly QA report | Checked | Implemented but unverified | `jobs/qa_weekly_report.py` aggregates daily QA into CSV; the inspected scheduler only enqueues analytics and prunes ingest keys. No automated weekly schedule/report artifact or dedicated weekly-report assertions found. |
| B: outlier/gap/drift rules | Unchecked | Incomplete | `jobs/qa_telemetry.py` implements all three. Outlier and observation-gap tests exist, but drift/report semantics lack focused assertions. QA expected buckets derive from each observed span, excluding completely silent assets and leading/trailing missing intervals. |
| B: lineage and source tags | Unchecked | Implemented but unverified | Migration 0016, `models/db.py`, `adapters/external_ingest.py` and ingestion CLIs store source/type/id, lineage and import ID. No end-to-end provenance round-trip assertion found. |
| B: dataset versioning and import validation | Unchecked | Implemented but unverified | Ingestion CLIs hash inputs and persist `DatasetImport` counts/reasons/version. `--dry-run` still commits a validation/import row; it is not a zero-write mode. Unit conversion tests do not prove dataset audit persistence or safe reruns. |
| B: per-city retention and compliance tags | Unchecked | Incomplete | Migration 0016 adds city metadata, but no enforcement uses these fields outside the model. Migration 0003 has global Timescale policies with edition-dependent fallbacks; these are not per-city retention. Tags do not establish compliance. |
| C: incident templates | Unchecked | Implemented but unverified | `App.tsx` provides storm-response, asset-failure and maintenance draft generation, copying and printing. No browser assertions for the template workflow. |
| C: notes, annotations and share links | Unchecked | Implemented but unverified | Migration 0017, note API/repository and `App.tsx` implement persistence, attachments and URL note selection. Backend tests cover roles/reference-city consistency, but collaboration/share/delete behavior has no complete browser test. |
| C: executive mode | Unchecked | Implemented but unverified | `App.tsx` has an executive toggle and summary rendering. No focused component/browser assertions or stakeholder validation. |
| C: scenario comparison UI | Unchecked | Implemented but unverified | `App.tsx` fetches comparison series and renders selectors/chart. Backend scenario validation is tested; visual values, selection changes and error states are not verified end to end. |
| D: horizontal worker autoscaling | Unchecked | Absent | Queue locking and worker code exist; deployment text proposes N workers. No autoscaling controller/configuration or scaling experiment found. |
| D: API/ingest/analytics SLO dashboards | Unchecked | Incomplete | Metrics, Grafana throughput/latency/error panels and API/ingest/queue alerts exist. Prometheus scrapes only `backend:8000`; standalone worker counters are process-local with no worker scrape endpoint. Freshness/rejection objectives and observed SLO attainment are missing. |
| D: failover automation and postmortems | Unchecked | Incomplete | Backup/restore checklists and incident response steps exist. No disposable DB restore automation, timed drill or dedicated postmortem template found. Failed-SQL queue recovery is narrower than failover. |
| D: blue/green playbook | Unchecked | Absent | Deployment reference discusses topology, but no blue/green routing, cutover, rollback or verified compatibility procedure found. Deferred beyond the demonstration. |
| E: public hydro API connector | Unchecked | Incomplete | Generic rain/river HTTP fetchers normalize mapped JSON/CSV with timeouts and tested conversions. Examples use `example.org`; there is no verified Portuguese provider/station/license or bounded retry/pagination flow. ERA5 rainfall retrieval requires CDS credentials, derives river levels and can fall back to synthetic data. |
| E: partner adapter SDK | Unchecked | Incomplete | Shared `IngestRecord`, validators, format parsers and mapping runbook provide reusable contracts. No packaged/documented partner SDK compatibility surface, adapter conformance suite or partner-feed validation found. |
| E: audited backfill | Unchecked | Incomplete | `docs/runbooks/backfill.md` describes synthetic seeding; ingestion has import audit rows. No resumable historical source backfill with bounded windows, retries and complete audit verification found. |
| E: Kafka streaming (optional) | Unchecked | Absent | No Kafka client, consumer, service or tests found. NDJSON input is file/stdin ingestion, not a Kafka integration. Deferred beyond the demonstration. |

## CI and operational risks to carry forward

- CI has a Python 3.12 backend job with lint, mypy, unit tests and an isolated
  integration DB; web build/typecheck; container builds; seeded ingestion/export
  smoke scripts and screenshot capture. No Python test matrix currently exists.
- The backend Dockerfile uses Python 3.14, while the README and backend CI name
  3.12. CI omits `ruff format --check .` and excludes `scripts/export_openapi.py`
  from its mypy command. Actions use version tags rather than immutable SHAs.
  Failure logs/artifacts are not consistently captured with `if: always()`.
- `tests/integration/conftest.py` correctly requires an explicit test-only
  PostgreSQL name and never falls back to application `DATABASE_URL`. Alembic,
  seed, baseline and smoke scripts do not inherit that protection; only invoke
  them against explicitly disposable resources during verification.
- `seed_all.sh` forwards telemetry limits but not `CITY_IDS` or
  `ANALYTICS_PIPE_LIMIT`; CI sets the latter at the host. Check effective
  container configuration before calling the dataset small or deterministic.
- Deployment topology, per-city retention metadata, pilot targets, and proposed
  recovery objectives must not be presented as measured production properties.
- The open dependency PRs require normal review and fresh validation; their
  existence is not evidence of an applied fix or a clean security scan.

Use the [versioned roadmap](../../ROADMAP.md) to schedule the missing evidence
and implementations rather than reopening already implemented features.
