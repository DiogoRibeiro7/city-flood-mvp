# Historical Portuguese rainfall ingestion

The [source assessment](../data/real-source-assessment.md) selects NOAA NCEI
GHCNh station `POMU0068545` (Porto / Pedras Rubras). The provider adapter uses
the shared `IngestRecord` contract and rainfall unit converter. It implements
the documented GHCNh 1.1.0 format; `format_version` identifies that parser
contract, not a claim that the upstream archive is immutable.

Only **six-hour accumulated rainfall** is ingested, as the distinct metric
**`rain_6h_mean_mmph`**. A depth in mm is divided by six to give the mean over
its recorded interval. The original depth, UTC start/end times, station
coordinates and source attributes remain in each observation's lineage.
The metric includes the interval because the existing database key is
`(asset_id, metric, ts)`. Twelve-hour totals remain outside this stream.
These rates are not sent to the existing `rain_mmph` detector and do not
validate its 15-minute intensity threshold. River-level ingestion, event
labels and real-event validation remain outstanding. The
[quality report](noaa_ghcnh_quality.md) and
[evaluation protocol](../evaluation/event-protocol.md) describe measured interval
support and the requirements for scoring detector output.

## Preview without a database

Run from the repository root with the installed Poetry environment. These
single-line commands work in PowerShell and POSIX shells.

The recorded six-row fixture needs no network, credentials, assets, settings
or database connection:

```text
poetry run python -m floodmvp.jobs.ingest_noaa_ghcnh --asset-id porto_ghcnh_pedras_rubras --city-id porto_real --start 2010-01-01T00:00:00Z --end 2010-01-12T00:00:00Z --fixture-manifest tests/fixtures/real_sources/noaa_ghcnh/provenance.json --dry-run --report test-results/noaa-ingestion/offline.json
```

Expected: 6 received, 2 accepted, 3 missing rainfall amounts and 1 trace
excluded, 0 inserted. A fixture is a curated excerpt, not a complete time
series. Its manifest's SHA-256 and byte count are checked before parsing;
lineage distinguishes the fixture hash from the original station-year hash.

For the real historical window, use the recorded source checksum:

```text
poetry run python -m floodmvp.jobs.ingest_noaa_ghcnh --asset-id porto_ghcnh_pedras_rubras --city-id porto_real --start 2010-01-01T00:00:00Z --end 2010-01-12T00:00:00Z --expected-sha256 2010=1febfaa9832085295cb813e987de298c73298318bf6104a51abb1ba65397d1b7 --dry-run --report test-results/noaa-ingestion/live.json
```

On **2026-11-01**, this command downloaded the same 14,325,059-byte source
assessed on October 31. It read 17,464 weather rows, of which 529 had report
timestamps in the window: **6 accepted**, **522 missing rainfall amounts**,
**1 trace**, **0 duplicates**. See the recorded
[live dry-run report](../data/ghcnh-ingestion-sample.json). These are parser
counts, not a station coverage percentage or independent quality assessment.
Weather rows with an empty six-hour field are not dry observations.

Dry run is the default even when `--dry-run` is omitted. It creates no import
audit row and never opens a database. The supplied city/asset names are only
prospective destinations: `asset_validation: "not_checked"` makes that limit
explicit. The report is always printed as JSON and optionally written by
atomic replacement to `--report`. A failed run returns exit code 2 and a
failure report; success returns 0. `--help` lists the options.

## Boundaries and rejection policy

- `--start` is inclusive and `--end` exclusive, applied to **report timestamps**.
  Both require explicit offsets and are normalized to UTC. The window must
  be positive and at most 31 days; a year boundary fetches two station-year
  chunks. An accumulation can begin before the report window.
- Requests use the fixed official HTTPS station-year URL and validated
  Portuguese station IDs. Redirects are rejected. Each chunk is limited to
  20,000,000 decoded bytes and 100,000 data rows; large historical periods
  require separate bounded requests. Raw annual files are not committed or
  automatically cached by the CLI.
- HTTP operations have a 30-second timeout and a 90-second per-chunk budget
  checked between reads and attempts. An in-progress read may take its timeout
  before the budget is rechecked. There are at most three attempts, with
  exponential backoff of 0.5 then 1 second. Transport errors and HTTP
  408/429/500/502/503/504 are retried. Numeric and HTTP-date `Retry-After`
  values are respected when within the remaining budget and 30-second wait
  limit; longer waits stop the run. HTTP 404 is a failure, not an empty year.
- Interrupted response bodies are discarded before retry. All chunks must
  be acquired and structurally validated before any database access. A later
  network or parsing failure cannot write an earlier successful chunk.
- Missing/duplicate columns, wrong-width rows, invalid encoding/timestamps,
  a different station/year and conflicting duplicate reports abort the batch.
  Exact duplicates of the selected rainfall fields/metadata are counted once.
- Empty rainfall is rejected as `missing_rainfall`. Measurement code `T` is
  reported as `trace_rainfall` and excluded from numeric ingestion; it is not
  converted into observed zero. An unflagged numeric zero is retained.
  Nonfinite/negative rainfall, invalid coordinates, nonblank measurement/QC
  codes and incomplete source metadata have separate rejection counts.
  The conservative first adapter excludes **all nonblank QC codes**, including
  codes that might be acceptable under a future source-specific policy.
