# v0.9.0-rc1 candidate checklist

This prepares an auditable synthetic demonstration candidate. It does not
authorize a tag or publication. Current package/API metadata remains 0.1.0.
Read the [version policy](version-policy.md), [acceptance gates](v1-acceptance.md),
[API audit](api-contract-audit.md) and [migration runbook](../runbooks/migrations.md).

## Candidate record

Complete these fields for the exact reviewed commit. A previous run's success
does not establish a result for a newer SHA.

| Field | Record |
| --- | --- |
| Proposed version | v0.9.0-rc1, unreleased |
| Source SHA and clean tree | Pending reviewed candidate |
| Python/web/API version alignment | Pending candidate metadata change |
| Runtime/tool versions and OS | Attach output from each job |
| Lock hashes and image IDs/digests | Attach manifest and image inspection |
| Alembic head and upgrade prerequisites | Attach migration evidence/preflight review |
| CI run URL and downloaded artifacts | Pending hosted run |
| Gate decision, owner and date | Pending candidate review |

## Required evidence

- [ ] G1: immutable installs, lint, formatting, types and web build pass.
- [ ] Python 3.12, 3.13 and 3.14 each pass unit/integration/migration suites;
  JUnit shows no unexpected skips and the public-schema snapshot passes.
- [ ] G2: fresh/seeded migration evidence is retained; legacy nullability,
  provenance, optional policies and deployment locks have an explicit disposition.
- [ ] G3: positive smoke passes. Stopped-worker failure occurs at export with
  useful diagnostics and successful cleanup.
- [ ] G4: CSV media type, authentication/error declarations and pagination ties
  have a reviewed resolution or explicit candidate scope decision.
- [ ] G6: dependency/security review and the single-tenant/single-worker boundary
  are documented and tested. Dependency PRs alone are not scan evidence.
- [ ] Versions, changelog, source SHA, lockfiles, artifacts and checksums agree.
  Download CI artifacts before their 14-day retention expires.
- [ ] Limitations distinguish synthetic inputs from real observations.
- [ ] Owner records go/no-go. Tagging and publication remain separate actions.

## Local commands

Run from the proposed commit with Poetry 2.2.1 and Node 24. Select an environment
for each Python interpreter and repeat tests for every matrix version. Local
Windows results do not substitute for hosted Linux results. Retain stdout,
stderr and exit status alongside the JUnit reports.

```text
poetry env use <absolute-path-to-python>
poetry install --no-interaction --no-ansi
poetry run python --version
poetry --version
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src scripts/export_openapi.py scripts/database_test_support.py scripts/smoke_stack.py scripts/seed_smoke.py scripts/release_manifest.py
poetry run pytest -q tests/unit --junitxml=test-results/rc/unit.xml
```

