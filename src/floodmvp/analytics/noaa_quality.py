"""Descriptive quality evidence for bounded GHCNh station/report-time windows."""

from __future__ import annotations

import datetime as dt
import math
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from floodmvp.adapters.noaa_ghcnh import (
    ADAPTER_VERSION,
    DATASET_DOI,
    FIELD,
    FORMAT_VERSION,
    INTERVAL_MINUTES,
    REQUIRED_COLUMNS,
    DownloadLimits,
    GHCNhBatch,
    GHCNhError,
    GHCNhRequest,
    SourceChunk,
    fingerprint,
    iter_source_rows,
    normalize_row,
)

REPORT_VERSION = "1"
DOCUMENTATION = "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/doc/ghcnh_DOCUMENTATION.pdf"


@dataclass(frozen=True)
class QualityPolicy:
    """Analysis assumptions, not a provider promise or a calibrated operational SLO."""

    expected_cadence_minutes: int = 360
    stale_after_minutes: int = 1440

    def __post_init__(self) -> None:
        if not 1 <= self.expected_cadence_minutes <= 44640:
            raise GHCNhError("expected cadence must be between 1 and 44640 minutes")
        if not 1 <= self.stale_after_minutes <= 44640:
            raise GHCNhError("stale threshold must be between 1 and 44640 minutes")


def _intervals(
    timestamps: list[dt.datetime], start: dt.datetime, end: dt.datetime
) -> dict[str, Any]:
    """Union observed accumulation intervals, clipped to a half-open analysis window."""
    merged: list[tuple[dt.datetime, dt.datetime]] = []
    for timestamp in sorted(timestamps):
        left = max(start, timestamp - dt.timedelta(minutes=INTERVAL_MINUTES))
        right = min(end, timestamp)
        if left >= right:
            continue
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
        else:
            merged.append((left, right))
    gaps = []
    cursor = start
    for left, right in [*merged, (end, end)]:
        if cursor < left:
            gaps.append(
                {
                    "start": cursor.isoformat(),
                    "end": left.isoformat(),
                    "minutes": (left - cursor).total_seconds() / 60,
                }
            )
        cursor = right
    minutes = sum((right - left).total_seconds() / 60 for left, right in merged)
    total = (end - start).total_seconds() / 60
    return {
        "window_minutes": total,
        "supported_minutes": minutes,
        "unsupported_minutes": total - minutes,
        "supported_fraction": minutes / total,
        "unsupported_intervals": gaps,
    }


def _sampling(timestamps: list[dt.datetime], cadence: int | None = None) -> dict[str, Any]:
    differences = [
        (b - a).total_seconds() / 60 for a, b in zip(timestamps, timestamps[1:], strict=False)
    ]
    histogram = Counter(differences)
    result: dict[str, Any] = {
        "timestamps": len(timestamps),
        "delta_minutes_histogram": [
            {"minutes": value, "count": count} for value, count in sorted(histogram.items())
        ],
        "multiple_observed_spacings": len(histogram) > 1,
    }
    if cadence is not None:
        result["deltas_different_from_assumed_cadence"] = sum(n != cadence for n in differences)
        result["off_grid_timestamps"] = sum(t.timestamp() % (cadence * 60) != 0 for t in timestamps)
    return result


def _freshness(timestamps: list[dt.datetime], end: dt.datetime, threshold: int) -> dict[str, Any]:
    if not timestamps:
        return {"status": "no_observation_in_window", "latest": None, "age_minutes": None}
    age = (end - timestamps[-1]).total_seconds() / 60
    return {
        "status": "stale_at_window_end" if age > threshold else "within_threshold_at_window_end",
        "latest": timestamps[-1].isoformat(),
        "age_minutes": age,
    }


