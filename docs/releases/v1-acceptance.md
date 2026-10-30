# v1 demonstration acceptance gates

This is an evidence checklist for `v0.9.0-rc1` and `v1.0.0`, not a release
approval. The target is a reproducible flood monitoring demonstration. It makes
no municipal production, calibrated prediction, uptime, or compliance claim.
The [implementation audit](implementation-audit.md) records inspected behavior;
the [roadmap](../../ROADMAP.md) assigns the remaining work.

## Observable gates

All applicable gates must pass on the candidate revision for v1. A failure,
missing artifact or skipped prerequisite keeps its gate open. For the synthetic
RC, require G1-G4 and G6 within an explicitly documented local/single-tenant
scope; carry the other gates forward as visible limitations.

| Gate | Required observation and retained evidence | Current disposition / follow-up |
| --- | --- | --- |
| G1: clean installation and static checks | Fresh locked Python/web installs; identified supported Python/Node versions; successful container builds, `ruff check`, `ruff format --check`, mypy including the OpenAPI exporter, web typecheck and build. Record tool versions, lock hashes and logs. | Open: local installs/lint/types/web checks pass, and the smoke follow-up verifies container builds. Formatting still fails in 52 existing Python files after prompt 3 (53 at baseline). CI uses Python 3.12 while the backend image uses 3.14; supported runtime/CI versions still need reconciliation. Prompt 5. |
| G2: isolated migrations and data integrity | Test harness rejects application/non-test names. Fresh PostGIS/Timescale DB reaches the single Alembic head; a second upgrade is a no-op. Assert expected extensions, hypertables, constraints/indexes, foreign keys and UTC timestamps against models. Upgrade representative seeded data without loss; document locking and manual steps. | Open: safety tests, manual migration from zero and repeat upgrade pass. Automated migration/model consistency and seeded-upgrade evidence are still missing; integration table recreation does not exercise the revision chain. Prompt 4. |
| G3: seeded end-to-end workflow | A single documented command provisions or verifies isolated prerequisites, waits with bounded polls, migrates, seeds a fixed small dataset, checks API/web readiness and key endpoints, queues an export, observes a terminal success and validates its CSV. A rerun succeeds without duplicate data. An induced failure returns nonzero with useful logs; cleanup removes only that run's resources. | Local verification passed in prompt 2: `python -m scripts.smoke_stack` uses a separate Compose stack, fixed input, actual worker/scheduler containers, failure diagnostics and cleanup. Two successful runs produced identical CSV; stopped-worker failure behaved as expected. See the [smoke evidence](../runbooks/smoke.md#observed-local-verification-2026-10-30); repeat on the reviewed candidate. |
| G4: API contract | Passing unit/integration suites and live public-schema comparison; error envelopes/status codes, malformed input, pagination/filter boundaries, timestamps and scenarios have documented assertions. Any changed contract has a regenerated snapshot and compatibility explanation. | Partial: the [prompt 3 contract audit](api-contract-audit.md) fixes validation 400/schema alignment, malformed-input crashes, and job UTC handling; 350 unit and 38 PostgreSQL tests plus full-stack smoke pass. Pagination/filter assertions are expanded. CSV media types, auth/error declarations, and pagination ties remain documented follow-ups. |
| G5: validated real-data experiment | Primary-source evidence for reuse terms, source/station IDs, units, time zone, cadence, retrieval window and gaps; selected Portuguese source; reproducible ingestion with provenance/deduplication; measured quality report distinguishing missing values from observed zero. Independent labels and matching rules precede accuracy scores; otherwise explicitly descriptive results. | Open: source assessment, dataset, observed quality report and case study are absent. Generic HTTP adapters and ERA5-assisted synthetic generation are insufficient. Prompts 6-10. |
| G6: security boundary | Passing privileged-role, unsafe-ingest-token, spoofed-header, CORS and request-limit tests; no secrets in source or web bundle; dependency review/scan results recorded. Prove cross-tenant denial for any tenant-hosting claim, or document a single-tenant boundary. Prove quota semantics across API processes or enforce/document a single-worker constraint. | Open: focused security regressions pass. Tenant attribution is not row authorization; quotas are process-local; no complete dependency scan or deployment security review was run. Prompts 5 and 13. |
| G7: observability and recovery | Verify API/ingest freshness/rejection/worker queue/completion metric semantics and scrape targets, alert rule validation and dashboard queries. In disposable resources, record DB backup/restore consistency, worker interruption/retry/stale-job handling and measured recovery/data-loss intervals against explicitly proposed RTO/RPO. | Open: metrics/alerts and runbooks exist, but worker scraping and a measured backup/restore drill are missing. Targets are not achieved service levels. Prompts 11-12. |
| G8: operator evidence workflow | Browser assertions take an observation through quality flags, event explanation, underlying measurements, notes, scenario comparison and export; cover errors and keyboard/accessibility behavior. Synthetic and real sources and uncertainty are visible. Any screenshots come from the tested revision and functioning stack. | Open: UI paths exist; build/typecheck and screenshot capture do not verify the complete flow. Prompt 14. |
| G9: reproducibility and release provenance | One command regenerates the historical report/tables/figures with recorded code revision, config, fixed window, seed, source version/retrieval date and checksums. Another clean environment reproduces outputs within declared tolerances. Final checklist records all gates/results/skips, version/changelog and accurate citation/author metadata. | Open: no complete case study/reproduction path or release provenance. Poetry author metadata is a placeholder. Prompts 10 and 15. |

