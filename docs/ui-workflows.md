# Operator evidence workflow

Prompt 14 extends the existing React application with a path from raw measurements
to detector output, notes, comparisons and CSV. This is decision-support software
for a demonstration, not a validated flood warning service.

## Run the demonstration

Install the locked web dependencies and Chromium, then run from the repository root:

```powershell
cd web
corepack yarn install --immutable
corepack yarn playwright install chromium --only-shell
cd ..
poetry run python -m scripts.smoke_stack --operator
```

Linux hosts may also need Playwright's `--with-deps` option. Docker Compose,
Python 3.12+ and Node 24 are required. The runner creates a UUID-named project,
loopback ports and volumes, migrates a fresh database, starts the real API,
worker and web application, then cleans up its resources on success or failure.
It never uses the host application's `.env` database. `--keep` retains this one
project for manual inspection and prints its cleanup command. `result.json`
records the API and web URLs.

The live browser assertions exercise this sequence:

1. Open the web URL with
   `/?from=2026-01-01T00:00:00Z&to=2026-01-01T01:00:00Z`.
   Keep **Stored observations**, then select `smoke_rain` using the asset selector
   or map. All three map assets and all fixture measurements are synthetic.
2. Inspect the twelve raw rain records, timestamps, values, quality flags and
   source attribution. Structural checks establish a timestamp and finite value;
   `ok` does not certify the sensor, source or hydrological accuracy.
3. Select the rain event. **Why this event fired** shows its producing run's
   threshold of 5 mm/h and minimum duration of 15 minutes. The fixture contains
   five consecutive 8 mm/h samples. **Focus asset** returns to its measurements.
   Confidence is a heuristic score, not a calibrated flood probability.
4. Select Analyst for the local demo, write a note describing source, quality,
   UTC window and limitations, and attach the asset and event. The browser verifies
   persistence through the real API. The UI role selector does not grant server
   permissions; deployed use still requires an authorized JWT.
5. Download CSV. The real worker processes the report and the browser verifies
   that its download contains the selected event. Report events use the applied
   window. Summary and hotspots remain current snapshots and are labeled accordingly.
6. For a separate synthetic comparison, apply `2026-01-02 00:00–01:00 UTC`, select
   `smoke_pipe`, choose scenario `operator-base`, then compare `operator-base`
   against `operator-test`. The fixture has values 0.5 and 1.5, a suspect-quality
   sample and a missing final comparison sample. The accessible table has eleven
   paired differences of 1; the last comparison and difference say **No sample**.
   This what-if window is not evidence for the previous day's detected rain event.

The original smoke fixture is unchanged. `seed_operator_smoke` verifies its 36
observations before adding two scenarios and 23 synthetic pipe records on the next
day. It rejects non-test targets and unexpected data. A one-second offset between
scenarios accommodates the existing timestamp-based primary key; the values still
occupy the same five-minute buckets.

## Evidence and limits

- Raw rows expose stored source, source type/ID and quality flag. Synthetic rows
  say so. NOAA GHCNh rows say recorded weather report; stored interval boundaries,
  duration and conversion explain six-hour means. Unknown sources are not promoted
  to verified observations. Legacy source defaults are metadata, not validation.
- Record checks, source quality, detector output and independent flood validation
  are distinct. The NOAA browser regression uses mocked metadata; the live demo
  uses synthetic fixtures. Real acquisition and scientific limits are documented
  in the [Porto case study](runbooks/noaa_case_study.md).
- `/v1/events/{event_id}/run` resolves the event's actual producing run, not the
  newest run or current settings. Missing historical settings remain unavailable.
  Existing runs do not record their scenario or gap policy, and current records
  may differ from the original inputs. The UI discloses this limitation; it does
  not claim an immutable replay of a past run.
- `/v1/assets/{asset_id}/observations/evidence` is a timestamp-ordered raw view,
  paginated at 100 rows by default (maximum 500), over a half-open `[from,to)`
  window. It exposes named measurement-context fields, not arbitrary lineage
  payloads or acquisition URLs. Both new reads inherit deployment admission.
  Existing observation, event, comparison, note and export contracts are preserved.