def _row_issues(row: dict[str, str]) -> list[str]:
    """Inspect independent problems even when ingestion would stop at the first rejection."""
    issues = []
    raw = row[FIELD].strip()
    if raw:
        try:
            depth = float(raw)
            if not math.isfinite(depth) or depth < 0:
                issues.append("impossible_rainfall")
        except ValueError:
            issues.append("invalid_rainfall_number")
            # The PSV contract is a bare number in mm, never a per-row unit string.
            if re.fullmatch(
                r"[+-]?[\d.]+\s*(?:mm|cm|in(?:ch(?:es)?)?|kg|m)(?:/h(?:r)?)?", raw, re.I
            ):
                issues.append("embedded_unit_token")
    try:
        lat, lon, elevation = (float(row[k]) for k in ("LATITUDE", "LONGITUDE", "ELEVATION"))
        if not all(math.isfinite(n) for n in (lat, lon, elevation)) or not (
            -90 <= lat <= 90 and -180 <= lon <= 180
        ):
            issues.append("impossible_coordinates")
    except ValueError:
        issues.append("invalid_coordinate_number")
    if row[f"{FIELD}_Quality_Code"]:
        issues.append("source_quality_flag")
    if row[f"{FIELD}_Measurement_Code"] not in ("", "T"):
        issues.append("unsupported_measurement_code")
    return issues