- Accepted values with blank source QC retain `quality_flag: "unverified"`.
  Acceptance only establishes this parser's contract, not physical plausibility
  or calibration. Original measurement/QC/report/source/source-station codes
  are retained in lineage. Rejected rows are counted; raw bytes and flags can
  be inspected in the licensed fixture or the checksummed upstream file.

`source_rows = received + outside_window`, and
`received = accepted + rejected + duplicates`. Database `existing` counts
refer to already-stored accepted records and are separate from input duplicates.

## Write and rerun

Configure `DATABASE_URL` in the process environment for the intended database;
the CLI never chooses a test database automatically. Review the dry-run report
first. The destination city and asset must already exist, belong together,
and represent the actual station rather than a synthetic drainage asset.
The asset's `props` must explicitly include:

```json
{"source": "noaa_ghcnh", "station_id": "POMU0068545"}
```

The verified station coordinates are latitude 41.23, longitude -8.68,
elevation 79 m. Provision/map the asset through the existing operator workflow;
this CLI creates neither cities nor assets. City/asset names in the preview
examples are illustrative and are not proof of an existing mapping.

Once that mapping and database are configured, replace `--dry-run` with
`--write` in the historical command. `--write` and `--dry-run` are mutually
exclusive. Writes verify city membership and station mapping, lock the asset,
and persist all observations plus a `DatasetImport` audit in one transaction.
Database lock/statement timeouts are 5/30 seconds respectively. Errors roll
back the entire import; no existing observations are overwritten.

Reruns leave identical observations unchanged and report them as `existing`.
Each successful write attempt creates an audit row, including a replay with
zero inserts. Original observation provenance/import IDs stay intact. The
data version hashes the station, UTC window, metric, adapter version and
source chunk hashes; retrieval times are excluded from that version.

Changes to observed depth, interval, flags or station metadata at an existing
key produce a conflict and roll back new rows and the audit. Review a changed
archive or incorrect mapping explicitly; do not delete observations merely
to bypass a conflict. If a whole-file hash changes but the selected
observations are identical, a run without the old pin can record a new audit
version and retain the original observation lineage. Use one
`--expected-sha256 YEAR=HASH` per year to require byte-identical inputs.
A checksum mismatch fails before persistence. No automatic revision approval
or overwrite option is provided.

If saving the report file fails after a committed write, stdout and the
database audit still describe the committed outcome; exit code 2 signals
the report-file failure. A rerun remains safe.

## Attribution and verification

Menne, Matthew J., et al. (2023), *Global Historical Climatology Network-Hourly
(GHCNh)*, NOAA NCEI, [doi:10.25921/jp3d-3v19](https://doi.org/10.25921/jp3d-3v19).
Subset: `POMU0068545`, January 2010 reports; source assessed 2026-10-31 and
accessed for this ingestion verification on 2026-11-01. The
[dataset-specific CC0 statement](https://www.ncei.noaa.gov/metadata/geoportal/rest/metadata/item/gov.noaa.ncdc:C01688/xml)
permits the recorded fixture; retain its provenance and citation with copies.
Converted mean rates are derived values and imply no NOAA endorsement.

Local verification on Python 3.12.10:

| Check | Observed result |
| --- | --- |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | Passed; 154 files |
| `poetry run mypy src scripts/export_openapi.py` | Passed; 72 source files |
| Backend suites, with guarded disposable `TEST_DATABASE_URL` for integration | 399 unit tests passed in the final `poetry run pytest -q tests/unit` run; 44 integration tests passed in the combined `poetry run pytest -q tests/unit tests/integration` run. Existing Alembic `path_separator` warning. |
| Migrated disposable child DB, real CLI write | Six accepted/inserted records; complete lineage and persisted audit report |
| Same real CLI rerun | Zero inserts, six existing; original rows retained |
| Fixture replay against those real observations | Zero inserts, two existing |
| Concurrent provider writes / conflicting revision / wrong city or unmapped asset | Automated PostgreSQL tests passed; single insertion or whole-transaction rollback as appropriate |
| Web, full-stack smoke, separate migration regression suite, other Python versions | Not rerun; no UI/API/schema changes. The CLI proof itself upgraded a fresh child DB through all migrations to `0018_ingest_expiry`. |

The CLI proof left six observations and three audit rows in the disposable
child database, then dropped that child. The owned test container was also
stopped and removed after verification. Local evidence is under ignored
`test-results/noaa-ingestion/`; unit tests use the permitted fixture and mock
HTTP only. No hosted CI result or detector accuracy is asserted here.

## Quality characterization

The [quality CLI](noaa_ghcnh_quality.md) adds JSON/Markdown reports for missing
intervals, duplicates, impossible values, sampling, historical freshness and
unit-contract limitations. It shares the acquisition/parser rules above and
distinguishes missing, trace and observed zero rainfall before aggregation.
