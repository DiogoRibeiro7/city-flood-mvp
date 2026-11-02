# Service objectives and observability

These are **proposed objectives**, not achieved uptime or validated municipal
service levels. Local tests establish instrumentation and query semantics only.
Use at least 30 days of representative operation, complete scrape coverage and
an agreed workload before accepting any target. Sparse historical NOAA imports
are not a continuous live telemetry feed.

## Inventory and changes

| Area | Existing behavior | Prompt 11 change |
| --- | --- | --- |
| HTTP | Counters, latency histogram, error classes and routed path templates; early quota/body/timeout responses counted | Count unexpected exceptions before propagation; bound arbitrary methods; collapse metric tenant IDs into fixed classes |
| Database | Driver query counts, latency and errors by operation | Reuse these metrics; no SQL text or new identifiers in labels |
| Ingestion | HTTP latency only | Committed event outcomes, event-to-commit delay, unusable timestamps, last insertion time and opt-in feed expectation |
| Worker | Completion/failure/retry counters updated before commit; claim wait and processing histograms with default buckets ending at 10 seconds; no scrape server | Publish outcomes after commit, add creation-to-terminal latency and progress timestamps, extend job buckets through 3600 seconds and expose a private scrape endpoint |
| Queue | Claim-time histogram cannot reveal work never claimed | Bounded read-only snapshot of due unfinished committed work, oldest age and collection health, independent of the worker |
| Monitoring | Backend-only scrape, seven dashboard panels, untested example alerts | Backend and worker targets, 20 diagnostic panels, recording rules, actionable alerts and controlled Prometheus rule tests in CI |

## Candidate SLIs and SLOs

All percentages below use a rolling **30-day** window. Dashboard five-minute
and one-hour views are diagnostics, not evidence that a 30-day target passed.
An absent series or zero denominator means **unknown/no qualifying activity**,
not 100% success. Account separately for missing scrapes; application counters
cannot observe failures before requests reach the process.

| SLI | Numerator / denominator | Proposed target and exclusions |
| --- | --- | --- |
| API availability | Non-5xx responses / all responses reaching middleware | At least 99.9%; exclude `/metrics` and `/v1/health`. Include unmatched requests and 4xx as served responses, while examining client errors separately. This is response availability, not network uptime. |
| API latency | Requests reaching response start within 0.75 s / all measured requests | At least 95%; same route exclusions. Includes upload and handler time, excludes streaming download completion and upstream proxy delay. |
| Live ingest freshness | Inserted events with aware non-future timestamps arriving within 300 s / all inserted API events | At least 95% for an agreed continuous live feed. Future/naive timestamps count against the fraction. CLI archives and synthetic seed jobs are outside API ingestion metrics. Historical API backfills require a separate workload/deployment or disabled live expectations. |
| Ingest invalid fraction | Invalid events / (accepted + invalid events) in committed new batches | Below 1%; duplicate rows excluded. Authentication, malformed whole requests and failed transactions are visible through HTTP metrics, not inferred event counts. |
| Worker claim wait | Claimed attempts within 300 s of scheduled time / all claimed attempts | At least 95%, by bounded job type. Retries are new attempts measured from their new schedule. Pair with due backlog because unclaimed jobs cannot enter a histogram. |
| Analytics timely success | Successfully completed analytics jobs within 300 s of creation / terminal analytics jobs (completed + failed) | At least 95%; includes retries, processing and intentional scheduled delays. Cancelled and unfinished jobs are excluded; backlog/progress alerts address jobs that never finish. Direct CLI analytics and scheduler omissions are outside this SLI. |

The initial values are review candidates, chosen to make slow requests, five-minute
queues and stale live telemetry visible. They are not calibrated to operational
traffic or hydrological warning needs. A 99.9% request-success target allows a
0.1% bad-request fraction; it does not imply a monthly downtime allowance unless
a time-based external availability SLI is also defined.

To calculate the candidates, use `increase(...[30d])` on the matching counters
and buckets; aggregate **after** increase/rate so each process reset is handled.
For example, the exact analytics ratio is:

