# Python dependency remediation — 2026-11-03

Follow-up: the [2026-11-05 web remediation](web-dependency-remediation.md) clears
the web findings and repairs the Prettier hook recorded below. This document
retains its original Python-focused verification scope.

The locked Python audit now reports **zero known advisories across 82 packages**,
down from **51 matches across 12 packages** in the merged readiness baseline.
No advisory was ignored. This clears the observed Python lockfile findings;
**v1.0.0 publication remains NO-GO** because the web findings and API/migration
gates remain open.

Baseline: merged PR #157, `b2a5b1ce2d5be11823f54ce9955194cd7f0de1dc`.
Implementation: `7d99146d3586a66356e8c8c37b518bc547062120`. The checks below use
that clean commit; this document is a subsequent evidence update. The prior
[readiness review](v1-readiness.md) and its evidence remain historical records.

## What changed

| Package | Previous lock | Updated lock | Prior advisory matches |
| --- | --- | --- | --- |
| anyio | 4.12.1 | 4.16.0 | 2 |
| certifi | 2026.1.4 | 2026.10.23 | 1 |
| filelock | 3.20.3 | 4.2.7 | 2 |
| idna | 3.11 | 3.20 | 1 |
| Mako | 1.3.10 | 1.4.3 | 1 |
| pydantic-settings | 2.13.1 | 2.16.2 | 1 |
| Pygments | 2.19.2 | 2.21.0 | 1 |
| PyJWT | 2.12.1 | 2.15.1 | 16 |
| pytest | 9.0.2 | 9.2.0 | 1 |
| Starlette | 0.52.1 | 1.10.0 | 5 |
| urllib3 | 2.6.3 | 2.8.0 | 5 |
| virtualenv | 20.36.1 | 21.15.2 | 15 |

Resolution also updates distlib 0.4.0 → 0.4.4, packaging 26.0 → 26.3 and
typing-extensions 4.15.0 → 4.16.0, and adds virtualenv's python-discovery 1.9.2.
No other locked packages changed. Direct minimums advance to PyJWT 2.15.1,
Starlette 1.3.1, pydantic-settings 2.14.2 and pytest 9.0.3. Transitive versions are
fixed by the committed lockfile. Application version metadata remains unreleased.

