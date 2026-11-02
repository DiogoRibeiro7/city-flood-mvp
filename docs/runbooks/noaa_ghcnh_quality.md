# NOAA GHCNh quality characterization

The quality CLI describes one Portuguese station and a bounded historical
report-time window. It shares the [ingestion adapter](noaa_ghcnh.md)'s acquisition,
structural validation and quantitative eligibility rules. It reads source rows
before rejected values and duplicate timestamps are discarded. No database,
asset registration, credentials or new dependencies are required.

The generated [JSON](../data/ghcnh-quality-sample.json) and
[Markdown](../data/ghcnh-quality-sample.md) record an actual HTTP acquisition on
2026-11-02. They are descriptive evidence, not a pass/fail certification or a
flood case study. Source attribution, CC0 evidence and format version are in the
[source assessment](../data/real-source-assessment.md).

## Reproduce the measured window

Run from the repository root after `poetry install`. Commands are single-line
for both PowerShell and POSIX shells:

```sh
poetry run python -m floodmvp.jobs.validate_noaa_ghcnh --station-id POMU0068545 --start 2010-01-01T00:00:00Z --end 2010-01-12T00:00:00Z --expected-sha256 2010=1febfaa9832085295cb813e987de298c73298318bf6104a51abb1ba65397d1b7 --expected-cadence-minutes 360 --stale-after-minutes 1440 --json-report test-results/noaa-quality/report.json --markdown-report test-results/noaa-quality/report.md
```

Repeat with another station/window to obtain a separately identified report;
each request is at most 31 days and downloads its intersecting annual files.
Cross-year requests require a pin for each year if complete checksum pinning is
desired. The downloader retains its existing byte/row limits, retry budget and
timeouts. Checksums detect changed upstream data; a mismatch stops analysis.
Large raw annual files are not committed.

The JSON is also written to stdout. Exit 0 means characterization completed,
even if it found gaps or impossible values. It does **not** mean data passed a
release gate. Exit 2 means invalid arguments, acquisition/structural failure or
report-write failure. A failed acquisition emits `coverage: null`, a reason and
completed source evidence; it never substitutes synthetic metrics. Each output
file is replaced atomically, but the pair is not a transaction: compare the
`analysis_version` in both files if an output write fails.

On POSIX systems, new report files use mode `0644` so other users/services can
read these public-data artifacts. Replacing an existing report preserves its
access mode, including restrictive `0600` permissions. Windows uses filesystem
ACLs. Invalid timestamps/checksum syntax name the offending CLI option in the
failure report, including timestamps whose UTC conversion exceeds the supported
date range.

The analysis version hashes the report/adapter versions, station, UTC window,
policy, scope and source payload hashes. Retrieval timestamps remain in source
provenance but do not change this version. Numeric results are reproducible
for these inputs; HTTP retrieval metadata naturally differs between executions.

## Definitions and limits

| Check | Rule and interpretation |
| --- | --- |
| Row scope | `start <= report timestamp < end`, in UTC; all annual rows are structurally checked, only in-window rows are characterized. Counters distinguish whole-source rows, selected rows, unique timestamps and duplicate extras. |
| Missing vs zero | Empty six-hour fields are `missing_rainfall`. A numeric zero without trace/other disqualifying flags is `observed_zero`. `T` is trace, not a measured dry interval. Rejected observations never become zero. State counters include explicit zero counts for these core categories. |
| Duplicates | Same station/UTC timestamp with identical selected rainfall fields, flags and station metadata collapses once. Different selected fields at that timestamp form a conflict: exclude the entire group from quantitative coverage. Other meteorological fields do not participate. Raw-row issue counts include duplicate rows; timestamp states do not. |
| Impossible/invalid values | Flag negative/nonfinite rainfall, nonnumeric cells, nonfinite station coordinates/elevation, and out-of-range latitude/longitude. Inspect independent problems even in a row rejected for another reason. Do not invent a station-specific upper rainfall threshold. Other provider flags and missing metadata use the ingestion rejection policy. |
| Unit consistency | Require the exact `precipitation_6_hour` schema field and its documented bare numeric mm values. Embedded unit strings such as `2 in` or `2 mm/h` are flagged and excluded. A renamed unit/field schema fails structural validation. The provider supplies no per-row unit metadata: report `contract_only`, not independently verified units. Silent numeric rescaling cannot be detected. Never combine 6-hour and 12-hour totals. |
| Assumed reporting grid | Default 360 minutes, anchored at the Unix epoch in UTC, with slot timestamps in the requested half-open window. Report expected slots, quantitative slots, slots without quantitative rainfall and per-state counts (including absent weather reports). `--expected-cadence-minutes` changes this explicit analytical assumption, not the accumulation duration. The station's required reporting schedule has not been established. |
| Interval support and gaps | Union the six-hour accumulation intervals ending at eligible quantitative timestamps, clip to the requested window and count overlapping minutes once. Report supported/total minutes, fraction, and every unsupported interval. Unsupported means unknown. This needs no reporting-cadence assumption. |
| Window edges | An observation at `start` covers preceding time and contributes zero supported minutes inside the window. Observations at/after `end` are excluded even if their accumulations overlap the window. Thus right-edge coverage is censored by the report-time selection. This metric is support from the selected reports, not all possible rainfall information about the window. |
| Sampling | Histogram actual spacings for weather timestamps and quantitative rainfall separately. Report multiple spacings, rainfall spacings different from the assumed cadence, and rainfall timestamps off its grid. These are descriptive deviations, not proof of station failure. |
| Staleness | Compare the last weather and quantitative rainfall timestamps separately to the historical window end. Age strictly greater than the configured threshold (default 1,440 minutes) is stale. No qualifying timestamp means `no_observation_in_window`, not a fabricated age. This says nothing about present-day station operation. |
| Daily tables | UTC calendar-day intersections with the requested window. Counts use report timestamps; supported minutes use all selected accumulations, including those ending on a later day. Daily supported minutes sum to the window total. |