## Commands available now

Run from the repository root after selecting the candidate revision. Record
stdout/stderr and exit status for each command; do not infer success from CI
configuration or a badge. Use Python 3.12 for the existing backend CI baseline.

```text
poetry env use <absolute-path-to-python-3.12>
poetry install --no-interaction --no-ansi
poetry run python --version
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src scripts/export_openapi.py
poetry run pytest -q tests/unit --junitxml=test-results/readiness-unit.xml
poetry run pytest -q tests/integration/test_database_safety.py
poetry run alembic heads
poetry run alembic history
```

`tests/unit/test_public_openapi_export.py` checks the committed schema against
the live generated schema; it runs in the unit suite without changing files.
After an intentional API change, regenerate with
`poetry run python scripts/export_openapi.py`, review the snapshot diff and
rerun that test. A documentation-only audit should not regenerate it needlessly.

From `web/`, use the project-pinned package manager:

```text
node --version
corepack yarn --version
corepack yarn install --immutable
corepack yarn typecheck
corepack yarn build --outDir ../test-results/readiness-web-dist
```

The output override keeps generated files under ignored `test-results/`.
The actual audit used Node 24.19.0 and Yarn 4.1.1; it does not substitute for
running the Node 20 environment configured in CI.

### Disposable PostgreSQL integration checks

The fixture in `tests/integration/conftest.py` recreates application tables.
Use a new test-only container, no host data mounts, and a database named
`floodmvp_test`. Do not reuse a demo/application database just because its name
can be changed. Docker must be running in Linux-container mode.

Example PowerShell setup (the name is intentionally specific; an existing
container with that name should make setup fail, not be replaced):

```powershell
docker run --rm -d --name city-flood-readiness-db-20261030 `
  --label city-flood-purpose=readiness-audit `
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=readiness-test-only `
  -e POSTGRES_DB=floodmvp_test -p 127.0.0.1::5432 `
  timescale/timescaledb-ha:pg16.11-ts2.25.0-all-oss
if ($LASTEXITCODE -ne 0) { throw 'Test database creation failed' }
$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
  docker exec city-flood-readiness-db-20261030 pg_isready -U postgres -d floodmvp_test
  if ($LASTEXITCODE -eq 0) { $ready = $true; break }
  Start-Sleep -Seconds 2
}
if (-not $ready) { throw 'Test database readiness timed out' }
$binding = docker port city-flood-readiness-db-20261030 5432/tcp
if ($LASTEXITCODE -ne 0 -or $binding -notmatch '^127\.0\.0\.1:(\d+)$') {
  throw 'Expected a single loopback-only PostgreSQL port binding'
}
$testPort = $Matches[1]
$env:TEST_DATABASE_URL = "postgresql+asyncpg://postgres:readiness-test-only@127.0.0.1:$testPort/floodmvp_test"
poetry run pytest -q tests/integration --junitxml=test-results/readiness-integration.xml
```

