# NOAA GHCNh quality report

Station: `POMU0068545`. Report timestamps: `[2010-01-01T00:00:00+00:00, 2010-01-12T00:00:00+00:00)`.

Scope: **annual_source_window**. Analysis version: `1d82741f49bc9f38bdc0af249ba679b125facd62b99c69e38d19bd060c123d5c`.

This is a descriptive characterization, not a quality pass or flood validation.

| Count | Value |
| --- | ---: |
| source_rows | 17464 |
| outside_window | 16935 |
| selected_rows | 529 |
| unique_timestamps | 529 |
| duplicate_extra_rows | 0 |
| exact_duplicate_extra_rows | 0 |
| conflicting_timestamps | 0 |
| quantitative_observations | 6 |

| State per unique timestamp | Count |
| --- | ---: |
| missing_rainfall | 522 |
| observed_positive | 6 |
| observed_zero | 0 |
| trace_rainfall | 1 |

Raw-row issues: `{}`. Examples and complete sampling histograms are in JSON.

Unit check: **contract_only**. The fixed field defines mm over six hours. PSV has no per-row unit metadata; silent unit/scale changes cannot be inferred from numbers. Other duration fields are not combined.

Quantitative interval support: **1800 / 15840 minutes (11.36%)**. Unsupported time is unknown, not dry.

Assumed 360-minute UTC grid: 6 / 44 quantitative slots; 38 without quantitative rainfall. This is an assumed schedule.

Assumed grid states: `{'missing_rainfall': 37, 'observed_positive': 6, 'trace_rainfall': 1}`.

Freshness at window end (threshold 1440 minutes):

| Series | Latest UTC | Age (minutes) | Status |
| --- | --- | ---: | --- |
| weather_reports | 2010-01-11T23:30:00+00:00 | 30.0 | within_threshold_at_window_end |
| quantitative_rainfall | 2010-01-10T12:00:00+00:00 | 2160.0 | stale_at_window_end |

Quantitative sampling: `{'timestamps': 6, 'delta_minutes_histogram': [{'minutes': 720.0, 'count': 2}, {'minutes': 1440.0, 'count': 1}, {'minutes': 2160.0, 'count': 1}, {'minutes': 8640.0, 'count': 1}], 'multiple_observed_spacings': True, 'deltas_different_from_assumed_cadence': 5, 'off_grid_timestamps': 0}`.

| Unsupported interval start | End | Minutes |
| --- | --- | ---: |
| 2010-01-01T00:00:00+00:00 | 2010-01-01T06:00:00+00:00 | 360 |
| 2010-01-01T12:00:00+00:00 | 2010-01-02T18:00:00+00:00 | 1800 |
| 2010-01-03T00:00:00+00:00 | 2010-01-03T06:00:00+00:00 | 360 |
| 2010-01-03T12:00:00+00:00 | 2010-01-04T06:00:00+00:00 | 1080 |
| 2010-01-04T12:00:00+00:00 | 2010-01-10T06:00:00+00:00 | 8280 |
| 2010-01-10T12:00:00+00:00 | 2010-01-12T00:00:00+00:00 | 2160 |

| UTC day/window start | Quantitative reports | Zero | Trace | Missing rainfall | Rejected / conflicting states | Supported / window minutes |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| 2010-01-01T00:00:00+00:00 | 2 | 0 | 0 | 46 | 0 | 360 / 1440 |
| 2010-01-02T00:00:00+00:00 | 0 | 0 | 0 | 48 | 0 | 360 / 1440 |
| 2010-01-03T00:00:00+00:00 | 2 | 0 | 0 | 46 | 0 | 360 / 1440 |
| 2010-01-04T00:00:00+00:00 | 1 | 0 | 0 | 47 | 0 | 360 / 1440 |
| 2010-01-05T00:00:00+00:00 | 0 | 0 | 0 | 48 | 0 | 0 / 1440 |
| 2010-01-06T00:00:00+00:00 | 0 | 0 | 0 | 48 | 0 | 0 / 1440 |
| 2010-01-07T00:00:00+00:00 | 0 | 0 | 0 | 48 | 0 | 0 / 1440 |
| 2010-01-08T00:00:00+00:00 | 0 | 0 | 0 | 48 | 0 | 0 / 1440 |
| 2010-01-09T00:00:00+00:00 | 0 | 0 | 0 | 48 | 0 | 0 / 1440 |
| 2010-01-10T00:00:00+00:00 | 1 | 0 | 0 | 47 | 0 | 360 / 1440 |
| 2010-01-11T00:00:00+00:00 | 0 | 0 | 1 | 48 | 0 | 0 / 1440 |

Limitations:

- Blank source QC is unverified, not passed QC; quantitative means eligible under the ingestion policy.
- Missing, rejected and trace rainfall are not observed zero; trace amounts are not quantitatively supported.
- Weather-report sampling and freshness include conflicting timestamps as reporting activity; quantitative rainfall excludes conflicts.
- Cadence and stale thresholds are declared analysis assumptions, not verified station schedules or service objectives.
- Coverage unions six-hour intervals from eligible report timestamps in [start,end). It clips the left edge and excludes reports at/after end, so the right edge is censored.
- Interval support does not resolve sub-hourly timing, establish flood events or validate detector accuracy.

Sources (CC0-1.0; Menne et al., NOAA NCEI):

- [Station-year 2010](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access/by-year/2010/psv/GHCNh_POMU0068545_2010.psv), retrieved 2026-11-02T10:47:12.192725+00:00; mode `http`; upstream SHA-256 `1febfaa9832085295cb813e987de298c73298318bf6104a51abb1ba65397d1b7`.

[Dataset DOI](https://doi.org/10.25921/jp3d-3v19); [provider format documentation](https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf).
