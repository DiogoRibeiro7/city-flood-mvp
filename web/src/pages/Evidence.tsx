import { useEffect, useState } from "react";
import {
  fetchEventRun,
  fetchObservationEvidence,
  ObservationEvidence,
} from "../api";

export type ReviewWindow = { from: string; to: string };
export const utc = (ts: string) =>
  new Date(ts).toISOString().replace("T", " ").replace(".000Z", " UTC");
export const sample = (value: number | null) =>
  value === null || !Number.isFinite(value) ? "No sample" : String(value);

export function WindowControls({
  window,
  onApply,
}: {
  window: ReviewWindow;
  onApply: (value: ReviewWindow) => void;
}) {
  const [from, setFrom] = useState(window.from.slice(0, 16));
  const [to, setTo] = useState(window.to.slice(0, 16));
  const [error, setError] = useState("");
  useEffect(() => {
    setFrom(window.from.slice(0, 16));
    setTo(window.to.slice(0, 16));
  }, [window]);
  return (
    <form
      aria-label="Review time window"
      onSubmit={(event) => {
        event.preventDefault();
        const start = new Date(`${from}Z`),
          end = new Date(`${to}Z`);
        if (
          !Number.isFinite(+start) ||
          !Number.isFinite(+end) ||
          end <= start
        ) {
          setError("Enter a valid UTC window with the end after the start.");
          return;
        }
        // Matches the bounded 5-minute gap grid in the observations API.
        if (+end - +start > 30 * 86400000) {
          setError("Review up to 30 days at a time.");
          return;
        }
        setError("");
        onApply({ from: start.toISOString(), to: end.toISOString() });
      }}
    >
      <div className="asset-meta">
        <label>
          From (UTC)
          <input
            type="datetime-local"
            required
            value={from}
            onChange={(e) => setFrom(e.target.value)}
          />
        </label>
        <label>
          To (UTC)
          <input
            type="datetime-local"
            required
            value={to}
            onChange={(e) => setTo(e.target.value)}
          />
        </label>
        <button type="submit">Apply window</button>
      </div>
      {error && <p role="alert">{error}</p>}
      <p className="evidence-hint">
        Applied: {utc(window.from)} → {utc(window.to)}. End excluded. This
        window controls measurements, events, comparisons and report events.
      </p>
    </form>
  );
}

function sourceLabel(row: ObservationEvidence) {
  if (row.source === "synthetic") return "Synthetic data";
  if (row.source === "noaa_ghcnh") return "Recorded weather report (NOAA)";
  return "Source not independently verified";
}

export function ObservationEvidencePanel({
  assetId,
  metric,
  window,
  scenarioId,
}: {
  assetId: string;
  metric: string;
  window: ReviewWindow;
  scenarioId: string;
}) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<Awaited<
    ReturnType<typeof fetchObservationEvidence>
  > | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null);
    setError("");
    fetchObservationEvidence(
      assetId,
      metric,
      window.from,
      window.to,
      scenarioId,
      offset,
    )
      .then((value) => {
        if (active) setData(value);
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [assetId, metric, window, scenarioId, offset, retry]);
  return (
    <section aria-labelledby="evidence-heading" className="evidence-panel">
      <h2 id="evidence-heading">Observation evidence</h2>
      <p className="evidence-hint">
        Raw {metric} records. Source attribution and quality flags come from
        stored metadata; “ok” is not independent validation. Synthetic records
        do not establish a real flood.
      </p>
      {error ? (
        <div role="alert">
          {error}{" "}
          <button onClick={() => setRetry(retry + 1)}>Retry evidence</button>
        </div>
      ) : !data ? (
        <p role="status">Loading evidence…</p>
      ) : (
        <>
          <p role="status">
            {data.rows.length} records on this page
            {data.has_more ? "; more available" : ""}.
          </p>
          {data.rows.length === 0 ? (
            <p>
              No raw measurements in this window and scenario. Missing data is
              not zero.
            </p>
          ) : (
            <div
              className="evidence-scroll"
              tabIndex={0}
              role="region"
              aria-label="Raw measurement table"
            >
              <table className="evidence-table">
                <caption>Raw measurements — {metric}, UTC</caption>
                <thead>
                  <tr>
                    <th scope="col">Timestamp / value</th>
                    <th scope="col">Quality / checks</th>
                    <th scope="col">Source / measurement meaning</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.ts}>
                      <td>
                        {utc(row.ts)}
                        <br />
                        <strong>{sample(row.value)}</strong>
                      </td>
                      <td>
                        {row.quality_flag || "unspecified"}
                        <br />
                        {row.value !== null &&
                        Number.isFinite(row.value) &&
                        Number.isFinite(Date.parse(row.ts))
                          ? "Timestamp and finite value present"
                          : "Invalid or missing value"}
                      </td>
                      <td>
                        <strong>{sourceLabel(row)}</strong>
                        <br />
                        {row.source} · {row.source_type} ·{" "}
                        {row.source_id || "No source ID"}
                        {Object.entries(row.measurement_context).map(
                          ([key, value]) => (
                            <div key={key}>
                              {key.replaceAll("_", " ")}: {value}
                            </div>
                          ),
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="detail-actions">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - 100))}
            >
              Previous records
            </button>
            <button
              disabled={!data.has_more}
              onClick={() => setOffset(data.next_offset!)}
            >
              Next records
            </button>
          </div>
        </>
      )}
    </section>
  );
}

export function EventExplanation({
  eventId,
  eventType,
}: {
  eventId: string;
  eventType: string;
}) {
  const [run, setRun] = useState<Awaited<
    ReturnType<typeof fetchEventRun>
  > | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    fetchEventRun(eventId)
      .then((value) => {
        if (active) setRun(value);
      })
      .catch((err) => {
        if (active) setError(err.message);
      });
    return () => {
      active = false;
    };
  }, [eventId]);
  const threshold =
    run?.params[
      eventType === "rain" ? "rain_threshold_mmph" : "overflow_fill_threshold"
    ];
  const duration =
    run?.params[
      eventType === "rain"
        ? "rain_min_duration_minutes"
        : "overflow_min_duration_minutes"
    ];
  const known =
    ["rain", "overflow"].includes(eventType) &&
    typeof threshold === "number" &&
    typeof duration === "number";
  return (
    <section aria-label="Why this event fired" className="evidence-panel">
      <h3>Why this event fired</h3>
      {error ? (
        <p role="alert">{error}. Rule settings cannot be verified.</p>
      ) : !run ? (
        <p role="status">Loading producing run…</p>
      ) : (
        <>
          <p>
            {known
              ? `Stored rule: ${eventType === "rain" ? "rain_mmph" : "fill_ratio"} ≥ ${threshold} for at least ${duration} minutes.`
              : "Rule settings were not recorded for this event type."}
          </p>
          <p className="evidence-hint">
            Run {run.run_id} · version {run.version}
            <br />
            {utc(run.start_ts)} → {utc(run.end_ts)}
          </p>
        </>
      )}
      <p className="evidence-hint">
        Detector output, not a confirmed flood. Confidence is a heuristic score,
        not a flood probability. The run does not record its scenario or gap
        policy; current raw records may differ from the original inputs. Inspect
        source, quality and gaps before acting.
      </p>
    </section>
  );
}
