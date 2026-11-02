# Event-onset evaluation protocol

**No real-world accuracy or warning lead time is established by this change.**
The selected NOAA archive has no independently verified flood labels. Its
six-hour rainfall totals cannot validate a 15-minute intensity detector. The
[quality report](../runbooks/noaa_ghcnh_quality.md) measures only 30/264 hours of
quantitative interval support from selected reports, with an assumed reporting
grid. Do not turn that window into a fully reviewed negative period, treat
missing rain as dry, or enlarge a tolerance until coarse data appears to validate
the detector. The [descriptive case study](../runbooks/noaa_case_study.md) now
reproduces this window through ingestion and interval analytics. Independent
real-event validation remains open; the case study reports no accuracy scores.

`floodmvp.analytics.evaluation.evaluate_events` implements protocol version 1.
It is a pure, database-free function returning JSON-compatible evidence, matches,
counts, exclusions and scores. It evaluates **event onsets**, not event duration,
peak severity, inundated area or calibrated probabilities. The controlled
examples below and in tests establish software behavior only.

## Existing detector scope

| Output | Meaning and evaluation constraint |
| --- | --- |
| `detect_rain_events` | Sustained `rain_mmph` threshold exceedance; defaults are 5 mm/h, 15 minutes and a five-minute maximum gap. A rain episode is not a flood. |
| `detect_overflow_events` | Sustained pipe `fill_ratio` exceedance; defaults are 1.0, ten minutes and a five-minute maximum gap. A fill-ratio proxy needs independent overflow evidence before it validates actual overflow. |
| `detect_threshold_events` | Returns `(start, end, peak)`. The final sample is extended using observed cadence; `start` is a retrospective onset, not the time an alert became available. |
| `run_city_analytics` / `AnalyticsEvent` | Currently selects the first rain gauge, limits pipes, and stores at most three overflow events per pipe. `created_at` is database insertion time. These stored summaries are not an exhaustive detection log or proof of warning delivery. Evaluate the complete pure detector output for a declared station set/run, or archive an exhaustive issuance log. |
| Existing `confidence` and calibration recommendations | Heuristic coverage/signal scores and telemetry percentiles. They are neither calibrated event probabilities nor independent event labels. |

Keep `rain`, `overflow` and `flood` separate. The evaluator rejects mixed event
types in one call. Use a stable station/asset identifier and an adjudicated
spatial mapping; it never matches another station merely because times overlap.
For a multi-asset incident, predefine one evaluation unit or separate station
labels with a shared incident ID in the evidence registry. Avoid presenting
correlated station labels as independent flood events.

## Human label and review protocol

1. **Freeze the target and study design.** Record the physical event definition,
   station set, UTC study period, source and detector versions, thresholds,
   duration/gap rules, input quality exclusions and event separation rule. One
   physical episode gets one reference ID even if several reports describe it.
   Tune parameters on development stations/periods, then freeze the held-out
   evaluation period before examining its results. Persist the actual detector
   configuration and code revision alongside the evaluator report.
2. **Collect independent evidence.** Use dated observation/incident records with
   a defensible relationship to the target location and event type. Preserve
   source URL or local reference, retrieval date, permitted excerpt/hash/version
   and the relevant page/record. Thresholds reapplied to the detector's input,
   synthetic generator schedules, and the detector's own incidents are not
   independent truth. A rainfall measurement alone cannot confirm inundation.
3. **Review positives and negatives.** Reviewers record confirmed events,
   explicitly reviewed event-free periods, and unknown/disputed periods.
   Absence of a news report or a label row is not evidence of no event. Review
   should be independent of detector output where practical; record blinding
   limitations and disagreements. A second reviewer adjudicates event identity,
   station mapping and timing before freezing the label set.
4. **Record uncertainty.** The label registry retains onset lower/upper bounds,
   end time if known, original time zone and UTC conversion, timing resolution,
   spatial uncertainty, evidence strength, reviewer identities and adjudication
   date. The evaluator accepts one agreed onset per confirmed reference plus
   `evidence_ref`, `reviewer` and `label_origin`. It does not interpret uncertain
   intervals or authenticate reviewer claims. Do not convert a date-only flood
   report to an invented midnight onset. Keep ambiguous cases in the exclusion
   registry and remove their unresolved periods from reviewed windows; report
   the resulting selection rather than silently discarding difficult positives.