def characterize(
    request: GHCNhRequest,
    chunks: Iterable[SourceChunk],
    *,
    policy: QualityPolicy = QualityPolicy(),
    limits: DownloadLimits = DownloadLimits(),
) -> dict[str, Any]:
    """Report one station/window only after all requested annual chunks validate.

    Exact duplicates collapse; conflicting timestamp groups are entirely excluded.
    Fixture selections describe rows only, never station completeness or freshness.
    """
    groups: dict[dt.datetime, list[tuple[int, dict[str, str], SourceChunk]]] = defaultdict(list)
    sources: list[dict[str, Any]] = []
    years: set[int] = set()
    source_rows = outside_window = 0
    issues: Counter[str] = Counter()
    examples: list[dict[str, Any]] = []
    try:
        for chunk in chunks:
            if chunk.year not in request.years or chunk.year in years:
                raise GHCNhError("quality report requires each requested year exactly once")
            years.add(chunk.year)
            for number, timestamp, row in iter_source_rows(chunk, request, limits):
                source_rows += 1
                if not request.start <= timestamp < request.end:
                    outside_window += 1
                    continue
                groups[timestamp].append((number, row, chunk))
                found = _row_issues(row)
                issues.update(found)
                if found and len(examples) < 20:
                    examples.append(
                        {
                            "year": chunk.year,
                            "source_line": number,
                            "timestamp": timestamp.isoformat(),
                            "issues": found,
                        }
                    )
            sources.append(chunk.provenance)
        if years != set(request.years):
            raise GHCNhError("quality report is missing a requested annual chunk")
    except GHCNhError as exc:
        exc.completed_sources = sources
        raise

    states: Counter[str] = Counter(
        {"missing_rainfall": 0, "observed_zero": 0, "observed_positive": 0, "trace_rainfall": 0}
    )
    state_at: dict[dt.datetime, str] = {}
    exact_duplicates = conflicting = 0
    for timestamp, rows in sorted(groups.items()):
        signatures = {tuple(row[k] for k in REQUIRED_COLUMNS if k != "DATE") for _, row, _ in rows}
        exact_duplicates += len(rows) - len(signatures)
        if len(signatures) > 1:
            conflicting += 1
            state = "conflicting_duplicate"
        else:
            number, row, chunk = rows[0]
            batch = GHCNhBatch(request)
            normalize_row(row, timestamp, number, chunk, batch)
            if batch.records:
                state = "observed_zero" if float(row[FIELD]) == 0 else "observed_positive"
            else:
                state = next(iter(batch.stats.reasons))
        states[state] += 1
        state_at[timestamp] = state

    weather = sorted(groups)
    quantitative = [t for t, s in state_at.items() if s in ("observed_zero", "observed_positive")]
    trace = [t for t, s in state_at.items() if s == "trace_rainfall"]
    selected_rows = sum(len(rows) for rows in groups.values())
    scope = (
        "annual_source_window"
        if all(s.get("mode") == "http" for s in sources)
        else "selected_rows_only"
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "report_version": REPORT_VERSION,
        "adapter_version": ADAPTER_VERSION,
        "status": "characterized",
        "scope": scope,
        "station_id": request.station_id,
        "start": request.start.isoformat(),
        "end": request.end.isoformat(),
        "field": FIELD,
        "format_version": FORMAT_VERSION,
        "license": "CC0-1.0",
        "dataset_doi": DATASET_DOI,
        "policy": asdict(policy),
        "sources": sources,
        "counts": {
            "source_rows": source_rows,
            "outside_window": outside_window,
            "selected_rows": selected_rows,
            "unique_timestamps": len(groups),
            "duplicate_extra_rows": selected_rows - len(groups),
            "exact_duplicate_extra_rows": exact_duplicates,
            "conflicting_timestamps": conflicting,
            "quantitative_observations": len(quantitative),
            "states_by_unique_timestamp": dict(sorted(states.items())),
            "issues_by_raw_row": dict(sorted(issues.items())),
        },
        "issue_examples": examples,
        "unit_check": {
            "status": "contract_only",
            "expected_unit": "mm",
            "interval_minutes": INTERVAL_MINUTES,
            "embedded_unit_rows": issues["embedded_unit_token"],
            "documentation": DOCUMENTATION,
            "limitation": "The fixed field defines mm over six hours. PSV has no per-row unit metadata; silent unit/scale changes cannot be inferred from numbers. Other duration fields are not combined.",
        },
        "limitations": [
            "Blank source QC is unverified, not passed QC; quantitative means eligible under the ingestion policy.",
            "Missing, rejected and trace rainfall are not observed zero; trace amounts are not quantitatively supported.",
            "Cadence and stale thresholds are declared analysis assumptions, not verified station schedules or service objectives.",
            "Coverage unions six-hour intervals from eligible report timestamps in [start,end). It clips the left edge and excludes reports at/after end, so the right edge is censored.",
            "Interval support does not resolve sub-hourly timing, establish flood events or validate detector accuracy.",
        ],
    }
    report["analysis_version"] = fingerprint(
        {
            "report_version": REPORT_VERSION,
            "adapter_version": ADAPTER_VERSION,
            "station": request.station_id,
            "start": report["start"],
            "end": report["end"],
            "policy": asdict(policy),
            "scope": scope,
            "sources": [(s["year"], s["sha256"]) for s in sources],
        }
    )
    if scope == "selected_rows_only":
        report.update(coverage=None, sampling=None, freshness=None, daily=[])
        report["limitations"].append(
            "Selected fixture rows are noncontiguous; station coverage, missing intervals, sampling and freshness are not assessed."
        )
        return report

    step = policy.expected_cadence_minutes * 60
    first = dt.datetime.fromtimestamp(math.ceil(request.start.timestamp() / step) * step, dt.UTC)
    grid: list[dt.datetime] = []
    cursor = first
    while cursor < request.end:
        grid.append(cursor)
        cursor += dt.timedelta(seconds=step)
    grid_states = Counter(state_at.get(t, "no_weather_report") for t in grid)
    quantitative_set = set(quantitative)
    quantitative_on_grid = sum(t in quantitative_set for t in grid)
    report["coverage"] = {
        "interval_support": _intervals(quantitative, request.start, request.end),
        "assumed_grid": {
            "anchor": "1970-01-01T00:00:00+00:00",
            "expected_slots": len(grid),
            "quantitative_slots": quantitative_on_grid,
            "slots_without_quantitative_rainfall": len(grid) - quantitative_on_grid,
            "quantitative_fraction": quantitative_on_grid / len(grid) if grid else None,
            "states": dict(sorted(grid_states.items())),
        },
    }
    report["sampling"] = {
        "weather_reports": _sampling(weather),
        "quantitative_rainfall": _sampling(quantitative, policy.expected_cadence_minutes),
        "trace_timestamps": [t.isoformat() for t in trace],
    }
    report["freshness"] = {
        "reference": request.end.isoformat(),
        "weather_reports": _freshness(weather, request.end, policy.stale_after_minutes),
        "quantitative_rainfall": _freshness(quantitative, request.end, policy.stale_after_minutes),
    }
    daily = []
    cursor = request.start
    while cursor < request.end:
        end = min(
            request.end,
            cursor.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1),
        )
        support = _intervals(quantitative, cursor, end)
        daily.append(
            {
                "start": cursor.isoformat(),
                "end": end.isoformat(),
                "states": dict(
                    sorted(Counter(s for t, s in state_at.items() if cursor <= t < end).items())
                ),
                "supported_minutes": support["supported_minutes"],
                "window_minutes": support["window_minutes"],
            }
        )
        cursor = end
    report["daily"] = daily
    return report