```promql
sum(increase(job_completion_latency_seconds_bucket{job="floodmvp-worker",job_type="analytics_run",outcome="completed",le="300.0"}[30d]))
/
sum(increase(job_completion_latency_seconds_count{job="floodmvp-worker",job_type="analytics_run"}[30d]))
```

For claim wait, divide `job_queue_age_seconds_bucket{le="300.0"}` increases by
`job_queue_age_seconds_count` increases, grouped by `job_type`. For the API and
ingest candidates, use the selectors in `infra/observability/alerts.yml` with
30-day increases. Use the HTTP request counter, not an error-only series, for
availability denominators. The recording rules handle an absent zero-error
series without converting an absent request stream into success.
Pre-routing rejections have the fixed `<unmatched>` label, so they remain in
these denominators even when the rejected raw URL was a probe; only matched
probe routes can be excluded by the existing path-template instrumentation.

## Metric semantics and boundaries

`GET /metrics` exports the API process registry plus its queue snapshot. The
worker serves its own registry on port 9101. Prometheus's `job` and `instance`
labels distinguish targets: worker outcomes must be selected from
`job="floodmvp-worker"`, and API ingestion from `job="floodmvp-backend"`.
Both processes import the shared registry; zero-valued series on the other
process are not additional evidence. The scheduler's registry is not scraped.

New series:

| Metric | Meaning |
| --- | --- |
| `ingest_events_total{outcome}` | `accepted`, `duplicate` or `invalid` events after a successful non-replayed API batch commit |
| `ingest_event_delay_seconds` | Histogram of commit time minus accepted event timestamp; aware non-future timestamps only, with a 300 s bucket |
| `ingest_timestamp_anomalies_total{reason}` | Accepted `future` or `naive` timestamps; never silently clamped to fresh |
| `ingest_last_commit_timestamp_seconds` | Last commit inserting at least one API event in this process; zero before the first insertion |
| `ingest_expected_active` | Operator-controlled live-feed expectation; default false |
| `job_completion_latency_seconds{job_type,outcome}` | Creation through observed terminal commit, with `completed` or `failed` outcome and a 300 s bucket |
| `job_last_success_timestamp_seconds{job_type}` | Worker-observed last committed success; absent before first success and reset on restart |
| `worker_last_poll_timestamp_seconds` | Last successful committed idle poll or finished attempt; an independently responding metrics thread does not imply progress |
| `job_queue_due_jobs{job_type}` | Committed queued/running rows whose scheduled time has arrived; future schedules and terminal states excluded |
| `job_queue_oldest_due_age_seconds{job_type}` | Oldest due unfinished scheduled-time age, zero only after a successful empty snapshot |
| `job_queue_collection_success` | One for the latest successful snapshot, zero on query failure |
| `job_queue_collection_timestamp_seconds` | Last successful snapshot time; stale values are not fresh observations |

Ingestion idempotency replays do not increment event counters or reset arrival
time. A duplicate-only or invalid-only committed batch contributes its outcomes
but does not refresh last insertion. Whole-transaction failures publish no event
results. Future event timestamps remain accepted according to the existing API
contract, but cannot improve the freshness numerator. `sent_at` is not used to
substitute for event time.

Worker completion/failure/retry counters now update only after commit. The
existing `job_queue_enqueued_total` counts flushed enqueue calls and can include
rolled-back transactions; it is **not** a durable completion denominator. The
claim and processing histograms describe attempts, including rolled-back work.
There is still a small crash window between DB commit and metric publication:
these process counters are monitoring signals, not a durable audit ledger.

The worker retains its transaction and row lock throughout execution. A separate
reader may therefore see an actively processed job as still queued. The snapshot
intentionally describes **due unfinished work**, not a precise runnable-only
queue or an in-flight worker count. Retries move the schedule forward; future
retry delays are excluded until due. Each snapshot uses a two-second total query
deadline and a 1.5-second PostgreSQL statement timeout. Failure retains old values
but marks them unusable; rules/panels require success and a timestamp younger than
60 seconds. Multiple API replicas see the same DB: use max/individual instances,
not a sum of duplicated backlog snapshots.

