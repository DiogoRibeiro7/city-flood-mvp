# NOAA GHCNh quality report

Station: `POMU0068545`. Report timestamps: `[2010-01-01T00:00:00+00:00, 2010-01-12T00:00:00+00:00)`.

Scope: **selected_rows_only**. Analysis version: `bb244d7884d1bb4e78ce33daf536712076281396ec8ba2586a809296c6748b82`.

This is a descriptive characterization, not a quality pass or flood validation.

| Count | Value |
| --- | ---: |
| source_rows | 6 |
| outside_window | 0 |
| selected_rows | 6 |
| unique_timestamps | 6 |
| duplicate_extra_rows | 0 |
| exact_duplicate_extra_rows | 0 |
| conflicting_timestamps | 0 |
| quantitative_observations | 2 |

| State per unique timestamp | Count |
| --- | ---: |
| missing_rainfall | 3 |
| observed_positive | 2 |
| observed_zero | 0 |
| trace_rainfall | 1 |

Raw-row issues: `{}`. Examples and complete sampling histograms are in JSON.

Unit check: **contract_only**. The fixed field defines mm over six hours. PSV has no per-row unit metadata; silent unit/scale changes cannot be inferred from numbers. Other duration fields are not combined.

Coverage, missing intervals, sampling and freshness: **not assessed for selected rows**.

Limitations:

- Blank source QC is unverified, not passed QC; quantitative means eligible under the ingestion policy.
- Missing, rejected and trace rainfall are not observed zero; trace amounts are not quantitatively supported.
- Cadence and stale thresholds are declared analysis assumptions, not verified station schedules or service objectives.
- Coverage unions six-hour intervals from eligible report timestamps in [start,end). It clips the left edge and excludes reports at/after end, so the right edge is censored.
- Interval support does not resolve sub-hourly timing, establish flood events or validate detector accuracy.
- Selected fixture rows are noncontiguous; station coverage, missing intervals, sampling and freshness are not assessed.

Sources (CC0-1.0; Menne et al., NOAA NCEI):

- [Station-year 2010](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2010/psv/GHCNh_POMU0068545_2010.psv), retrieved 2026-10-31T10:26:51.355574+00:00; mode `recorded_fixture`; SHA-256 `8f38fcb576a56d697acbd85868ffa7a7d0d77d536bd4f61647d25459682f0385`.

[Dataset DOI](https://doi.org/10.25921/jp3d-3v19); [provider format documentation](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf).
