# API contract audit

Audit date: 2026-10-30. Baseline: `develop` at
`e71e8316283b3531c2a4061ded5eab15d15a809e` (prompt 2 merged).
The audit compared 34 operations across 31 paths in the live FastAPI schema,
router declarations, Pydantic models, exception handlers, repository queries,
the public exporter, and HTTP/PostgreSQL tests.

## Findings and changes

| Area | Observed behavior and contract | Resolution / evidence |
| --- | --- | --- |
| Validation status | FastAPI generated 422 responses for 30 operations; the application handler returns 400 `INVALID_ARGUMENT`. The public exporter incorrectly relabeled those responses `UNPROCESSABLE_ENTITY`. | Both live `/openapi.json` and the public snapshot now describe the existing 400 envelope. `api/openapi.py` replaces only automatically generated validation responses, preserving explicit 422 declarations and existing endpoint-specific 400 examples. Error schemas come from the shared Pydantic `ErrorResponse` model. |
| Malformed input | Calibration watch > warning produces a `ValueError` in Pydantic diagnostics; rejected NaN/infinite thresholds leave nonfinite values in diagnostics. Serializing either caused HTTP 500. | Diagnostics now encode exceptions, nonfinite floats, and bytes safely. HTTP tests verify 400 responses, envelope fields, request IDs, malformed JSON, invalid body types, and missing fields. The threshold constraints are unchanged. |
| Timestamps | GET query timestamps already interpreted missing offsets as UTC. Export/report job bodies retained naive datetimes, so comparing a naive bound with an aware bound crashed with HTTP 500. | Both job query models normalize to UTC before validation, persistence, and worker use. Missing offsets remain accepted as UTC; explicit offsets retain their instant. Equal/reversed windows and values outside the representable UTC range return 400. PostgreSQL tests verify canonical stored timestamps; CSV worker tests cover both combinations of naive/aware bounds. |
| Pagination | Assets, events, and notes return bare arrays with offset/limit, despite unused `ListResponse`/`Paging` models. Limits are assets 1–5000, events 1–1000, notes 1–200; offsets are nonnegative. | Preserve arrays and bounds. HTTP tests exercise invalid bounds/types; PostgreSQL tests exercise first/next/empty asset pages, the maximum asset limit, and pagination after filtering. Asset ordering uses `asset_id`. Timestamp ties in events/notes still need the follow-up below. |
| Filters | Asset type is a string filter: an unknown type returns an empty array. Spatial/tag validation returns 400. Repeated tag predicates and cross-city/scenario references have existing regression coverage. | Preserve these semantics. HTTP tests add malformed bbox/tag and nonfinite radius cases; PostgreSQL tests verify type/tag filters combined with pagination and the empty unknown-type result. Existing spatial, reference, and scenario suites pass. |
| Success/error compatibility | Job creation returns 200 with a queued job. Resource-specific errors include `CITY_NOT_FOUND`, `ASSET_NOT_FOUND`, and `JOB_FILE_NOT_FOUND`. | Preserve current success statuses, response bodies, and specific error examples. Existing export tests continue through queue, worker, status, download, and missing artifact handling. |

The changed malformed requests now receive the intended 400 instead of 500.
Successful payload shapes, list formats, aliases (`from`/`to`), and filter
acceptance remain unchanged. Job query timestamps are persisted as UTC strings;
normalization also applies when workers read previously queued queries.
Ingest payloads and idempotency hashing are outside this change.

## Remaining discrepancies

G4 remains open: this change resolves the cohesive request-validation group,
not every response or deployment configuration.

- **CSV media type:** `/v1/analytics/jobs/{job_id}/download` returns a file,
  while the generated 200 response still advertises `application/json` with an
  empty schema. Declare the CSV/binary response explicitly and assert its
  content type and disposition through HTTP.
- **Authentication and other errors:** the exporter derives security from
  header names and selects Bearer when both headers exist. Runtime access
  depends on environment/JWT/API-key configuration. Some note 404 errors and
  middleware 413/429/504 responses are not declared per operation. Review the
  auth matrix with prompt 13 and add its contract assertions without weakening
  runtime checks.
- **Stable pagination ties:** event lists order by `start_ts` descending;
  note lists order by `created_at` descending, with no unique secondary key.
  Equal timestamps can make offset pages unstable. Add deterministic tie
  breakers and fixtures before claiming stable pagination across those lists;
  concurrent inserts also remain an inherent offset-pagination limitation.
- **Ingest timestamp policy:** ingest models retain their existing datetime
  handling. Any future normalization must consider stored idempotency digests
  and existing payload equivalence, rather than changing them implicitly.

## Reproduction and observed results

Run these from the repository root with the locked Python 3.12 environment:

```text
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src scripts/export_openapi.py
poetry run python scripts/export_openapi.py
poetry run pytest -q tests/unit --junitxml=test-results/contract-unit.xml
poetry run pytest -q tests/integration --junitxml=test-results/contract-integration.xml
poetry run python -m scripts.smoke_stack --artifacts test-results/contract-smoke
```

Integration tests require `TEST_DATABASE_URL` pointing to a **new disposable**
PostgreSQL database named `floodmvp_test`; they recreate tables. Follow the
[isolated database instructions](v1-acceptance.md#disposable-postgresql-integration-checks).
This audit used a fresh Timescale/PostGIS container, no host data mounts,
loopback-only published port, and the existing test-name safeguard. Application
data was not used. Integration tests do not verify the migration chain; prompt 4
addresses that separately.

Observed with Python 3.12.10:

- `ruff check .`: passed.
- `ruff format --check .`: failed on 52 existing files; all changed Python files
  pass. The baseline had 53 failures; formatting the touched OpenAPI test removed
  one. A repository-wide formatting change is outside this PR.
- mypy: passed, 69 source files.
- Unit tests: **350 passed**, no skips.
- Disposable PostgreSQL integration tests: **38 passed**, no skips.
- Full-stack smoke: passed migration, deterministic seed, readiness, API,
  queued export/CSV, and scheduler checks. The runner cleaned up its stack.
  Local evidence: `test-results/contract-smoke/city-flood-smoke-465484972f2c/result.json`
  and adjacent logs (ignored artifacts, not committed).
- Web `corepack yarn typecheck` and
  `corepack yarn build --outDir ../test-results/contract-web-dist`: passed
  with Node 24.19.0 / Yarn 4.1.1. Vite retains its existing bundle-size warning.

The public snapshot test compares the complete generated export, not only path
names. Additional tests compare validation statuses against unmodified FastAPI
generation, preserve explicit 422 responses, and verify repeated schema calls
and exporting do not alter the live contract. Local results do not establish a
remote CI result or production readiness.