Labels never include device, city, job, request or tenant IDs, URLs with concrete
IDs, event metric names, payloads or exception messages. Job types are restricted
to `analytics_run`, `export_csv`, `report_csv` and `other`. HTTP methods use a fixed
allowlist plus `OTHER`; routed paths remain templates and pre-routing rejections
use `<unmatched>`. Legacy `http_requests_tenant_*` names are retained, but `tenant`
now contains only `public`, `analytics-key` or `authenticated`. Existing dashboards
that selected a real tenant ID must migrate to these aggregate classes. Quota
identity and the logged tenant identity are unchanged.

This is an **operator aggregate view**, not tenant-isolated reporting. Metrics
endpoints have no application authentication; keep API `/metrics`, worker 9101,
Prometheus and Grafana on trusted networks or behind authenticated operator ingress.
The worker binds loopback by default; Compose sets its private container interface
without publishing a host port. These metrics do not establish row-level tenant
authorization. Use one API process per scraped target; unconfigured multiprocess
Python registries behind one endpoint cannot provide reliable aggregate counters.

## Run and inspect

After configuring the ordinary application environment and preparing the database:

```sh
docker compose up -d db backend
docker compose exec -T backend alembic upgrade head
docker compose up -d --build worker prometheus grafana
```

This starts a consumer, not the periodic scheduler. Enqueue work through existing
API routes or run the documented scheduler separately. The default Compose file
shares the exports volume between API and worker. The base Prometheus service
retains data for 35 days in `prometheus_data`; a new or deleted volume cannot
supply a complete 30-day evaluation. The disposable smoke stack remains ephemeral.

For a continuous expected API feed, set `INGEST_EXPECTED_ACTIVE=true` and recreate
the backend. Leave it false for demonstrations, backfills or intermittent feeds.
Silence monitoring uses the latest insertion/startup time with a ten-minute grace
and five-minute hold; startup does not fabricate an observed insertion timestamp.
One active producer can mask another silent producer because this is aggregate
monitoring, not per-device coverage.

Grafana remains at `http://localhost:3000` with the repository's local demo
credentials (`admin` / `admin`). Open **FloodMVP Service Objectives (proposed)**
(existing dashboard UID `floodmvp-api`). Start with scrape/collection health,
then request/ingest outcomes, queue age, worker progress and DB diagnostics.
No-data panels must remain unknown; do not configure them to display 100% success.
The last-success graph is not a guarantee that every configured city was analyzed.

## Alert response

Rules in `infra/observability/alerts.yml` are examples, not achieved SLOs or a
complete error-budget paging policy. Alertmanager routing is not configured here;
`page`/`ticket` labels express proposed urgency and do not send notifications.

| Alert | Trigger / hold | First action |
| --- | --- | --- |
| `MetricsTargetDown` | Missing or failed API/worker scrape / 2 min | Check process, endpoint and private network before interpreting other graphs |
| `ApiHigh5xxRate` | More than 2% 5xx in 5 min, over 100 requests / 10 min | Correlate request IDs, exception logs and DB errors |
| `ApiLatencyP95High` | Fewer than 95% within 750 ms in 5 min, over 100 requests / 10 min | Inspect route latency, DB operations and saturation; response-start only |
| `IngestInvalidFractionHigh` | More than 1% invalid in 5 min, over 100 nonduplicate results / 10 min | Fix producer validation; inspect whole-request errors separately |
| `IngestFreshnessLow` | Fewer than 95% within 300 s, over 100 inserted events in 5 min, live expectation enabled / 10 min | Check timestamps, producer clocks and buffering; confirm this is not a backfill |
| `IngestNoArrivals` | No insertion for 10 min after last insertion/startup, expectation enabled / 5 min | Check producer connectivity, duplicates and rejection counters |
| `QueueSnapshotUnavailable` | Failed collection or last good sample older than 60 s / 2 min | Check DB connectivity and statement timeout; cached values are unusable |
| `DueJobAgeHigh` | Fresh snapshot contains due unfinished work older than 300 s / 5 min | Check worker progress, active jobs and retries; do not blindly requeue locked work |
| `WorkerPollStalled` | No successful poll/attempt completion for 300 s / 5 min | Inspect current handler and DB locks even if the metrics server responds |
| `AnalyticsCompletionLow` | Fewer than 95% terminal analytics jobs succeed within 300 s in 1 h, at least 10 terminal jobs / 10 min | Inspect failures and retry history alongside unfinished backlog |

