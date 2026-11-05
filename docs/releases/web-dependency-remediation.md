# Web dependency remediation — 2026-11-05

The complete recursive web dependency audit now reports **zero advisory entries**,
down from **41 across 10 package names** (1 critical, 17 high, 21 moderate, 2 low).
The broken Prettier mirror hook is replaced by the installed, locked formatter.
A fresh install, build, eight controlled browser tests and one live full-stack
browser workflow pass. The unchanged Python lock was rescanned and still reports
zero known advisories. **v1.0.0 publication remains NO-GO** for the outstanding
API contract and migration/schema gaps.

Baseline: merged PR #158 at `9774cfb0d69e9ddd017c85fd53bcf1e88ccef8e5`.
Implementation: `60653a1c5d85930a2ec7153dbb77dd136b66fe7e`.
The fresh web copy and full-stack checks use this clean commit. Hook validations
used the same implementation files before that commit; this report is a later
evidence-only change. The [original readiness review](v1-readiness.md) and
[Python follow-up](python-dependency-remediation.md) retain their dated results.

## Dependency changes

| Previously affected package | Previous lock | Final disposition |
| --- | --- | --- |
| Vite | 8.0.1 | 8.3.6 |
| esbuild | 0.27.4 | 0.28.2 |
| PostCSS | 8.5.8 | 8.5.32 |
| nanoid | 3.3.11 | 3.3.20 |
| source-map-js | 1.2.1 | 1.2.2 |
| tar | 7.5.11 | 7.5.22 |
| glob | 13.0.1 | Removed with the obsolete optional build-tool chain |
| minimatch | 10.2.4 | Removed with that chain |
| brace-expansion | 5.0.2 | Removed with that chain |
| ip-address | 10.1.0 | Removed with that chain |

Direct minimums advance to Vite 8.3.6 and esbuild 0.28.2. Updating the existing
`node-gyp@latest` descriptor from 12.2.0 to 13.1.0 removes its old
make-fetch-happen/cacache/glob dependency chain and uses undici 8.12.4 instead.
That optional node-gyp path is introduced by fsevents through Vite/Playwright;
no new direct build-tool dependency or forced transitive resolution is added.
Vite's bundler advances from Rolldown 1.0.0-rc.10 to 1.2.16, with its native
platform packages. The complete version additions/removals are in the summary.
React, Recharts, Playwright 1.58.2 and Prettier 3.8.1 remain at their prior locks.

