# Disposable full-stack smoke test

Run from the repository root with **Python 3.12+**, Docker running Linux
containers, and Docker Compose v2 or newer. No application stack, `.env`, host
Poetry environment, Node installation or credentials need to be pre-started or
configured. The first run downloads/builds the images used by the documented
stack and needs network access and several minutes of build time.

```text
python -m scripts.smoke_stack
```

The command returns 0 only when all checks pass and automatic cleanup succeeds.
It returns 1 on assertion, readiness, build, command or cleanup failure. Use
`poetry run python -m scripts.smoke_stack` if Poetry selects your Python 3.12
interpreter. The host runner itself uses only the standard library.

## What it verifies

1. Build the existing backend and web Dockerfiles. A dedicated
   `docker-compose.smoke.yml` reuses the documented TimescaleDB, Prometheus and
   Grafana images/configuration and adds separate worker/scheduler services.
2. Start a new test database, poll readiness, enable extensions through the
   existing init script, and run `alembic upgrade head`.
3. Seed one synthetic Porto city, three fixed assets and 36 five-minute
   measurements over **2026-01-01 00:00-01:00 UTC**. Seed twice and check exact
   stored values/counts to prove replay does not duplicate input. Run the
   existing analytics code over that fixed interval.
4. Start API, worker, web, Prometheus and Grafana. Poll their HTTP readiness and
   check that Vite serves the actual randomly assigned API address. Query cities,
   assets, observations, events, city status and summary; assert exact rainfall
   observations and the presence of synthetic rain/overflow events.
5. Queue a CSV export over HTTP. A **separate worker container** must complete
   it before the deadline. Download the CSV through the API and compare all 12
   rainfall rows, timestamps and values with the fixed fixture. The API and
   worker share only this project's disposable export volume.
6. Start the scheduler after the fixed-window assertions and verify that its
   queued analytics job completes. This step uses the scheduler's current-time
   window, which may contain no fixture observations; it verifies scheduling and
   execution, not current hydrological coverage or detector accuracy.
7. Stop the scheduler/worker consumers, then run the existing ingestion
   authentication/replay/concurrency and export/report SQL-failure regression
   scripts in the backend. The export script drives its own worker, avoiding
   competing consumers during its failure/retry assertions.
8. Save diagnostics and remove this run's containers, networks, data/export
   volumes and two built image tags. Shared base images remain cached.

This smoke checks web serving/configuration, not rendered browser interaction
or accessibility. It does not prove real-data validity, migration/model
equivalence, recovery objectives or tenant isolation. The synthetic inputs and
CSV are deterministic; generated job/run IDs and operational timestamps are not.

## Isolation and safe reruns

Every invocation generates a new `city-flood-smoke-<random-id>` project and
rejects a project that already has containers (including stopped ones), volumes
or networks. No existing Compose project is adopted or reset. The test DB is
`floodmvp_smoke_test`, is reachable only inside its project network, and has no
published host port or host data-directory mount. API/web/monitoring ports are
random and bound to `127.0.0.1`.

The runner supplies an explicit generated `compose.env`, clears inherited
`COMPOSE_*` configuration, and pins all database/ingestion settings in the smoke
Compose file. It never reads the application's `.env` or falls back to an
application `DATABASE_URL`. The seeder separately requires `APP_ENV=test`, a
valid generated smoke project ID, host `db` and the exact smoke database name.
It uses conflict-safe fixture inserts, never table deletion or the demo resetter,
and rejects unexpected/changed data. Test credentials are local throwaway values.

The older `seed_all.sh`, `smoke_ingest_idempotency.py` and `smoke_export_jobs.py`
remain available for their existing seeded-stack checks. This runner supplies
the missing isolated lifecycle and deterministic fixture. It does not call the
ingestion smoke's current-time/random-input generator or the export smoke's
in-process worker; their broader regression coverage remains in normal CI.

## Results and failure diagnosis

Each run prints its artifact directory under `test-results/smoke/<project>/`:

- `result.json`: status, failed/current phase, fixture version/hash, seed counts,
  checks completed, job ID, endpoints, elapsed time and cleanup result.
- `commands.log`: exact Docker arguments, captured output and exit codes.
- `services.log`, `services.json`, `images.json`: bounded service logs, service
  state and image inventory, captured before cleanup.
- `export.csv`: the successfully verified synthetic export, when reached.
- `compose.env`: this run's project and discovered API address, for inspection.

Readiness uses bounded polls, not a fixed startup sleep. Defaults are 120 seconds
per service, 60 seconds per queued job, 1,200 seconds for image builds, and
bounded Docker command timeouts. Individual HTTP attempts time out after five
seconds. The error includes the failed phase and last observed state/response.

Exercise a real failure by stopping the worker immediately before enqueueing:

```text
python -m scripts.smoke_stack --inject-failure worker --job-timeout 5
```

