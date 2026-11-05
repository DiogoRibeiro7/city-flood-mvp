# API response and pagination contract follow-up

Date: 2026-11-05. Baseline: `develop` at
`4ddc301e5ada3fe2cab6dc1eeb9c864858d5261e`, after PR #160.
This follow-up addresses the response and pagination discrepancies recorded in
the [API audit](api-contract-audit.md) and G4 of the
[readiness review](v1-readiness.md). The default and integration branch is
`develop`.

## Corrections and compatibility

| Area | Result and regression coverage |
| --- | --- |
| CSV download | The live and exported 200 response for `/v1/analytics/jobs/{job_id}/download` declares `text/csv`, a binary string schema and the attachment `Content-Disposition` header. `FileResponse` now receives the media type explicitly, avoiding host MIME-database variation. The real queue/worker/export integration test checks HTTP media type, filename and CSV contents for all three timestamp-input variants. Error responses remain JSON. |
| Error envelopes | Every documented operation includes middleware 413 (`REQUEST_TOO_LARGE`), 429 (`RATE_LIMITED` and `TENANT_RATE_LIMITED`) and 504 (`REQUEST_TIMEOUT`) responses. Note get/delete declare `NOTE_NOT_FOUND`; note creation documents city, asset and event reference errors. Queue lookup/retry/cancel and unconfigured ingestion declare their existing errors. Live and public error responses reference the shared `ErrorResponse` model. HTTP regressions compare actual status, content type, code and request ID with both schemas. |
| Authentication declarations | Deployment data operations retain the existing JWT-or-legacy-key declarations, including JWT precedence, role/tenant checks and local-demo exceptions. Ingestion now names a distinct `IngestBearer` scheme for `INGEST_TOKEN`; a deployment JWT or API key does not substitute for that token. The exporter preserves the live declarations instead of deriving security requirements from header names. Existing deployed-authentication and privileged-access tests remain active. Runtime authorization is unchanged. |
| Pagination ties | Events order by `start_ts DESC, event_id ASC`; notes order by `created_at DESC, note_id ASC`. PostgreSQL HTTP tests insert timestamp ties out of ID order and verify repeated first/next/empty pages, the complete result, and filtering before pagination. Newer and older timestamps verify that the original primary ordering remains intact. |

Paths, successful JSON payloads, bare-array list responses, timestamp parsing,
filters, pagination bounds, error statuses/codes, CSV bytes and attachment names
remain compatible. Equal-timestamp rows now have a defined order. Existing
clients may observe a different order within those formerly unspecified ties.
Offset pagination remains sensitive to concurrent inserts/deletes or selection
of a new analytics run; it is not a snapshot or cursor protocol. Ingest timestamp
normalization and stored idempotency digests are unchanged.

The checked-in `docs/openapi/public.yaml` is regenerated from the live app. The
snapshot test checks the full export, and dedicated tests compare both live and
public CSV, error and authentication declarations. Repeated schema generation
and exporting preserve the live cached schema and explicitly declared 422s.

## Verification

Local commands use the existing locked Python 3.12 environment from the dependency
remediation. Artifacts are under ignored `test-results/api-contract/`. Database
tests use a newly created TimescaleDB/PostGIS container, a loopback-only random
port, no host data mount, and the guarded `floodmvp_test` database. The integration
suite recreates only that database's tables; migration tests use fresh child test
databases. The container is removed after the checks.

```text
python -m ruff check .
python -m ruff format --check .
python -m mypy src scripts/export_openapi.py
python scripts/export_openapi.py
python -m pytest -q tests/unit --junitxml=test-results/api-contract/unit.xml
python -m pytest -q tests/integration tests/migrations --junitxml=test-results/api-contract/database.xml
python -m scripts.smoke_stack --operator --artifacts test-results/api-contract/smoke
```

Observed locally with Python **3.12.10**:

| Check | Result |
| --- | --- |
| Repository Ruff lint and format | Pass; 175 Python files formatted correctly. |
| mypy, including the public exporter | Pass; 77 source files. |
| Complete unit suite | **669 passed, 3 skipped**, 17.99 s. The three existing atomic-file permission cases skip because POSIX access modes are not Windows ACLs. `unit.xml` and `unit.log` retain the results. |
| PostgreSQL integration and migration suites | **56 passed**, no skips, 73.75 s. This includes filtered event/note pagination ties, real worker CSV HTTP headers, and fresh/seeded/repeat migration assertions. `database.xml`, `database.log` and `database.json` retain the results and owned container identity; cleanup completed. |
| Full stack with `--operator` | Pass in **101.968 s**, run `city-flood-smoke-0726ce4e6454`: migrations, seed replay, API, exact worker CSV, **1 live browser test**, scheduler, monitoring and ingestion/export failure regressions. All owned resources removed. The report and command/browser logs are under `smoke/<project>/`. |
| Web `corepack yarn typecheck` and `corepack yarn build --outDir ../test-results/api-contract/web-dist` | Both pass; generated assets stay outside tracked source. Vite retains its existing large-chunk and external-output-directory notices. |
| Pre-commit on changed files | All six applicable hooks pass; the web-only Prettier hook skips because no web source changed. |

The existing Alembic `path_separator` deprecation and browser color-output
warnings are nonfatal. Hosted Linux checks cover the Python 3.12–3.14 matrix;
the final PR SHA's result is linked in the PR, separately from this local record.
A passing schema comparison alone does not establish correct HTTP or database behavior.
The legacy migration/schema disposition remains the next implementation work;
the final release decision and deployment evidence remain separate requirements.
No tag, release or deposit is authorized by this follow-up.
