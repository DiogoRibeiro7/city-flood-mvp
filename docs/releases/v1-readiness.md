# v1.0.0 readiness review — 2026-11-03

Follow-ups: [Python dependency remediation](python-dependency-remediation.md)
and [web dependency remediation](web-dependency-remediation.md) clear the recorded
lockfile findings and broken Prettier hook. The findings below remain the original
audit record. Publication remains **NO-GO** while API/migration gates are open.

**Recommendation: NO-GO for publishing v1.0.0.** Dependency advisories and
unresolved migration/API contract differences keep G2, G4 and G6 open. Passing
functional checks does not clear those findings. Metadata is staged as
`1.0.0-rc1` (Python `1.0.0rc1`), unreleased. No version tag, GitHub Release or
archival deposit was created.

## Scope and source identity

The target is a reproducible demonstration, including a **descriptive** rainfall
case study. It is not a validated flood predictor or municipal deployment.
Baseline: merged prompt 14 at `fd046be8a54083fad57317336c70fc7290e05910`.
Remote default and integration branches were verified as `develop`. Twenty-two
open dependency/action PRs were not merged into this review.

- `dae0dc048a34af80d66af44797241b1ef5ae9f3b`: candidate application metadata,
  citation and preparation documents. Fresh Python matrix, web checks, scans,
  live/cached case study and successful recovery ran on this application revision.
- `d9c54053e017ababb9ad095823a59575b4aa0d42`: only the disposable smoke request
  budget and its runbook changed. The successful complete stack/browser rerun,
  corrupt-backup check, distribution build and final artifact collection use this
  clean revision. Application code and dependency lockfiles are identical to the
  preceding preparation commit. This report is a subsequent evidence-only change.

The [artifact manifest](evidence/v1-readiness-2026-11-03/manifest.json) records
that clean collection revision, versions, lock hashes and every included file's
SHA-256. The [verification summary](evidence/v1-readiness-2026-11-03/verification-summary.json)
retains per-run revisions/results, advisory IDs/fix versions, redacted secret
triage, case-study provenance and comparison hashes. The collection revision is
not a claim that every earlier check ran at that SHA. Nested case-study manifests
are hashed separately in the summary because the generic collector excludes
files named `manifest.json`.

Large logs, JUnit, screenshots/traces, source bytes and packages remain locally
under ignored `test-results/v1-readiness/`; they are not attached to this PR.
The committed hashes identify those local artifacts, not a public archive or a
signature. Preserve them before any publication decision. CI retains its own
artifacts for 14 days.

## Executed verification

Host: Windows; Docker Linux containers. Fresh interpreters: **3.12.10, 3.13.5,
3.14.0**; Poetry **2.2.1**, uv **0.9.9**, Node **24.19.0**, Corepack **0.35.0**,
Yarn **4.1.1**, Playwright **1.58.2**, Chromium headless shell **145 / build 1208**,
Docker **29.8.2**, Compose **5.6.0**. Three new Python environments are outside
the artifact directory. Each locked install included the optional `case-study`
group. Each database suite received its own new, guarded disposable test database;
no application database configuration or data was used.