Provision a **new disposable** Timescale/PostGIS database using the
[database setup](v1-acceptance.md#disposable-postgresql-integration-checks).
Set `TEST_DATABASE_URL` to that server and a `test_...` or `..._test` database;
use different databases for concurrent interpreter runs. Migration tests need
`CREATEDB`/extension privileges. Never use application data.

```text
poetry run pytest -q tests/integration tests/migrations --junitxml=test-results/rc/postgres.xml
poetry run python -m scripts.smoke_stack --artifacts test-results/rc/smoke
poetry run python -m scripts.smoke_stack --inject-failure worker --job-timeout 5 --artifacts test-results/rc/smoke-negative
```

The negative command must exit **1**, with phase `export`, an export-completion
timeout and `cleanup: completed` in its unique `result.json`. Another failure
does not establish the intended assertion. The manual smoke workflow checks
these fields automatically. Stop the disposable database after testing.

From `web/`:

```text
npm install --global corepack@0.35.0
corepack enable
corepack yarn install --immutable
node --version
corepack yarn --version
corepack yarn typecheck
corepack yarn build --outDir ../test-results/rc/web
```

Validate workflows with Actionlint 1.7.12 or the digest-pinned command in the CI
static job. Its container also checks shell snippets. Hosted permissions,
scheduling and artifact delivery still require a GitHub run.

When the gate review permits candidate metadata preparation, update the four
version locations in the policy, regenerate OpenAPI and repeat the checks on
the resulting commit. Then build and inventory the artifacts:

```text
poetry run python scripts/export_openapi.py
poetry run pytest -q tests/unit/test_release_evidence.py tests/unit/test_public_openapi_export.py
poetry build --output test-results/rc/python
poetry run python -m scripts.release_manifest --artifacts test-results/rc
```

The manifest records actual versions: running this on current metadata produces
a **0.1.0 rehearsal**, not a v0.9.0-rc1 package. Before the final manifest, place
tool-version output, image inspection, CI logs and the gate decision beside the
reports. For example, `docker image inspect python:3.14-slim node:24-slim` records
resolved runtime images. Final evidence requires a clean committed tree. These
commands do not push tags or publish anything.

## CI layout and audit findings

- `static` runs locked lint/format/types/Actionlint once. The former workflow
  already ran lint once; the new matrix does not duplicate it.
- `backend (3.12/3.13/3.14)` runs unit and disposable database suites with
  fail-fast disabled. Artifacts include JUnit, package/version/command logs and
  database service output on failure.
- `web` uses Node 24 and immutable Yarn installs; retains its bundle and logs.
- `full-stack` calls the shared smoke workflow. It builds images once in that
  job, exercises readiness/seed/API/worker/scheduler, runs the existing ingestion
  concurrency and export/report SQL-failure checks, and cleans up.
- The image upload/download hop is removed. `Optional demo screenshots` keeps
  visual capture available manually. Fixed waits, external tiles and limited UI
  assertions make it unsuitable as a required RC gate; prompt 14 owns browser
  and accessibility coverage. Timeout, service logs and cleanup are explicit.
- Actions use full SHA pins and read-only content permissions. Bash `pipefail`
  propagates failed checks through log capture. Superseded CI runs are cancelled
  per ref; artifacts are retained for 14 days.

## Prompt 5 checkpoint

The RC decision is **no-go**: G2/G4 retain documented differences and G6 lacks
a complete dependency/deployment security review. Workflow preparation and local
passes do not approve a candidate. Real-data and operational gates remain future
work. Continue the numbered implementation sequence after review/merge with
these gaps visible; do not tag or publish until the decision changes.

## Observed local verification (2026-10-30)

Based on merged prompt 4 at `1eda1c085638b5f345f7b59c9f8ea4d27f8dcd64`.
Executed on Windows; each interpreter used a separate PostgreSQL database in a
new disposable Timescale/PostGIS container. Python 3.13/3.14 used fresh isolated
Poetry installs; the existing locked 3.12 environment was retained.

| Check | Actual result |
| --- | --- |
| Python 3.12.10 | 404 passed: 361 unit, 38 integration, 5 migration; no skips |
| Python 3.13.5 | 404 passed; no skips |
| Python 3.14.0 | 404 passed; no skips |
| Ruff lint / format | Passed; all 149 Python files conform to the locked formatter |
| mypy including exporter, database/smoke/evidence helpers | Passed, 73 source files |
| Actionlint 1.7.12 digest-pinned container, including ShellCheck | Passed |
| Node 24.19.0, Yarn 4.1.1 immutable install, typecheck and production build | Passed |
| Full-stack positive | Passed migrations, seed/replay, API/web, exact CSV, scheduler, ingestion concurrency and export/report failure recovery; cleanup completed |
| Stopped-worker negative | Expected exit 1, export timeout and completed cleanup; wrapper assertions passed |
| `poetry build --output test-results/rc/python` | Built 0.1.0 wheel and source archive as a rehearsal |

Local evidence is under ignored `test-results/rc/`: three interpreter JUnit
reports, web/package outputs, manifest and copied smoke diagnostics. Original
smoke reports are also under `test-results/rc-smoke/city-flood-smoke-ae09e7b3b66f`
and `test-results/rc-smoke-negative/city-flood-smoke-f782dc1e8417`.

Formatting is a separate commit: 47 tracked Python files were compared with
their prior source and have identical ASTs. Twelve tracked bytecode files were
removed from version control; caches remain ignored. This prevents Python 3.13
verification from changing tracked generated files.

The existing Alembic `path_separator` deprecation warning remains. Optional
screenshot capture was not run; it is not a release assertion. Hosted workflow
scheduling, permissions and artifact delivery cannot be established by local
Actionlint, and no remote CI pass is claimed here. No tag or publication occurred.
