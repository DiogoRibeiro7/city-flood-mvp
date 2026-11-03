# Reproducibility statement

City Flood MVP reproduces a software demonstration and a descriptive rainfall
case study. It does not establish prediction accuracy or municipal readiness.
Use the exact reviewed commit, both lockfiles, recorded Python/Node versions and
database image digest. Version metadata alone does not identify the tested source.

Install Python dependencies with Poetry 2.2.1 (`poetry install --with case-study`)
and web dependencies with Node 24 / Yarn 4.1.1 (`corepack yarn install --immutable`
from `web`). Run the commands in the [readiness record](docs/releases/v1-readiness.md).
Database tests must use owned disposable test resources; never supply application
data to the integration fixture, which recreates tables.

- `poetry run python -m scripts.smoke_stack --operator` exercises fixed synthetic
  observations, analytics, the web review, notes, worker CSV, monitoring and cleanup.
  Install the Playwright Chromium headless shell first. `--inject-failure worker`
  exercises an expected export timeout and resource cleanup.
- `poetry run python -m scripts.noaa_case_study --output-dir <new-directory>`
  downloads the pinned NOAA GHCNh archive for station `POMU0068545`, then validates,
  ingests/replays and describes reports in `[2010-01-01, 2010-01-12)` UTC.
  `--source-manifest <prior-output>/source/manifest.json` repeats the complete case
  from the same source bytes in a new database. An excerpt fixture is not equivalent
  to the full archive. See the [case-study runbook](docs/runbooks/noaa_case_study.md).
- `poetry run python -m scripts.recovery_drill` measures a disposable logical
  backup/restore and worker recovery workflow against proposed targets. Local
  timing results depend on the host and do not establish production RTO/RPO.

For cached case-study reproduction, compare CSVs, quality reports and analytical
JSON exactly after excluding only documented generated import IDs. Acquisition
timestamps, random resource identities and run metadata vary. Figure byte hashes
are comparable only with matching renderer/platform details; across environments
compare numerical data and labels, not binary image equality. The case study uses
no random simulation (`seed: null`). Synthetic smoke data has a fixed fixture hash.

Retain source/checksums, commands, exit statuses, JUnit, image identities, tool
versions, the clean source SHA and `scripts.release_manifest` output. Known test
skips and unsuccessful prerequisites remain visible. CI artifacts expire after
14 days unless retained elsewhere. Cite [CITATION.cff](CITATION.cff) with the exact
commit used; no DOI or published stable release is claimed.