| Check / command | Observed result and evidence relative to the artifact root |
| --- | --- |
| Fresh `poetry install --with case-study --no-interaction --no-ansi` on Python 3.12–3.14 | All three exit 0; `python-{312,313,314}/install.log`, package inventories and command/exit records. Both dependency lockfiles unchanged. |
| Each fresh interpreter: `python -m pytest tests/unit tests/integration tests/migrations -q --junitxml=<file>` | **662 passed, 3 skipped, 2 warnings each**: 608 unit and 54 integration/migration passes. JUnit times 139.828 / 142.027 / 142.348 seconds. Logs/XML in each Python directory; owned database cleanup recorded as removed. |
| `poetry check --lock`; `poetry run ruff check .`; `poetry run ruff format --check .` | All exit 0; formatter checked 173 files. `poetry-check.log`, `ruff-check.log`, `ruff-format.log`. |
| `poetry run mypy src scripts/export_openapi.py scripts/database_test_support.py scripts/smoke_stack.py scripts/seed_smoke.py scripts/release_manifest.py scripts/recovery_drill.py scripts/recovery_probe.py scripts/noaa_case_study.py` | Exit 0, 84 source files; `mypy.log`. |
| Actionlint 1.7.12 Docker image, including ShellCheck | Exit 0; `actionlint.log`. Image pinned to `sha256:b1934ee5f1c509618f2508e6eb47ee0d3520686341fec936f3b79331f9315667`. |
| Promtool `check rules infra/observability/alerts.yml` and `test rules tests/observability/alerts.test.yml` | Both exit 0 using `prom/prometheus:v2.53.0`; `promtool-check.log`, `promtool-tests.log`. |
| In `web`: `corepack yarn install --immutable`, `corepack yarn typecheck`, `corepack yarn build --outDir ../test-results/v1-readiness/web-bundle` | All exit 0; install/type/build logs and generated bundle retained. |
| In `web`: `corepack yarn test:security`; `corepack yarn test:operator` | **2 + 6 passed**; separate JUnit files/logs. Operator tests include controlled error/keyboard cases and a scoped axe check with zero reported violations. |
| `python -m scripts.smoke_stack --operator --artifacts test-results/v1-readiness/smoke-retry` | Exit 0, **107.390 s**, run `city-flood-smoke-d1c7330a1605`; backend/web builds, migrations, seed replay, API, actual worker CSV, **1 live browser test**, scheduler, Prometheus/Grafana queries and ingestion/export SQL-failure regressions passed. Cleanup completed. |
| `python -m scripts.smoke_stack --inject-failure worker --job-timeout 5 --artifacts test-results/v1-readiness/smoke-negative` | Expected exit **1** at `export`, queued-job timeout; run `city-flood-smoke-45b2a5fad280`. Error/phase and cleanup explicitly asserted. |
| `python -m scripts.recovery_drill --artifacts test-results/v1-readiness/recovery` | Exit 0, **105.922 s**; run `city-flood-recovery-b058485cfc17`. Snapshot equality, killed-worker rollback/restart, SQL failure/backoff/retry and stale-job detection passed; cleanup completed. |
| `python -m scripts.recovery_drill --inject-failure corrupt-backup --artifacts test-results/v1-readiness/recovery-negative` | Expected exit **1** at `archive_integrity`, checksum mismatch refused before restore; run `city-flood-recovery-563a9a27c997`. Cleanup completed. |
| Fresh Python 3.12: `python -m scripts.noaa_case_study --output-dir test-results/v1-readiness/case-live` | Exit 0; actual live NOAA acquisition, migrated-database ingestion/replay and report/figure generation; clean source recorded. |
| Fresh Python 3.13: `python -m scripts.noaa_case_study --source-manifest test-results/v1-readiness/case-live/source/manifest.json --output-dir test-results/v1-readiness/case-replay-313` | Exit 0 in a second newly installed environment and database. Seven output files byte-identical; analytical JSON identical after excluding only the two generated import IDs. `reproduction-comparison.json`. |
| `poetry build --output test-results/v1-readiness/python-dist` | Exit 0, wheel and sdist built as `1.0.0rc1`; wheel name/version/author/license metadata inspected and hashes retained. |
| `uvx --from cffconvert==2.0.0 cffconvert --validate -i CITATION.cff` | Exit 0, valid CFF 1.2.0; isolated tool install, no application dependency changes. |
| Dependency and secret scans | Actual nonzero findings below; neither audit was reclassified as a passing check. |
| Fresh Python 3.12: `python -m scripts.release_manifest --artifacts test-results/v1-readiness` | Completed with `working_tree_clean: true` at `d9c5405`; committed copy linked above. |

### Failure found during verification

The first complete smoke attempt, `city-flood-smoke-0317160e6f9f`, exited **1**
at the browser scenario comparison. The API returned HTTP **429** for observation
evidence: rapid browser requests and preflight traffic shared the Docker gateway
IP under the default 5 requests/s, burst 20 budget. The initial browser trace,
error context and service logs are retained with that failed run.

