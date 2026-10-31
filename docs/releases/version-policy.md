# Version and runtime policy

Current Python, web and API metadata remain **0.1.0**. The next target is a
synthetic demonstration candidate named **v0.9.0-rc1**, not an issued release.
The [candidate checklist](rc-checklist.md) and [v1 gates](v1-acceptance.md) govern
readiness. Version changes alone do not establish readiness.

## Version locations and compatibility

Keep these values aligned in the same reviewed change:

| Location | Stable example | First candidate example |
| --- | --- | --- |
| `pyproject.toml`, `tool.poetry.version` | `0.9.0` | `0.9.0rc1` |
| `web/package.json`, `version` | `0.9.0` | `0.9.0-rc1` |
| FastAPI version in `src/floodmvp/api/main.py` | `0.9.0` | `0.9.0-rc1` |
| Regenerated `docs/openapi/public.yaml`, `info.version` | `0.9.0` | `0.9.0-rc1` |
| Proposed Git tag, only with explicit approval | `v0.9.0` | `v0.9.0-rc1` |

The release-version test checks package/API alignment, including Python's
candidate spelling; the existing snapshot test checks the public schema.
Regenerate the snapshot after a version edit and review the diff.

Use patch increments for compatible fixes and minor increments for compatible
features. Document incompatible API/data changes explicitly before v1; after
v1 they require a major increment. Increase the candidate number whenever
candidate source or dependencies change. Never move a published tag or reuse
its version for different artifacts.

The `/v1` URL namespace is an API compatibility boundary, separate from the
package version. Preserve successful request/response behavior unless a
migration path and regression evidence accompany a reviewed change. Alembic
revision IDs are independent; retain the head and upgrade prerequisites in evidence.

## Verified runtime matrix

| Component | CI policy | Container / reproduction |
| --- | --- | --- |
| Backend tests | Python 3.12, 3.13, 3.14; unit + integration + migrations per version | Backend image uses Python 3.14; record exact patches/platform |
| Static checks | Python 3.12 once | Locked Ruff/mypy; local hooks use Poetry |
| Web | Node 24, Yarn 4.1.1, Corepack 0.35.0 | Web image also uses Node 24 |
| Python installs | Poetry 2.2.1 with committed `poetry.lock` | Same Poetry version in backend image |
| Database checks | PostgreSQL 16 / TimescaleDB 2.25.0 OSS, PostGIS | Fresh disposable resources and explicit test names |

Python metadata currently permits 3.12 and later within Python 3; the matrix
states what this project verifies. New runtime versions need install,
type/build, unit/database and container-smoke evidence before joining that
matrix. Hosted runner/container patches may differ from the laptop.

## Dependencies and provenance

Keep both lockfiles in the candidate commit and use immutable Yarn installs.
Actions are pinned to full commit IDs with readable major-version comments;
Dependabot still proposes updates. Verify upstream refs and rerun workflow
validation when changing pins. Actionlint is pinned by image digest.

Runtime base images still use version tags. Record resolved image IDs/digests
and build logs for each candidate; tags alone cannot establish identical images
across dates. Dependency locks and artifact hashes support auditing, not a claim
of bit-for-bit rebuilds on arbitrary hosts.

`scripts.release_manifest` records source SHA, clean/dirty status, package
versions, lock hashes, interpreter/platform and artifact checksums. It does not
turn missing or failed checks into passes. Releasable evidence needs a clean
committed tree, retained results and an explicit gate decision.

Keep `CHANGELOG.md` under Unreleased until approval. Do not invent release dates,
authors, DOIs or publication records. Tags, GitHub Releases and external deposits
require a separate explicit instruction.