5. **Attest complete observation periods.** A `ReviewedWindow` means every target
   onset in `[start,end)` was reviewed, **and** the detector's required input and
   complete output were available there. Its `review_ref` points to that audit,
   including negative evidence and input availability. Split around outages,
   disputed timing and unreviewed periods. This is stricter than NOAA rainfall
   interval support. Merely having downloaded a station-year is insufficient.
6. **Freeze and archive.** Version the label registry, exclusions, mapping and
   review-window audit. Use `human_reviewed` only for that attested evidence.
   The evaluator requires nonempty evidence/reviewer references and rejects
   mixing this origin with `controlled` labels. These checks cannot verify
   independence or correctness; its report states that human review is
   caller-attested. Re-review any subsequent revisions before comparing scores.

## Matching and boundary policy

The caller must supply both nonnegative tolerances. There is no calibrated
default. For prediction onset `p`, reference onset `r`, early tolerance `E` and
late tolerance `L`, a candidate pair satisfies **`-E <= p - r <= L`**, inclusively,
within the same station, event type and continuous reviewed period. Tolerance
is a matching allowance, not a claim that an alert was available that early.
Select it from the use case and verified timing resolution before seeing test
scores; publish sensitivity analyses for a predeclared set of tolerances.

Overlapping or adjacent reviewed windows are unioned per station. True gaps
remain gaps. For each union `[a,b)`, eligible prediction onsets occupy
**`[a + L, b - E)`**. This ensures all reference onsets that could match a scored
prediction lie in reviewed time. Short periods with no interior contribute no
exposure. Predictions outside reviewed windows are `unreviewed`; those inside
the excluded edge strips are `boundary_tolerance`. Neither counts as a false
alarm, and both remain listed in the report.

Every reference onset inside a reviewed union must have its entire candidate
prediction horizon `[r-E, r+L]` inside that eligible prediction interval. In
particular, the right endpoint must be strictly before its exclusive end.
Otherwise evaluation **fails**, naming the reference and requesting more
reviewed context. This deliberate conservative rule avoids dropping known
positives or counting unobservable boundary matches as misses. Extend the
joint review/availability evidence before scoring; do not remove the positive
just to pass validation. References wholly outside reviewed windows are listed
as unreviewed and have no score contribution. No match crosses an unknown gap.

Example of padding: for `E=L=5 minutes`, a reviewed day `[00:00,24:00)` has
prediction support `[00:05,23:55)`, and scored references require onsets from
00:10 inclusive to 23:50 exclusive. This is a definition of the eligible sample,
not a station service objective. Report excluded periods and study coverage.

Within each eligible group, sort onsets and then event IDs; pair the earliest
feasible prediction and reference. Too-early predictions become false alarms;
too-late references become misses. This gives maximum match cardinality for
the fixed onset-tolerance rule and deterministic ties. It does not optimize
closest timing or best lead time. One prediction can match one reference only.
Additional alerts for an already matched episode remain false alarms. Repeated
IDs are rejected; distinct IDs with identical onset remain distinct alerts.
Deduplicate repeated analytics runs before evaluation using an auditable rule.

## Scores and lead time

Let `TP` be matched pairs, `FP` unmatched eligible predictions and `FN` unmatched
eligible references. Aggregate scores use summed counts across stations; the
report also includes per-station counts and denominators.

| Quantity | Definition |
| --- | --- |
| Precision | `TP / (TP + FP)`; `null` when there are no eligible predictions. |
| Recall / detection probability | `TP / (TP + FN)`; `null` when there are no eligible references. |
| Scored station-days | Sum of eligible prediction-support durations across stations, divided by 86,400 seconds. Overlaps count once per station; event types are evaluated separately. Includes reviewed event and event-free time. |
| False alarms per station-day | `FP / scored_station_days`; `null` with no eligible exposure. This is an onset rate, not false-alarm duration, false-alarm ratio `FP/(TP+FP)`, or probability of false detection `FP/(FP+TN)`. No arbitrary true-negative time bins are invented. |
| Onset error | `prediction.onset - reference.onset` in seconds; negative means the estimated onset was early. |
| Warning lead time | `reference.onset - prediction.issued_at` in seconds for each matched pair with a recorded issuance timestamp. Positive means advance warning, negative means late warning. Missing issue times remain `null`; they are never replaced with the event onset. |
| Median lead time | Median over matched pairs with issue times, alongside sample count and count without issue times. Interpret conditionally on detected events and available logs; it excludes misses and says nothing about warning delivery latency. |