The disposable Compose file now explicitly permits **20 requests/s, burst 100**
for both IP and tenant quotas. Quotas remain active; application/production
defaults are unchanged and dedicated quota tests remain in the passing matrix.
The complete rerun passed, including the previously failing comparison. Both
independent runs' fixed-window exports were byte-identical, and seeding twice
preserved exactly 36 observations. This demonstrates the smoke workflow under
its declared test budget; it is not a UI load or default-quota capacity test.

### Skips and limits of passing checks

On every Windows interpreter, the three parameter cases `[None]`, `[384]`, `[416]`
of `tests.unit.test_noaa_quality.test_atomic_report_modes_are_readable_or_preserve_existing_access`
were skipped: **“POSIX access modes are not Windows ACLs.”** No database tests
were skipped. Hosted Linux results for this PR's final SHA must be checked
separately; a prior green commit is not candidate evidence.

Nonfatal warnings include Poetry's legacy metadata deprecations, Alembic's absent
`path_separator` (two warnings per suite), Vite's large chunk, Recharts initial
container sizing and browser color-output warnings. Manual screen-reader/usability
review, cross-platform figure equality, external alert notification, deployment
TLS/secret-store/replica inspection, PITR/off-site storage and production load or
service-level attainment were not performed.

The database reached `0018_ingest_expiry`: PostgreSQL **16.11**, TimescaleDB
**2.25.0 OSS**, PostGIS **3.6.1**. The resolved database image was
`timescale/timescaledb-ha@sha256:1cb0764fb549213391fb5a96822b3e143da5bd72c108e5e07f5d721eddf65af9`.
All owned test containers were removed; cleanup outcomes are retained per run.

## Dependency and credential review

`pip-audit 2.9.0 --disable-pip --no-deps -r <locked-requirements.txt> --format json`
returned **1**, with **51 advisory matches across 12 packages** in the 81-entry
lock inventory. This scope includes optional, development and platform-specific
dependencies. Package counts are anyio 2, certifi 1, filelock 2, idna 1, Mako 1,
pydantic-settings 1, Pygments 1, PyJWT 16, pytest 1, Starlette 5, urllib3 5 and
virtualenv 15. Exact locked versions, advisory IDs, aliases and offered fix
versions are in the committed summary; no fix version was applied or presumed
compatible.

`corepack yarn npm audit --all --recursive --json` returned **1**, with **41
advisory entries across 10 packages**: **1 critical, 17 high, 21 moderate, 2 low**.
Affected packages are brace-expansion, esbuild, glob, ip-address, minimatch,
nanoid, postcss, source-map-js, tar and Vite. Its NDJSON includes build/development
and transitive dependencies. These are registry advisory matches, not 41 proven
exploitable paths in the deployed bundle. Review reachability, remediate or
justify each applicable finding, then rerun locked installs and affected checks.

Gitleaks **8.30.1** scanned the non-shallow checkout's available history with
`git /repo --log-opts=--all --redact=100` (138 commits, about 20.44 MB). Exit **1**
reported six `generic-api-key` findings. All six were inspected at their exact
commit/file/line: controlled JWT literals inside unit tests, used in monkeypatched
settings and test signing. No deployed credential was identified in that scope.
The unmodified redacted findings and their manual triage are retained; the scan
was not forced green with broad exclusions or a history rewrite. Scanning the
built web bundle with `dir /bundle --redact=100` returned **0**, no findings.
Neither result inventories an external secrets manager or proves absence of secrets.

## Real-data and recovery interpretation

Live NOAA retrieval occurred at **2026-11-03T14:59:11.246787+00:00**. The annual
station `POMU0068545` source is **14,325,059 bytes**, SHA-256
`1febfaa9832085295cb813e987de298c73298318bf6104a51abb1ba65397d1b7`.
The fixed window is `[2010-01-01, 2010-01-12)` UTC. Of 529 window timestamps,
**6** contain quantitative positive reports, **1** is trace, **522** lack a
quantitative value, and **0** establish observed zero rainfall. Clipped interval
support is **30/264 hours**. First import inserted six observations; replay
inserted zero, recognized six existing rows and preserved provenance. Both
fresh environments produced identical observations/daily/timeline CSV, quality
JSON, report Markdown, SVG and PNG. The current PNG was visually inspected;
unknown and trace intervals are explicit. Both environments ran on the same
Windows host, so this is not cross-platform rendering evidence. Independent
flood labels remain absent; accuracy values remain null. This satisfies the
explicitly descriptive branch of G5, not flood-event validation.