FastAPI stays at 0.135.1: its published package metadata permits Starlette >=0.46.0,
and [FastAPI documents Starlette 1.x support](https://fastapi.tiangolo.com/release-notes/#01330).
The [Starlette release notes](https://starlette.dev/release-notes/) describe the
security fixes and major-version changes. The unchanged public OpenAPI snapshot
and complete application suites are the compatibility evidence for this project.

[PyJWT's changelog](https://pyjwt.readthedocs.io/en/stable/changelog.html) documents
malformed-claim handling and token-decoding hardening. Ten added application
regressions send signed malformed `exp`/`nbf`/`iat` values and deeply nested JSON
through the actual request middleware and protected route. They require 401,
no repository access, and successful subsequent valid authentication. Eight
cases raised uncaught TypeError under the old lock; the existing recursion and
required-expiry protections already passed the other two. All ten pass after
the update. Random test keys avoid adding static credential-like literals.

## Verification

| Check | Result |
| --- | --- |
| Fresh locked installs on Python 3.12.10 / 3.13.5 / 3.14.0 | Pass, including the optional case-study group. `uv pip check` reports all 82 installed packages compatible in each environment. |
| Full `pytest tests/unit tests/integration tests/migrations -q` in each environment | **672 passed, 3 skipped each** (618 unit + 48 integration + 6 migration passes). JUnit times: 264.407 / 262.861 / 254.524 s. Separate owned databases; all cleaned up. |
| Focused authentication/public OpenAPI tests | **50 passed**, including all ten new JWT cases; public schema unchanged. The old dependency environment produced 8 failures and 2 passes for those ten cases. |
| `poetry check --lock`, Ruff lint/format, mypy | All pass; 173 formatted files, 84 typed source files. |
| Python lock inventory audit | Before: exit 1, 51 matches / 12 packages / 81 inventory entries. After: exit 0, **0 matches / 82 entries**. [Raw post-update report](evidence/python-security-2026-11-03/after-audit.json). |
| Full Docker smoke with `--operator` | Pass, **317.828 s**, project `city-flood-smoke-aa05e355c645`. Backend/web builds, migrations, deterministic seed/replay, API, actual worker CSV, **1 live browser workflow**, scheduler, monitoring and ingestion/export SQL-failure regressions pass. Cleanup completed. |
| Cached NOAA case study with the updated dependencies | Pass. Seven report/table/figure files byte-identical to the reviewed live-source baseline; analytical JSON identical after excluding only the two generated import IDs. Source checksum and clean revision retained; disposable DB removed. |
| Developer hook bootstrap | Existing complete pre-commit config fails at checkout of the unavailable `pre-commit/mirrors-prettier` ref `v3.2.5` (exit 3), before running a hook. Running only the unchanged `check-yaml` hook through a temporary isolated config succeeds (exit 0), exercising updated virtualenv/filelock. This is not a passing claim for the complete hook config. |

The three skips on every interpreter are the existing POSIX permission-mode
cases of `test_atomic_report_modes_are_readable_or_preserve_existing_access`
(`[None]`, `[384]`, `[416]`): POSIX access modes are not Windows ACLs. No database
tests were skipped. Alembic emitted two existing `path_separator` warnings per
run; Python 3.14 also emitted two pytest-asyncio event-loop-policy deprecations.
Poetry's legacy metadata warnings remain. These are local Windows results with
Linux Docker services, not final-SHA hosted Linux results.

The first parallel Python 3.12/3.14 installs encountered Windows file-lock errors
in Poetry's shared artifact cache. Failed logs were retained. Both were repeated
in new environments with separate Poetry caches and succeeded; Python 3.13's
first install succeeded. No package checksum or dependency constraint was bypassed.

Web dependencies/typechecking/controlled browser suites, recovery drills, secret
scans and a second live NOAA download were not repeated in this targeted change.
The actual web/API/worker workflow and complete backend tests above were rerun.
The missing Prettier mirror ref is a separate existing developer-tooling follow-up;
`.pre-commit-config.yaml` is unchanged.


Audit command, executed against both complete locked name/version inventories:

```text
pip-audit --disable-pip --no-deps -r <before-or-after-requirements.txt> --format json --output <audit.json>
```

The tool is pip-audit 2.9.0. The inventories include main, dev, optional and
platform-specific packages; advisory matches do not establish runtime exploitability.
The 32 main-group and 19 dev-group baseline matches are all absent in the new
scan. This scan does not assess Node dependencies, operating-system packages,
or image/bootstrap tools outside `poetry.lock`, and zero reported advisories is
not proof that no vulnerabilities exist.

## Reproduction and evidence

Use Poetry 2.2.1 with Python 3.12–3.14, install from the committed lock including
`--with case-study`, and run the unit/integration/migration suites against an
owned disposable PostgreSQL/Timescale/PostGIS test database. The
[reproducibility statement](../../REPRODUCIBILITY.md) and
[case-study runbook](../runbooks/noaa_case_study.md) specify the existing runners.
This follow-up's complete stack command was:

```text
python -m scripts.smoke_stack --operator --artifacts test-results/python-security/smoke
```

The cached case-study command used the retained checksummed source manifest:

```text
python -m scripts.noaa_case_study --source-manifest test-results/v1-readiness/case-live/source/manifest.json --output-dir test-results/python-security/case-replay
```

The [verification summary](evidence/python-security-2026-11-03/verification-summary.json)
retains advisory IDs and fix versions, all dependency changes, per-check results
and comparison hashes. The [artifact manifest](evidence/python-security-2026-11-03/manifest.json)
identifies the locally retained audit reports, requirements, install/test logs,
JUnit and smoke/case-study evidence under ignored `test-results/python-security/`.
Large artifacts and caches are not committed or publicly archived. Hosted CI for
the final PR SHA is separate evidence; do not infer it from the prior PR's green run.

## Remaining work

G6 stays open for the web audit findings (41 entries in the unchanged prior scan)
and scoped deployment evidence; G2 and G4 retain their recorded schema/contract
gaps. Address web dependencies/tooling next, then the API and migration follow-ups.
No GitHub Release, version tag or deposit is created by this change.

The dependency refresh overlaps the upgrades proposed in Dependabot PRs #69,
#91, #92, #93, #94, #105, #106, #111 and #130. Those PRs were not merged, closed,
or otherwise changed; their remaining relevance can be reviewed after this PR.