The compatible-range refresh used [Yarn's recursive update](https://yarnpkg.com/cli/up),
followed by the two direct minimum changes and the node-gyp refresh. The initial
compatible-range pass still reported esbuild/glob/minimatch findings; the final
scan includes those packages' fixes/removal. No advisory exclusions or package
`resolutions` were used. [esbuild 0.28.1 release notes](https://github.com/evanw/esbuild/releases/tag/v0.28.1)
describe the Windows development-server path fix included in 0.28.2.

The optional native-build tooling now requires at least Node 24.15.0 on the
supported Node 24 line. `web/package.json` declares `^24.15.0`, and the
[runtime policy](version-policy.md) records the floor. Local checks used
**Node 24.19.0**; the exact Docker base digest used in the build reports
**Node 24.22.2**. Yarn remains **4.1.1**, Corepack **0.35.0**.

## Prettier hook repair

The [old mirror repository](https://github.com/pre-commit/mirrors-prettier) is
archived, and its configured `v3.2.5` tag is unavailable. The local system hook
now invokes `node web/node_modules/prettier/bin/prettier.cjs --write --ignore-unknown`
from the repository root. Pre-commit's `web/...` filenames therefore retain their
correct meaning, including paths containing spaces. Install dependencies first
with `corepack yarn install --immutable` in `web/`; no separate formatter download
or automatic installation occurs in the hook.

Temporary untracked probes verified actual reformatting, a second unchanged run
and unknown-file preservation. Because pre-commit detects changes through Git,
the probe asserts file contents directly rather than expecting a nonzero exit
for an untracked file. The complete repository hook configuration also passed
for all four implementation files, including YAML, EOF/whitespace, Ruff lint,
Ruff format, mypy and Prettier. The source tree was not globally reformatted.

## Observed checks

| Check | Result |
| --- | --- |
| `corepack yarn npm audit --all --recursive --json` | Baseline exit 1 with 41 entries; final exit **0** with empty NDJSON. Repeated in the fresh install with the same result. |
| `corepack yarn install --immutable` | Pass in the working checkout and a new directory containing the 21 tracked web files, initially without node_modules. Source file hashes and clean implementation SHA retained. |
| `corepack yarn typecheck`; `corepack yarn build --outDir <artifact-directory>` | Both exit 0 in the fresh install. Generated assets retained outside tracked source. |
| `corepack yarn test:security` | **2 passed**, zero failures/skips; JUnit 17.406 s. |
| `corepack yarn test:operator` | **6 passed**, zero failures/skips; JUnit 42.648 s, including scoped accessibility and keyboard/error cases. |
| `python -m scripts.smoke_stack --operator --artifacts test-results/web-security/smoke` | Exit 0 in **284.594 s**; run `city-flood-smoke-9c986f16a4dc`. Backend/web image builds, migrated database, seed replay, API, real worker CSV, **1 live browser test**, scheduler, monitoring queries and ingestion/export SQL-failure recovery pass. All owned stack resources removed. |
| `python -m pre_commit run --files .pre-commit-config.yaml web/package.json web/yarn.lock docs/releases/version-policy.md` | All seven hooks pass, using the updated Python environment and installed web dependencies. |
| Current Python lock inventory: `pip-audit --disable-pip --no-deps -r <inventory> --format json` | Exit 0, zero known advisories across 82 lock entries; Python dependencies unchanged. |
| Gitleaks 8.30.1 `dir /bundle --redact=100` on the rebuilt web bundle | Exit 0, no findings. |
| `python -m scripts.release_manifest --artifacts test-results/web-security` | Records clean implementation SHA, lock hashes and all retained artifact hashes. |

Playwright remains 1.58.2 with the installed Chromium headless shell. The live
workflow's JUnit time is 12.687 s. Current screenshots come from that functioning
stack; the observation-review screenshot was visually inspected. Screenshots
supplement the assertions and show synthetic observations, not real flood validation.

The Node base used by Docker is
`node@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9`.
A post-cleanup attempt to inspect the removed stack correctly found no resources;
the Node version was subsequently verified by running that exact base digest.

Vite retains its large-chunk warning (732.22 kB JavaScript before compression)
and output-directory notice; Recharts emits initial container-size warnings.
The existing generic pre-commit-hooks revision emits deprecated-stage warnings.
These did not fail checks. macOS/fsevents compilation was not exercised; its
optional dependency graph is included in the audit. The backend matrix, recovery
drill and real-data experiments were not repeated in this web-only change.
The preceding Python PR's [hosted CI run succeeded](https://github.com/DiogoRibeiro7/city-flood-mvp/actions/runs/41673841042);
CI for this PR's final SHA remains separate evidence.

## Evidence and release disposition

The [verification summary](evidence/web-security-2026-11-05/verification-summary.json)
contains advisory IDs/URLs/ranges, version changes and per-check results. The
[artifact manifest](evidence/web-security-2026-11-05/manifest.json) hashes locally
retained audit output, source identities, logs, JUnit, screenshots and bundle files
under ignored `test-results/web-security/`. Large artifacts are not publicly
archived by this PR. Audits include development and platform-optional dependencies;
registry matches are not claims of runtime exploitability. Zero findings do not
establish the absence of vulnerabilities or assess OS/bootstrap packages outside
the dependency inventories. The full Git-history secret scan was not repeated.

The dependency portion of G6 and the Prettier blocker are cleared. Existing
single-tenant/single-API-process limits and deployment verification requirements
remain. G2's legacy schema disposition and G4's API media/error/pagination gaps
are the next implementation work before a new release decision. No merge, tag,
GitHub Release or deposit is performed by this follow-up.

This refresh overlaps web Dependabot proposals #82, #88, #96, #98, #99, #101,
#103, #110 and #159; their PRs were not merged, closed or changed here.