Quantitative eligibility does not establish passed provider QC. No interpolation,
rainfall sums across gaps, flood labels, scores or sub-hourly measurements are
generated. The existing database QA job uses regular live-telemetry assumptions;
this report does not change its flags or rules.

Weather-report sampling and freshness deliberately include conflicting
timestamps: they prove reporting activity even though their rainfall values
are ambiguous. Conflicts remain excluded from quantitative rainfall support,
sampling and freshness. The daily Markdown table includes every rejected or
conflicting state alongside the zero/positive, trace and missing categories.
For recorded fixtures, source citations label the upstream annual-file hash
and the selected excerpt hash separately.

## Observed result

The pinned 14,325,059-byte annual source contains 17,464 weather rows. Of the
529 unique timestamps in the selected 11 days, 522 have missing six-hour
rainfall, six have quantitative positive rainfall, one is trace, and zero are
observed dry intervals. No duplicate timestamps, impossible values, or embedded
unit tokens were found in the selected rows; this does not prove that numeric
units are correct independently of the source contract.

The six quantitative reports occupy **6/44 assumed six-hour slots (13.64%)**.
Their clipped, nonoverlapping accumulation support totals **30/264 hours
(11.36%)**. One report ends at the left boundary and contributes no in-window
support, explaining the different fractions. The largest unsupported interval
is 138 hours. Missing cells at ordinary weather-report timestamps are not
expected rainfall-report failures without an established station schedule.

Weather spacings were 30 minutes 526 times, 10 minutes once and 20 minutes once.
Quantitative rainfall spacings were 12, 12, 24, 36 and 144 hours (as a sorted
distribution, not chronological order). At the window end the latest weather
report was 30 minutes old and the latest quantitative rainfall was 36 hours
old: only the latter exceeds the assumed 24-hour stale threshold. The separate
trace timestamp was 2010-01-11 00:00 UTC and supplies no quantitative depth.

These findings constrain the next evaluation protocol: sparse six-hour totals
cannot validate the application's 15-minute intensity detector, and there are
no independently verified flood labels in this dataset. G5 remains open for
evaluation and a reproducible descriptive case study.

## Offline checks

```sh
poetry run python -m floodmvp.jobs.validate_noaa_ghcnh --start 2010-01-01T00:00:00Z --end 2010-01-12T00:00:00Z --fixture-manifest tests/fixtures/real_sources/noaa_ghcnh/provenance.json --json-report test-results/noaa-quality/fixture.json --markdown-report test-results/noaa-quality/fixture.md
poetry run pytest -q tests/unit/test_noaa_quality.py tests/unit/test_noaa_ghcnh.py
```

The recorded fixture is a curated noncontiguous selection. Its JSON/Markdown
snapshots deliberately contain **no station coverage, missing-interval,
sampling or freshness metrics**. The snapshot test omits only the hash of the
manifest file bytes, which can differ with Git line-ending conversion; it
retains the invariant raw PSV hash. Modified rows in unit tests are explicitly
controlled examples, never observed results. They cover missing/trace/zero,
duplicates/conflicts, overlap and boundary clipping, stale and empty windows,
irregular sampling, malformed units/schema, source failures and report outputs.

## Verification record

Local checks on 2026-11-02, using Python 3.12.10:

| Command/check | Outcome |
| --- | --- |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | Passed; 157 files |
| `poetry run mypy src scripts/export_openapi.py` | Passed; 74 source files |
| `poetry run pytest -q tests/unit --junitxml=test-results/noaa-quality/unit.xml` | 428 passed, including 29 quality cases and 38 existing adapter cases; existing Alembic `path_separator` deprecation warning |
| Pinned live CLI above | Passed; JSON/Markdown recorded; latest retrieval 2026-11-02 10:47:12 UTC |
| Independent standard-library calculation on the same hashed annual payload | Confirmed 529 selected rows, six quantitative reports, 522 missing values, 1,800 union minutes, daily totals and JSON/Markdown agreement |
| Database integration/migrations, web and full-stack smoke | Not run: no database, schema, API or web behavior changes; provider parsing/acquisition refactor covered by adapter and quality unit tests |

No hosted CI result or present-day station availability is asserted by these
local checks. The broader Python version matrix was not rerun locally.

Review follow-up on 2026-11-02: lint, formatting (157 files) and mypy (74 source
files) passed again. The full Windows Python 3.12.10 unit
suite passed **438 tests**, with three POSIX permission cases skipped and the
same Alembic warning. Both NOAA test modules passed **all 80 cases** in a
disposable Linux `python:3.12-slim` container (Python 3.12.16), including creation
with mode `0644` and replacement preserving modes `0600` and `0640`. Its repository
mount was read-only; file-mode assertions ran in the container's temporary
filesystem. No database was accessed.

The recorded live report was re-rendered with corrected labels and daily states;
its analytical values, source hashes and HTTP retrieval metadata were preserved.
The follow-up did not download new observations or claim a new live acquisition.
