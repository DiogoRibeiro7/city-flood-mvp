"""Event-onset evaluation on explicitly reviewed, observable station periods.

This module scores a declared label set; it cannot establish that labels are
independent, complete or correct. See docs/evaluation/event-protocol.md.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from statistics import median
from typing import Any, Literal

EventType = Literal["rain", "overflow", "flood"]
LabelOrigin = Literal["controlled", "human_reviewed"]
PROTOCOL_VERSION = "1"


def _utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("evaluation timestamps must include a UTC offset")
    try:
        return value.astimezone(dt.UTC)
    except OverflowError as exc:
        raise ValueError("evaluation timestamp is outside the supported UTC range") from exc


def _text(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def _kind(value: str) -> None:
    if value not in ("rain", "overflow", "flood"):
        raise ValueError("event_type must be rain, overflow or flood")


def _origin(value: str) -> None:
    if value not in ("controlled", "human_reviewed"):
        raise ValueError("label_origin must be controlled or human_reviewed")


@dataclass(frozen=True)
class EventOnset:
    event_id: str
    station_id: str
    event_type: EventType
    onset: dt.datetime

    def __post_init__(self) -> None:
        _text(self.event_id, "event_id")
        _text(self.station_id, "station_id")
        _kind(self.event_type)
        object.__setattr__(self, "onset", _utc(self.onset))


@dataclass(frozen=True)
class Detection(EventOnset):
    # Null for retrospective detector output without a recorded issuance time.
    issued_at: dt.datetime | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.issued_at is not None:
            object.__setattr__(self, "issued_at", _utc(self.issued_at))


@dataclass(frozen=True)
class ReferenceEvent(EventOnset):
    evidence_ref: str
    reviewer: str
    label_origin: LabelOrigin

    def __post_init__(self) -> None:
        super().__post_init__()
        _text(self.evidence_ref, "evidence_ref")
        _text(self.reviewer, "reviewer")
        _origin(self.label_origin)


@dataclass(frozen=True)
class ReviewedWindow:
    """Attested complete onset labels AND available detector input/output in [start,end)."""

    station_id: str
    event_type: EventType
    start: dt.datetime
    end: dt.datetime
    review_ref: str
    reviewer: str
    label_origin: LabelOrigin

    def __post_init__(self) -> None:
        _text(self.station_id, "station_id")
        _text(self.review_ref, "review_ref")
        _text(self.reviewer, "reviewer")
        _kind(self.event_type)
        _origin(self.label_origin)
        object.__setattr__(self, "start", _utc(self.start))
        object.__setattr__(self, "end", _utc(self.end))
        if self.end <= self.start:
            raise ValueError("reviewed windows must have positive duration")


@dataclass(frozen=True)
class MatchPolicy:
    """Explicit asymmetric onset tolerance; no calibrated default is implied."""

    early_tolerance: dt.timedelta
    late_tolerance: dt.timedelta

    def __post_init__(self) -> None:
        if self.early_tolerance < dt.timedelta(0) or self.late_tolerance < dt.timedelta(0):
            raise ValueError("matching tolerances must be nonnegative")


def _merged_windows(windows: Sequence[ReviewedWindow]) -> list[tuple[dt.datetime, dt.datetime]]:
    merged: list[tuple[dt.datetime, dt.datetime]] = []
    for window in sorted(windows, key=lambda w: (w.start, w.end)):
        if merged and window.start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], window.end))
        else:
            merged.append((window.start, window.end))
    return merged


def _match(
    predictions: list[Detection], references: list[ReferenceEvent], policy: MatchPolicy
) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    """Maximum-cardinality chronological matching for a fixed onset tolerance.

    A too-early prediction cannot match any later reference; a too-late reference
    cannot match any later prediction. Otherwise the earliest feasible pair can
    be chosen without reducing cardinality. Ties use event IDs, not input order.
    """
    predictions = sorted(predictions, key=lambda p: (p.onset, p.event_id))
    references = sorted(references, key=lambda r: (r.onset, r.event_id))
    p = r = 0
    matches: list[dict[str, Any]] = []
    false_alarms: list[str] = []
    misses: list[str] = []
    while p < len(predictions) and r < len(references):
        prediction, reference = predictions[p], references[r]
        delta = prediction.onset - reference.onset
        if delta < -policy.early_tolerance:
            false_alarms.append(prediction.event_id)
            p += 1
        elif delta > policy.late_tolerance:
            misses.append(reference.event_id)
            r += 1
        else:
            matches.append(
                {
                    "station_id": prediction.station_id,
                    "prediction_id": prediction.event_id,
                    "reference_id": reference.event_id,
                    "onset_error_seconds": delta.total_seconds(),
                    "lead_time_seconds": (
                        (reference.onset - prediction.issued_at).total_seconds()
                        if prediction.issued_at is not None
                        else None
                    ),
                }
            )
            p += 1
            r += 1
    false_alarms.extend(prediction.event_id for prediction in predictions[p:])
    misses.extend(reference.event_id for reference in references[r:])
    return matches, false_alarms, misses


def _metrics(matches: list[dict[str, Any]], fp: int, fn: int, seconds: float) -> dict[str, Any]:
    tp = len(matches)
    leads = [m["lead_time_seconds"] for m in matches if m["lead_time_seconds"] is not None]
    days = seconds / 86400
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "scored_station_days": days,
        "false_alarms_per_station_day": fp / days if days else None,
        "lead_time_samples": len(leads),
        "matches_without_issue_time": tp - len(leads),
        "median_lead_time_seconds": median(leads) if leads else None,
    }


def _serialized(value: Detection | ReferenceEvent | ReviewedWindow) -> dict[str, Any]:
    return {
        key: item.isoformat() if isinstance(item, dt.datetime) else item
        for key, item in asdict(value).items()
    }


def evaluate_events(
    predictions: Sequence[Detection],
    references: Sequence[ReferenceEvent],
    reviewed_windows: Sequence[ReviewedWindow],
    *,
    event_type: EventType,
    label_origin: LabelOrigin,
    policy: MatchPolicy,
) -> dict[str, Any]:
    """Evaluate one event type; never turn unreviewed periods into negative labels.

    Prediction onset support is [review_start + late, review_end - early).
    References inside a reviewed period require their entire matching horizon
    inside that support. Insufficient reference padding fails evaluation instead
    of silently dropping a difficult positive or manufacturing boundary errors.
    """
    _kind(event_type)
    _origin(label_origin)
    for items, name in ((predictions, "prediction"), (references, "reference")):
        if len({item.event_id for item in items}) != len(items):
            raise ValueError(f"duplicate {name} event_id; deduplicate repeated runs explicitly")
    all_items: list[Detection | ReferenceEvent | ReviewedWindow] = [
        *predictions,
        *references,
        *reviewed_windows,
    ]
    for item in all_items:
        if item.event_type != event_type:
            raise ValueError(
                "evaluate one event_type at a time; rain/overflow/flood are distinct targets"
            )
    labeled_items: list[ReferenceEvent | ReviewedWindow] = [*references, *reviewed_windows]
    for labeled in labeled_items:
        if labeled.label_origin != label_origin:
            raise ValueError("cannot mix controlled and human_reviewed label evidence")

    inputs = {
        "predictions": [_serialized(p) for p in sorted(predictions, key=lambda p: p.event_id)],
        "references": [_serialized(r) for r in sorted(references, key=lambda r: r.event_id)],
        "reviewed_windows": sorted(
            (_serialized(w) for w in reviewed_windows),
            key=lambda w: (w["station_id"], w["start"], w["end"], w["review_ref"], w["reviewer"]),
        ),
    }
    config = {
        "early_tolerance_seconds": policy.early_tolerance.total_seconds(),
        "late_tolerance_seconds": policy.late_tolerance.total_seconds(),
        "matching": "one-to-one, maximum cardinality, earliest feasible onset then event_id",
        "boundary_policy": "trim prediction support; require fully padded references",
    }
    report: dict[str, Any] = {
        "protocol_version": PROTOCOL_VERSION,
        "event_type": event_type,
        "label_origin": label_origin,
        "evidence_statement": (
            "Controlled examples test software behavior only; no real-world accuracy evidence."
            if label_origin == "controlled"
            else "Human review is caller-attested; scores are conditional on the supplied label completeness, independence and timing."
        ),
        "limitations": [
            "Unreviewed periods and detector outages are unknown, never confirmed negatives; split reviewed windows around them.",
            "Onset matching does not assess event duration, severity, spatial extent or calibrated flood probability.",
            "No issue timestamp means no lead-time estimate; retrospective event onset is not alert issuance.",
            "Counts and station-time denominators accompany scores; no confidence interval or independence assumption is supplied.",
            "Choose tolerances, evidence windows and detector settings before inspecting test outcomes; report selection and timing uncertainty.",
        ],
        "policy": config,
        "inputs": inputs,
    }
    fingerprint = {
        "protocol_version": PROTOCOL_VERSION,
        "event_type": event_type,
        "label_origin": label_origin,
        "policy": config,
        "inputs": inputs,
    }
    report["evaluation_id"] = hashlib.sha256(
        json.dumps(fingerprint, sort_keys=True, allow_nan=False).encode()
    ).hexdigest()

    all_matches: list[dict[str, Any]] = []
    all_false_alarms: list[str] = []
    all_misses: list[str] = []
    ignored_predictions = []
    ignored_references = []
    stations = sorted({item.station_id for item in all_items})
    per_station = []
    total_seconds = 0.0
    for station in stations:
        windows = _merged_windows([w for w in reviewed_windows if w.station_id == station])
        cores = [
            (start + policy.late_tolerance, end - policy.early_tolerance)
            if end - start > policy.early_tolerance + policy.late_tolerance
            else None
            for start, end in windows
        ]
        pred_groups: dict[int, list[Detection]] = defaultdict(list)
        ref_groups: dict[int, list[ReferenceEvent]] = defaultdict(list)
        for reference in (r for r in references if r.station_id == station):
            index = next(
                (i for i, (start, end) in enumerate(windows) if start <= reference.onset < end),
                None,
            )
            if index is None:
                ignored_references.append({"event_id": reference.event_id, "reason": "unreviewed"})
                continue
            core = cores[index]
            if (
                core is None
                or reference.onset - core[0] < policy.early_tolerance
                or core[1] - reference.onset <= policy.late_tolerance
            ):
                raise ValueError(
                    f"reference {reference.event_id} needs additional reviewed time around its onset; extend the evidence window before scoring"
                )
            ref_groups[index].append(reference)
        for prediction in (p for p in predictions if p.station_id == station):
            index = next(
                (i for i, (start, end) in enumerate(windows) if start <= prediction.onset < end),
                None,
            )
            reason = "unreviewed" if index is None else "boundary_tolerance"
            core = cores[index] if index is not None else None
            if index is None or core is None or not core[0] <= prediction.onset < core[1]:
                ignored_predictions.append({"event_id": prediction.event_id, "reason": reason})
            else:
                pred_groups[index].append(prediction)
        matches: list[dict[str, Any]] = []
        false_alarms: list[str] = []
        misses: list[str] = []
        for index in range(len(windows)):
            paired, fp, fn = _match(pred_groups[index], ref_groups[index], policy)
            matches.extend(paired)
            false_alarms.extend(fp)
            misses.extend(fn)
        seconds = sum(
            (end - start).total_seconds()
            for core in cores
            if core is not None
            for start, end in [core]
        )
        total_seconds += seconds
        per_station.append(
            {
                "station_id": station,
                "scored_windows": [
                    {"start": core[0].isoformat(), "end": core[1].isoformat()}
                    for core in cores
                    if core is not None
                ],
                "metrics": _metrics(matches, len(false_alarms), len(misses), seconds),
            }
        )
        all_matches.extend(matches)
        all_false_alarms.extend(false_alarms)
        all_misses.extend(misses)
    report.update(
        status="evaluated" if total_seconds else "not_evaluated",
        per_station=per_station,
        matches=all_matches,
        false_alarm_ids=all_false_alarms,
        missed_reference_ids=all_misses,
        ignored_predictions=sorted(ignored_predictions, key=lambda p: p["event_id"]),
        ignored_references=sorted(ignored_references, key=lambda r: r["event_id"]),
        metrics=_metrics(all_matches, len(all_false_alarms), len(all_misses), total_seconds),
    )
    return report