- One applied UTC window drives evidence, chart, events, comparison and report
  events. Up to 30 days can be reviewed at once. Charts request five-minute means
  with explicit gaps. Comparison nulls stay missing. Connecting lines are not
  measurements between samples; inspect the raw table. City overview values and
  report summary/hotspots remain current snapshots, outside this historical window.
- The asset selector reflects the loaded Porto map selection and its filters and
  limits. Focusing an event outside that selection reports the limitation. Events
  are capped at 50 rows. No events or measurements does not establish no flooding.
  Notes should record the reviewed window and uncertainty; CSV does not export
  raw quality/provenance columns. Saved views retain their applied UTC window;
  note share links include the current review window and linked asset/event.

## Regression and accessibility checks

Run `corepack yarn typecheck`, `corepack yarn test:security` and
`corepack yarn test:operator` in `web`, then the disposable command above.
`operator.spec.ts` drives the React application with controlled API responses:
keyboard selection, map loading, source distinctions, producing-run explanation,
interval semantics, invalid windows, sparse comparisons, evidence retry, stale
response suppression, note links, CSV failure/retry and saved historical views.

The axe scan covers the review card, event explanation, notes form and comparison
panel for WCAG A/AA rules. Native labels, table headings, focus outlines, pressed
states and live error/status regions support inspection. This is not a whole-app
accessibility certification or a manual screen-reader usability assessment.

`operator_live.spec.ts` uses the disposable stack without mocked API responses.
Screenshots come from that functioning application and explicitly show synthetic
data. They and the downloaded CSV live under `test-results/web/operator-live/`;
traces are retained on failure. Mocked tests use `test-results/web/operator/`.
Stack logs and cleanup results are under `test-results/smoke/` by default, or the
chosen `--artifacts` parent. CI retains these artifacts separately.

Database integration tests cover ordering/pagination, non-finite values,
quality/context preservation, scenario isolation, missing resources, window/limit
validation and resolving the producing run despite a newer run. Existing security
tests enumerate the new routes, and the public OpenAPI snapshot includes both reads.

## Observed local verification — 2026-11-02

Before the implementation commit, Ruff checks/formatting (173 files), mypy
(77 source files), web typecheck/build and actionlint passed. Python 3.12 ran
608 unit tests with three existing Windows-only skips. Python 3.14 in disposable
Timescale/PostGIS resources ran all 54 integration/migration tests successfully.
The five controlled operator browser tests and two credential tests passed;
the scoped axe audit reported no violations. Browser: Chromium 145 / Playwright 1.58.2.

The real stack run `city-flood-smoke-d30712d22322` passed in 176.156 seconds,
including the 23.7-second live browser workflow, queue/CSV, scheduler, monitoring
and ingestion/export failure regressions. Cleanup completed for this stack and
the separate database test project `city-flood-smoke-c7f6b58aa5d8`. Logs are under
`test-results/operator-stack/` and `test-results/operator-postgres/` locally.
An earlier stack run failed at migrations because socket readiness accepted
PostgreSQL's temporary bootstrap server. Its resources were cleaned up; the
smoke runner and health check now require TCP readiness.

Non-fatal tooling output remains: the existing Alembic path-separator deprecation,
Recharts' initial pre-measurement size warning and Vite's large-bundle notice.
These checks do not replace the final release-candidate matrix or hosted CI results.

The smoke workflow was repeated from clean implementation commit
`58a9d2b19df5fa526e65d55b61b2fef3c45ac916`. Project
`city-flood-smoke-a58284aee8eb` passed in 161.188 seconds, including its 11.3-second
live browser test; cleanup completed. The [retained screenshots](screenshots/README.md)
come from this run. Its local logs are under `test-results/operator-clean/`.
The subsequent review also fixes selection surviving an empty map filter, with
an additional controlled browser regression; this does not change the captured path.
All six operator browser cases and the scoped axe audit passed after that fix,
and web typecheck passed again. JUnit output paths now resolve to the root
`test-results/web/` artifact directory used by CI.