Capture the pytest exit code immediately. This verifies ORM-backed behavior,
not migrations. In this audit no application `DATABASE_URL` was used for tests.
After recording results, stop only the container created for the audit (Docker
`--rm` also removes its anonymous volumes):

```powershell
docker inspect --format '{{index .Config.Labels "city-flood-purpose"}}' city-flood-readiness-db-20261030
# Verify the result is readiness-audit and this is the container you created.
docker stop city-flood-readiness-db-20261030
Remove-Item Env:TEST_DATABASE_URL -ErrorAction SilentlyContinue
```

### Migration and smoke follow-up

Migration verification must use a separate fresh disposable database, not the
one whose tables the integration fixture recreates. The audit ran the following
in the same disposable container **before cleanup**, using the loopback port
resolved above. Stop at any nonzero command exit; never replace the explicit
test database name with an application database.

```powershell
docker exec city-flood-readiness-db-20261030 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -c 'CREATE DATABASE floodmvp_migrations_test'
Get-Content -Raw infra/db/init.sql | docker exec -i city-flood-readiness-db-20261030 psql -U postgres -d floodmvp_migrations_test -v ON_ERROR_STOP=1
$env:DATABASE_URL = "postgresql+psycopg2://postgres:readiness-test-only@127.0.0.1:$testPort/floodmvp_migrations_test"
poetry run alembic upgrade head
poetry run alembic current
poetry run alembic upgrade head
docker exec city-flood-readiness-db-20261030 psql -U postgres -d floodmvp_migrations_test -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM alembic_version; SELECT extname, extversion FROM pg_extension ORDER BY extname; SELECT hypertable_schema, hypertable_name FROM timescaledb_information.hypertables;'
```

Run this in a dedicated shell so the temporary `DATABASE_URL` does not replace
settings used for other work. Alembic currently has an application-database
fallback and does not enforce the test-name guard; a safe automated harness,
schema assertions and an upgrade over seeded data remain prompt 4 work.

Existing stack verification components, **only against a separately provisioned
disposable Compose project**, are:

```text
bash ./scripts/seed_all.sh
docker compose exec -T backend python /app/scripts/smoke_ingest_idempotency.py
docker compose exec -T backend python /app/scripts/smoke_export_jobs.py
```

They require configured database/ingestion credentials, a ready API and seeded
measurements; the export script runs the queue worker itself. They mutate data
and do not themselves provide deterministic isolation/cleanup. Do not run them
against an application stack to fill an evidence gap. Prompt 2 adds the complete
entry point `python -m scripts.smoke_stack`; see its [runbook](../runbooks/smoke.md)
for actual success/failure-path results and cleanup instructions.

No real-data reproduction, full browser acceptance, backup/restore drill, or
release-publication command is claimed to exist here. Define and execute those
commands in the corresponding later work before closing their gates.

## Baseline verification record

Audit date: 2026-10-30, Windows/PowerShell, Python 3.12.10, Poetry 2.2.1,
Node 24.19.0, project-pinned Yarn 4.1.1, Docker server 29.8.2; baseline code
`5b4a600b1c4e73638284b54113de53e3339f7ca2`. Changes in this PR are documentation
only. Generated JUnit/build files are local ignored artifacts, not committed
release evidence. A fresh CI run must be linked separately; local checks are
not a claim about GitHub Actions results. Local Poetry/Node versions differ
from CI's Poetry 1.8.4/Node 20; those exact CI environments were not run locally.

Locked input SHA-256 values:

- `poetry.lock`: `6b0dbd2c39ddda89cb816b814119b282843fcea5ad456320c52610d1119a229f`
- `web/yarn.lock`: `1e9d6c27116d4f4a79bc739f0ffe24b758005e02a02bcf40b1c5de9ca61d2e4b`
- Test DB image `timescale/timescaledb-ha:pg16.11-ts2.25.0-all-oss`:
  `sha256:1cb0764fb549213391fb5a96822b3e143da5bd72c108e5e07f5d721eddf65af9`