Expected: **exit 1**, phase `export`, `Timed out waiting for export job completion`,
and `cleanup: completed`. A failure in an earlier phase is not proof that this
negative test passed. Inspect the JSON report to distinguish it.

For troubleshooting, retain only that invocation's resources:

```text
python -m scripts.smoke_stack --keep
```

Use the exact cleanup command printed by the runner (`docker compose` with the
explicit project, smoke file and generated env file, followed by
`down --volumes --remove-orphans`). Run it from the same shell context without
overriding `SMOKE_PROJECT` or `SMOKE_API_BASE`. Do not use a bare application
`docker compose down -v` or a global Docker prune. If necessary, remove only the
two image tags `<printed-project>-backend` and `<printed-project>-web` afterward.
Ctrl+C/SIGTERM attempts normal diagnostics and cleanup; a machine crash or force
kill may require the same manual cleanup.

## CI and focused tests

The **Disposable full-stack smoke** workflow is shared through `workflow_call`
and `workflow_dispatch`. Required PR CI calls its positive path, replacing the
previous build/image-transfer/screenshot chain. A manual run defaults to both
the success and stopped-worker negative paths, checking the precise failure
phase and cleanup status. Both modes retain artifacts even on failure.

```text
poetry run pytest -q tests/unit/test_smoke_stack.py
poetry run pytest -q tests/integration/test_smoke_seed.py
```

The second command still requires the repository's separate disposable
`TEST_DATABASE_URL`; never use an application DB. Tests cover database/project
safeguards, deterministic seed replay and preservation of unexpected data,
readiness polling/deadlines, terminal job failures, CSV content, command-timeout
logs, and cleanup ownership/error paths.

## Observed local verification (2026-10-30)

The table below is the original prompt 2 record. Prompt 5 changes the web image
to Node 24 and adds the retained regression scripts; its new positive/negative
results are recorded in the [candidate checklist](../releases/rc-checklist.md).

Executed on Windows with Python 3.12.10, Docker server 29.8.2 and Compose 5.6.0.
The container builds used the existing Python 3.14 and Node 25 Dockerfiles;
host web checks used Node 24.19.0 and project-pinned Yarn 4.1.1. These results
are local evidence, not a claim about GitHub Actions or all supported hosts.

| Check | Actual result |
| --- | --- |
| `poetry run python -m scripts.smoke_stack` | Passed, including seed replay, exact API observations, export/download, scheduler handoff and cleanup. Report: `test-results/smoke/city-flood-smoke-44cd60047cc4/result.json`. |
| `poetry run python -m scripts.smoke_stack --artifacts test-results/smoke-repeat` | Passed again. Report: `test-results/smoke-repeat/city-flood-smoke-aa5ee63a9852/result.json`. Both successful exports have SHA-256 `406cecee2cd39db72b75632e08468a10d5ea64b151acaf81d832b57da6fb0c86`. |
| `poetry run python -m scripts.smoke_stack --inject-failure worker --job-timeout 5 --artifacts test-results/smoke-negative` | Expected exit 1 in phase `export`, with the last job state `queued` and cleanup completed. Report: `test-results/smoke-negative/city-flood-smoke-bc08f4a8c154/result.json`. No containers, volumes or networks remained for any of these three project IDs. |
| `poetry run pytest -q tests/unit --junitxml=test-results/smoke-unit.xml` | 319 passed. |
| `poetry run pytest -q tests/integration --junitxml=test-results/smoke-integration.xml` | 34 passed against a separate disposable test DB, including fixture replay and scheduler city scoping/recent-run checks. Test container removed afterward. |
| `poetry run ruff check .` | Passed. |
| `poetry run mypy src scripts/export_openapi.py scripts/smoke_stack.py scripts/seed_smoke.py scripts/smoke_fixture.py` | Passed: 71 source files. |
| `poetry run ruff format --check .` | Existing baseline failure: 53 files need formatting. All eight added/modified Python files pass their focused format check. |
| `corepack yarn typecheck` and `corepack yarn build --outDir ../test-results/smoke-web-dist` in `web/` | Passed; existing build warnings about the large JS chunk, plugin timings and output outside the web directory remain. |
| Compose/workflow validation | `docker compose config --format json` passed; inspected all published ports and DB settings for isolation. Parsed the dispatch-only workflow and compiled its Python step. The new GitHub workflow was not dispatched. |

The first end-to-end run exposed a pre-existing scheduler crash before enqueue:
the generic SQLAlchemy JSON field did not support `.astext`. The scheduler now
uses `.as_string()`, with PostgreSQL tests covering queued/running jobs for the
same versus different cities and recent completed analytics. The successful
runs above include that fix. No public API or OpenAPI contract changed.

Artifacts are local, ignored outputs rather than committed datasets or CI
results. Re-run the command on the release candidate and retain its reports.
