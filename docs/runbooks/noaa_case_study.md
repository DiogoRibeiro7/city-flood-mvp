# Reproduce the Porto historical case study

This case study follows the approved [source assessment](../data/real-source-assessment.md):
NOAA NCEI GHCNh station `POMU0068545` (Porto / Pedras Rubras), with report
timestamps in `[2010-01-01T00:00Z, 2010-01-12T00:00Z)`. It is descriptive.
There are no independently verified flood labels or reviewed event-free periods
in these inputs, so no prediction accuracy or warning lead time is reported.

## One command after setup

Use a Git checkout, Python 3.12, Poetry, and Docker running Linux containers.
From the repository root, install the locked optional plotting dependencies:

```sh
poetry install --with case-study
```

Then reproduce the full acquisition-to-report workflow with:

```sh
poetry run python -m scripts.noaa_case_study --output-dir test-results/porto-case
```

Choose a **new output directory** each time; the runner refuses existing paths.
It downloads the approved 14 MB annual station file, checks its pinned SHA-256,
validates all source rows, characterizes the selected window, and normalizes the
same bytes for ingestion. A changed upstream file fails the run; do not replace
the pin without assessing the new version and updating its evidence.

The runner creates a labelled, disposable TimescaleDB/PostGIS container using
an immutable image digest. It binds a random loopback port, waits for a real
authenticated TCP connection, creates a random test child database, and applies
the repository's migrations. It inserts the observations using `persist_batch`,
replays the batch, verifies both import audits and unchanged lineage, and reads
the committed observations back for analysis. It does not read `DATABASE_URL` or
require application services. The child database is dropped and the owned
container and its anonymous volumes are removed on exit, including failures.
The image must be available locally or downloadable from the registry.

The first run may download the database image. Source downloads use the adapter's
bounded attempts, timeout, size and row limits; database readiness has a 90-second
deadline and migration execution a 120-second limit. A failure exits nonzero and
writes a failed manifest, with no successful-case claim. `resources.json` records
the exact container ID, ownership label and cleanup outcome without credentials.
After a hard process termination, inspect that file and verify the full ID and
`city-flood.case-study` label before manually removing a leftover container.

## Outputs and interpretation

| Artifact | Contents |
| --- | --- |
| `manifest.json` | Run status, source URL/hash/retrieval metadata, code revision and dirty flag, lock hash, package/Python versions, configuration, seed, image identity, cleanup and artifact hashes |
| `source/manifest.json`, `source/*.psv` | Exact source bytes and original HTTP provenance for offline reproduction; ignored large local artifacts |
| `case-study.json` | Descriptive interval analytics and verified ingestion/replay receipts, dataset version and migration revision |
| `quality.json`, `daily.csv` | Missing/trace/zero states, sampling, historical freshness, assumed-grid availability and clipped interval support |
| `observations.csv` | Full six-hour intervals, depths/mean rates, source row/hash and unverified QC |
| `timeline.csv` | Rainfall intervals, trace reports and unsupported periods for incident review; no confirmed flood incidents |
| `rainfall.svg`, `rainfall.png`, `report.md` | Figure and readable results with source attribution and interpretation limits |

The analytics classify quantitative six-hour depths as positive (`depth > 0 mm`)
or observed zero. They do not estimate rainfall timing within an interval,
interpolate gaps, calculate storm totals across gaps, or infer flood events.
The first report ends exactly at the window's left boundary; its full depth
remains visible, but contributes zero in-window support. Reports at or beyond
the right boundary are excluded. Trace amounts and unsupported periods remain
unknown, never zero or dry. Blank provider QC remains unverified.

The existing 15-minute `rain_mmph` detector is explicitly **not run** on
`rain_6h_mean_mmph`. Six-hour means cannot establish its intensity/duration
criteria. Precision, recall, false alarms per station-day, confirmed incident
count and lead time are null, with reasons. Any future comparison must follow
the [independent-event protocol](../evaluation/event-protocol.md).

No stochastic analytics or simulated data are used: `seed` is null. Random
resource names and import IDs are administrative identities, not data seeds.
The source version is identified by GHCNh format version 1.1.0, annual payload
SHA-256, HTTP metadata and the ingestion dataset version. The manifest records
the actual retrieval date, not the historical observation dates.

## Offline reproduction and small fixture check

To replay the complete source cached by a previous run without contacting NOAA:

```sh
poetry run python -m scripts.noaa_case_study --source-manifest test-results/porto-case/source/manifest.json --output-dir test-results/porto-case-replay
```

This validates the exact full annual payload against the approved checksum,
preserves the original HTTP retrieval metadata and records cache use separately.
Each replay still creates a fresh disposable database. Keep the source manifest
beside its PSV file. An excerpt cannot be substituted for the complete archive.

For a small pipeline demonstration using only committed, noncontiguous rows:

```sh
poetry run python -m scripts.noaa_case_study --fixture-manifest tests/fixtures/real_sources/noaa_ghcnh/provenance.json --output-dir test-results/porto-case-fixture
```

This explicitly reports `selected_rows_only`; station coverage, sampling,
freshness and missing intervals are not assessed. It does not reproduce the
full-window quantitative results.

## Reproducibility and retention

For the same cached source and locked environment, compare CSV contents and
analytic JSON values exactly, and SVG/PNG hashes when the renderer environment
also matches. Run timestamps, acquisition mode, resource identities and import
IDs vary. A fresh HTTP download also changes retrieval metadata; the dataset
version remains stable for unchanged source bytes/configuration. Across operating systems or renderer
versions, compare figure data/labels and numeric tables; binary image equality
is not promised. Preserve the recorded code revision and lock file when
reproducing an older result, and inspect the dirty flag before citing it.

NOAA's archive reuse evidence and attribution are recorded in the source
assessment (CC0-1.0; Menne et al., DOI `10.25921/jp3d-3v19`). Commit only the small
report, figure, tables and manifests under `docs/case-studies/porto-2010/`.
Keep annual raw downloads, database state, credentials and large run logs under
ignored local output directories. `.gitattributes` preserves the LF bytes of
the checksummed text artifacts on Windows checkouts.

## Verification commands

```sh
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src scripts/export_openapi.py scripts/noaa_case_study.py
poetry run pytest -q tests/unit
poetry run pytest -q tests/migrations/test_noaa_case_study_postgres.py tests/integration/test_noaa_ghcnh_postgres.py
```

The last command requires `TEST_DATABASE_URL` pointing to an explicitly isolated
test server; use the [database test isolation rules](migrations.md). The
integration fixture resets its supplied test database. The case-study runner
itself needs no database URL and always provisions its own resources.