| Command/check | Observed result |
| --- | --- |
| Python 3.12 environment + `poetry install --no-interaction --no-ansi` | Passed; fresh isolated environment installed locked dependencies and the project. |
| `poetry run ruff check .` | Exit 0, all checks passed; existing cache writes on G: emitted access-denied warnings. |
| `poetry run ruff format --check .` | Exit 1: 53 files would be reformatted, 80 already formatted. Pre-existing baseline issue; no code formatting changes made. |
| `poetry run mypy src scripts/export_openapi.py` | Exit 0: no issues in 68 source files. |
| `poetry run pytest -q tests/unit --junitxml=test-results/readiness-unit.xml` | Exit 0: 300 passed in 49.03 seconds, including live public-schema and security assertions. |
| `poetry run pytest -q tests/integration/test_database_safety.py --junitxml=test-results/readiness-db-safety.xml` | Exit 0: 7 passed in 0.50 seconds, including rejection of application names and absence of fallback to `DATABASE_URL`. These seven tests also run in the full integration suite below. |
| `poetry run pytest -q tests/integration --junitxml=test-results/readiness-integration.xml` | Exit 0: 29 passed in 18.91 seconds against `floodmvp_test` in the new loopback-only disposable container. No skipped tests. |
| `poetry run alembic heads` / `poetry run alembic history` | Exit 0; one head `0018_ingest_expiry`, 18 revisions in one chain. Graph inspection alone is not an upgrade test. |
| Separate `floodmvp_migrations_test`: extension init, `alembic upgrade head`, `alembic current`, repeated `alembic upgrade head` | All exit 0. All 18 revisions applied; current is `0018_ingest_expiry`; repeat upgrade emitted no revision operations. Local migration log: `test-results/readiness-migrations.log`. |
| SQL inspection of migrated DB | Confirmed current revision, TimescaleDB 2.25.0, PostGIS 3.6.1, `pg_trgm` 1.6, `uuid-ossp` 1.1, and the `public.telemetry_observation` hypertable. Full schema equivalence/seeded upgrade was not tested. |
| `corepack yarn install --immutable` (in `web/`) | Exit 0 with Yarn's optional TypeScript patch warning `YN0066`. Lockfile unchanged. |
| `corepack yarn typecheck` (in `web/`) | Exit 0. |
| `corepack yarn build --outDir ../test-results/readiness-web-dist` | Exit 0; 616 modules transformed. Warnings: output outside web root is not emptied, plugin timings, and JS chunk over 500 kB (721.20 kB). |
| Documentation review | `git diff --check` passed; checked eight edited Markdown files, all 16 relative links/anchors and reconciliation of all 20 historical roadmap items. |
| Disposable resource cleanup | Verified the audit label and exact created container ID before stopping it. Docker removed the container; no application containers/volumes were changed. |
| GitHub dependency alert summary on branch push | GitHub reported 99 vulnerabilities on the default branch: 4 critical, 39 high, 47 moderate and 9 low. This is the remote push summary, not an independently executed scan or triaged finding set; review the repository's dependency alerts before closing G6. |
| Full Compose build/seed/smokes, UI interactions/screenshots, real source access, dependency security scan, recovery drill | Not run in this documentation audit. Their component code/configuration was inspected; no passing result, screenshot, benchmark or observed dataset metric is asserted. |

## Outstanding release decision

**No-go for either release.** Formatting is a known failure and supported-runtime,
migration/model-consistency and security evidence remain incomplete. The prompt
2 smoke follow-up supplies local full-stack evidence, but real-data,
operator-workflow and recovery evidence are additional v1 blockers. The baseline
table above remains the original prompt 1 record; later smoke outcomes are
recorded separately in the linked runbook.

Prompt 3 depends on review and merge of the prompt 2 smoke-test PR into the
current integration branch. Do not merge automatically or continue from an
assumed merge. After each predecessor is merged, fetch and re-evaluate changed
code, tests, open PRs and these gate results before continuing.