def render_markdown(report: dict[str, Any]) -> str:
    """Render the same evidence as JSON, including failed/unavailable acquisitions."""
    if report["status"] == "failed":
        return f"# NOAA GHCNh quality report\n\nStatus: failed. {report['error']}\n\nNo coverage metrics were produced. See JSON for completed source evidence.\n"
    counts = report["counts"]
    lines = [
        "# NOAA GHCNh quality report",
        "",
        f"Station: `{report['station_id']}`. Report timestamps: `[{report['start']}, {report['end']})`.",
        "",
        f"Scope: **{report['scope']}**. Analysis version: `{report['analysis_version']}`.",
        "",
        "This is a descriptive characterization, not a quality pass or flood validation.",
        "",
        "| Count | Value |",
        "| --- | ---: |",
        *[f"| {key} | {value} |" for key, value in counts.items() if isinstance(value, int)],
        "",
        "| State per unique timestamp | Count |",
        "| --- | ---: |",
        *[f"| {key} | {value} |" for key, value in counts["states_by_unique_timestamp"].items()],
        "",
        f"Raw-row issues: `{counts['issues_by_raw_row']}`. Examples and complete sampling histograms are in JSON.",
        "",
        f"Unit check: **{report['unit_check']['status']}**. {report['unit_check']['limitation']}",
        "",
    ]
    if report["coverage"] is None:
        lines += [
            "Coverage, missing intervals, sampling and freshness: **not assessed for selected rows**.",
            "",
        ]
    else:
        support = report["coverage"]["interval_support"]
        grid = report["coverage"]["assumed_grid"]
        lines += [
            f"Quantitative interval support: **{support['supported_minutes']:g} / {support['window_minutes']:g} minutes ({support['supported_fraction']:.2%})**. Unsupported time is unknown, not dry.",
            "",
            f"Assumed {report['policy']['expected_cadence_minutes']}-minute UTC grid: {grid['quantitative_slots']} / {grid['expected_slots']} quantitative slots; {grid['slots_without_quantitative_rainfall']} without quantitative rainfall. This is an assumed schedule.",
            "",
            f"Assumed grid states: `{grid['states']}`.",
            "",
            f"Freshness at window end (threshold {report['policy']['stale_after_minutes']} minutes):",
            "",
            "| Series | Latest UTC | Age (minutes) | Status |",
            "| --- | --- | ---: | --- |",
            *[
                f"| {key} | {report['freshness'][key]['latest']} | {report['freshness'][key]['age_minutes']} | {report['freshness'][key]['status']} |"
                for key in ("weather_reports", "quantitative_rainfall")
            ],
            "",
            f"Quantitative sampling: `{report['sampling']['quantitative_rainfall']}`.",
            "",
            "| Unsupported interval start | End | Minutes |",
            "| --- | --- | ---: |",
            *[
                f"| {gap['start']} | {gap['end']} | {gap['minutes']:g} |"
                for gap in support["unsupported_intervals"]
            ],
            "",
            "| UTC day/window start | Quantitative reports | Zero | Trace | Missing rainfall | Supported / window minutes |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for day in report["daily"]:
            states = day["states"]
            zero = states.get("observed_zero", 0)
            lines.append(
                f"| {day['start']} | {zero + states.get('observed_positive', 0)} | {zero} | {states.get('trace_rainfall', 0)} | {states.get('missing_rainfall', 0)} | {day['supported_minutes']:g} / {day['window_minutes']:g} |"
            )
        lines.append("")
    lines += [
        "Limitations:",
        "",
        *[f"- {item}" for item in report["limitations"]],
        "",
        "Sources (CC0-1.0; Menne et al., NOAA NCEI):",
        "",
    ]
    for source in report["sources"]:
        lines.append(
            f"- [Station-year {source['year']}]({source['url']}), retrieved {source['retrieved_at']}; mode `{source['mode']}`; SHA-256 `{source['sha256']}`."
        )
    lines += [
        "",
        f"[Dataset DOI]({DATASET_DOI}); [provider format documentation]({DOCUMENTATION}).",
        "",
    ]
    return "\n".join(lines)