`status=not_evaluated` and null score denominators are the correct result when
no eligible reviewed time exists. A fully reviewed negative period can support
a false-alarm rate even with no positives; its recall is still undefined. Do
not interpret zero eligible observations as perfect performance.

Counts, excluded time, timing uncertainty and reviewer limitations must precede
claims about scores. No confidence intervals are fabricated: event and station
dependence can invalidate simple independent-binomial assumptions. With enough
independent storms, predeclare a storm/station-block resampling design and
report intervals, sample size and sensitivity to label adjudication. A small
hand-picked window supports a descriptive case study, not municipal readiness.

## Reusable function example (controlled data only)

This code is a software example, not Portuguese observations or real accuracy.
Run it with `poetry run python` from the repository root:

```python
import datetime as dt
import json
from floodmvp.analytics.evaluation import (
    Detection, MatchPolicy, ReferenceEvent, ReviewedWindow, evaluate_events,
)

day = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
onset = day + dt.timedelta(hours=12)
report = evaluate_events(
    [Detection("controlled-p1", "test_A", "rain", onset - dt.timedelta(minutes=3),
               issued_at=onset + dt.timedelta(minutes=1))],
    [ReferenceEvent("controlled-r1", "test_A", "rain", onset,
                    "controlled:example-v1", "test-author", "controlled")],
    [ReviewedWindow("test_A", "rain", day, day + dt.timedelta(days=1),
                    "controlled:review-v1", "test-author", "controlled")],
    event_type="rain",
    label_origin="controlled",
    policy=MatchPolicy(dt.timedelta(minutes=5), dt.timedelta(minutes=5)),
)
assert report["matches"][0]["onset_error_seconds"] == -180
assert report["matches"][0]["lead_time_seconds"] == -60
print(json.dumps(report, indent=2, allow_nan=False))
```

For pure detector output, construct a `Detection` from each returned `start`
and leave `issued_at=None` unless an actual issuance log exists. Use the full
output, not the capped database summary. Tests exercise both current detectors
this way with explicitly controlled labels. No detector behavior, database
model, public API or OpenAPI schema is changed.

The report embeds normalized input events and evidence windows, configuration,
protocol version, exclusions, matches, per-station and aggregate results. Its
`evaluation_id` hashes those inputs/configuration deterministically; input order
and equivalent UTC offsets do not affect it. Archive code revision, detector
configuration and source/label artifact hashes separately; an evaluation ID
cannot prove the evidence is true or capture an unrecorded detector setting.

## Verification and methodological context

```sh
poetry run pytest -q tests/unit/test_event_evaluation.py tests/unit/test_threshold_events.py
```

Tests cover reviewed negatives versus unknown periods, one-to-one duplicate
penalties, temporal edges, overlap/gap exposure, station separation, padding
failures, UTC offsets, missing and signed lead times, metadata validation and
both existing detector outputs. A small exhaustive matching oracle checks the
chronological algorithm against 120 deterministic controlled cases.

Local verification on 2026-11-02, Python 3.12.10:

| Check | Outcome |
| --- | --- |
| `poetry run ruff check .` | Passed |
| `poetry run ruff format --check .` | Passed; 159 files |
| `poetry run mypy src scripts/export_openapi.py` | Passed; 75 source files |
| `poetry run pytest -q tests/unit --junitxml=test-results/event-evaluation/unit.xml` | 471 passed, including 33 new evaluation cases; three existing POSIX permission cases skipped on Windows; existing Alembic `path_separator` warning |
| Documentation example and local Markdown links | Passed; the example emitted controlled evidence only |
| Database integration/migrations, web and full-stack smoke | Not run: this change adds a pure evaluation module and documentation, with no database, detector, API or web behavior changes |

The broader Python/OS matrix was not rerun locally. These checks make no claim
about hosted CI or hydrological accuracy.

The [Hong Kong Observatory's verification overview](https://rsmc.hko.gov.hk/nowcast/verification.html)
distinguishes detection probability, false-alarm ratio and false-detection
probability, and treats warning timeliness as a separate concern.
[ECMWF's discussion of displacement penalties](https://www.ecmwf.int/en/about/media-centre/science-blog/2023/verifying-high-resolution-forecasts)
explains why small timing/location errors affect verification and why scale
matters. These inform the terminology and explicit tolerance requirement;
the station-onset matching, padding and exposure rules above are this project's
declared protocol, not an implementation of either organization's operational
verification system. No hydrological accuracy score is reported here.