Logical restore reproduced the protected snapshot exactly. Local database
recovery measured **15.609 s**, checkpoint exposure was bounded by **12.266 s**,
and one deliberately committed post-backup observation was absent. Worker
kill/restart recovery measured **12.547 s**; SQL-failure retry **19.172 s**.
These are below the proposed drill targets (14,400 / 900 / 300 s respectively)
for this tiny synthetic workload and pre-provisioned restore destination. They
do not establish operational RTO/RPO, PITR or exactly-once external effects.

## Gate disposition and next work

| Gate | Disposition on the observed candidate | Required follow-up |
| --- | --- | --- |
| G1 installation/static | Local evidence passes across the declared matrix; packages and container builds succeed. | Check final PR SHA's hosted CI and preserve artifacts. |
| G2 migrations/integrity | **OPEN.** Fresh/seeded/repeat/integrity tests pass while documenting 20 legacy timestamp nullability differences; optional Timescale policies are absent on OSS. | Resolve or explicitly accept each schema exception within the demonstration scope; record deployment upgrade/policy prerequisites. Passing tests of known exceptions do not close the gate. |
| G3 seeded workflow | **PASS within disposable scope.** Complete corrected smoke, replay, exact CSV and expected stopped-worker failure pass. | Preserve declared request budget; repeat on any changed candidate. |
| G4 API contract | **OPEN.** Schema snapshot and behavioral tests pass; CSV download 200 still declares an empty JSON schema, some 404/413/429/504 responses are undeclared, event/note pagination lacks unique timestamp tie breakers. | Fix media/error declarations and stable tie ordering with focused regressions; reconcile the [contract audit](api-contract-audit.md). Prompt 13's deployed admission fix is already included. |
| G5 real-data experiment | **PASS for explicitly descriptive rainfall evidence.** Actual ingestion/replay, source/license/provenance, missing/trace distinction and second-environment reproduction recorded. | Independent flood labels and suitable temporal data are required before accuracy/lead-time claims, not to relabel this descriptive demonstration. |
| G6 security | **OPEN / NO-GO.** Role/tenant/CORS/quota tests and bundle scan pass within dedicated-tenant, one-API-process scope; dependency findings remain. | Review/remediate advisories and rerun scans/tests; retain fixture-secret triage. No shared-database tenancy or multiple-process claim. |
| G7 monitoring/recovery | **PASS within local drill scope.** Scrapes, panel queries, alert rules, restore/worker/retry/stale detection and corruption refusal verified. | Operational objectives and deployment notification/storage evidence remain outside this demonstration. |
| G8 operator evidence | **PASS within automated scope.** Six controlled tests, two security tests, one live stack workflow and scoped axe checks pass. | Manual usability/accessibility, immutable historical input replay and real flood validation are not established. |
| G9 reproducibility/provenance | Local reproduction, author/citation/version/changelog/checklist and hashed evidence complete. **Final release decision remains open.** | Preserve artifacts, confirm hosted CI for the selected final SHA, resolve open gates and obtain an explicit owner decision. |

Next reviewable work is dependency remediation with advisory triage, followed by
API contract corrections and a documented migration/schema disposition. Then
select a new reviewed candidate, rerun affected checks and reconsider the release.
Merging this readiness PR does not approve a version tag or publication.

## Metadata

The established non-bot Git author is **Diogo Ribeiro**. Poetry's placeholder
author is replaced by that name; citation metadata uses its given/family names.
No email, ORCID, affiliation, DOI or release date is inferred. The repository's
MIT license is retained. [CITATION.cff](../../CITATION.cff) describes the software
and an unreleased candidate; the NOAA dataset retains its separate attribution.
Optional Zenodo metadata/deposit was not needed or created.

See the [reproducibility statement](../../REPRODUCIBILITY.md),
[changelog](../../CHANGELOG.md) and [tagged-release checklist](v1-release-checklist.md).