Ratio guards reduce low-volume noise; they do not establish statistical confidence.
Zero traffic should lead to source/scheduler expectation checks, not a success
claim. Read-only triage comes first; recovery and backup drills belong to prompt 12.

## Verification

```sh
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src scripts/export_openapi.py scripts/smoke_stack.py
poetry run pytest -q tests/unit
poetry run pytest -q tests/integration
poetry run python -m scripts.smoke_stack --artifacts test-results/observability-smoke
```

Integration tests require the [guarded disposable test database](migrations.md),
never an application database. The smoke runner owns a separate Compose project,
checks real API and worker scrapes, observes committed analytics completion in
Prometheus, submits every dashboard query and removes its resources. These checks
do not measure 30-day uptime or real feed freshness. New unit/integration cases
cover commit failure, idempotency replay, timestamp anomalies, bounded labels,
queue filters, failed collection and unexpected HTTP exceptions.

Run Prometheus rule checks on an existing monitoring container:

```sh
docker compose exec -T prometheus promtool check rules /etc/prometheus/alerts.yml
```

CI additionally runs `promtool test rules` against
`tests/observability/alerts.test.yml` using the configured Prometheus 2.53 image
and a read-only repository mount. The fixtures are controlled synthetic series;
they test predicates, missing/low traffic, probe exclusion, worker outages,
failed snapshots, live-feed opt-in and analytics terminal outcomes.

Design references: [Prometheus instrumentation guidance](https://prometheus.io/docs/practices/instrumentation/)
explains bounded labels and timestamp gauges;
[the Python client's HTTP exporter](https://prometheus.github.io/client_python/exporting/http/)
documents the worker's metrics server and shutdown lifecycle. Local source,
tests and retained command outcomes remain the evidence for this implementation.

## Observed local verification — 2026-11-02

Base: merged prompt 10 at `4fcccfc0c897e358844def0712264fe26c726b29`.
Host checks used Python 3.12.10 / Poetry 2.2.1 on Windows; the stack used the
repository's Python 3.14 backend Dockerfile and Prometheus 2.53.0. No application
database or unrelated Docker resource was reset.

| Check | Observed result |
| --- | --- |
| Ruff lint / format | Passed; 166 files already formatted |
| Mypy including the smoke runner | Passed; 78 source files |
| Full unit suite | 494 passed, three existing POSIX permission cases skipped on Windows; existing Alembic `path_separator` deprecation warning |
| Full PostgreSQL integration suite | 45 passed on an owned disposable server; cleanup recorded as removed |
| Prometheus configuration and rules | Config valid; all 17 recording/alert rules valid |
| Prometheus controlled rule tests | All ten scenarios passed, including explicit zero-traffic unknown semantics |
| Compose config / actionlint | Passed against `.env.example`; monitoring CI step validated |
| Full-stack smoke | Passed; API/worker targets healthy, Prometheus observed `job_queue_completed_total{job_type="analytics_run"}=1`, and all targets in the 20-panel dashboard executed successfully |
| Existing smoke regressions | Seed replay, exact CSV export, scheduled analytics, ingestion replay/concurrency and SQL-failure recovery all passed |
| Cleanup | Smoke containers, volumes, network and generated image tags removed; no owned containers remained |
| Browser dashboard rendering / separate web typecheck and production build | Not run; web source unchanged. Smoke checked serving and API configuration, not browser interactions |
| Hosted CI / operational SLO attainment / measured recovery objectives | Not established by these local checks |

The actual smoke project was `city-flood-smoke-657bb77c983e`; its result recorded
569.485 seconds including an initial image build. That elapsed time is not a
service latency benchmark or recovery measurement. Local ignored evidence is in
`test-results/service-objectives-smoke/city-flood-smoke-657bb77c983e/`:
`result.json`, `prometheus-targets.json`, `prometheus-completion.json`, command
logs and service diagnostics. Unit and DB JUnit files are
`test-results/service-objectives-unit.xml` and
`test-results/service-objectives-db/results.xml`. No operational workload or
30-day scrape history was collected; every SLO value above remains proposed.
