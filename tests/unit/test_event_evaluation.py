"""Controlled labels verify evaluation mechanics, never real-world accuracy."""

from __future__ import annotations

import datetime as dt
import json
import random
from dataclasses import replace

import pandas as pd
import pytest

from floodmvp.analytics.evaluation import (
    Detection,
    MatchPolicy,
    ReferenceEvent,
    ReviewedWindow,
    evaluate_events,
)
from floodmvp.analytics.overflow_events import detect_overflow_events
from floodmvp.analytics.rain_events import detect_rain_events

BASE = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)
ZERO = MatchPolicy(dt.timedelta(0), dt.timedelta(0))


def time(minutes):
    return BASE + dt.timedelta(minutes=minutes)


def detection(identifier, minute, station="test_A", issued=None):
    return Detection(
        identifier, station, "rain", time(minute), time(issued) if issued is not None else None
    )


def reference(identifier, minute, station="test_A"):
    return ReferenceEvent(
        identifier,
        station,
        "rain",
        time(minute),
        "controlled:labels-v1",
        "test-author",
        "controlled",
    )


def window(start=0, end=1440, station="test_A"):
    return ReviewedWindow(
        station, "rain", time(start), time(end), "controlled:review-v1", "test-author", "controlled"
    )


def evaluate(predictions=(), references=(), windows=(), policy=ZERO):
    return evaluate_events(
        predictions,
        references,
        windows,
        event_type="rain",
        label_origin="controlled",
        policy=policy,
    )


def test_counts_denominators_signed_lead_time_and_unknown_periods():
    result = evaluate(
        [
            detection("p1", 95, issued=90),
            detection("p2", 205, issued=210),
            detection("fp", 400),
            detection("unknown", 2000),
        ],
        [
            reference("r1", 100),
            reference("r2", 200),
            reference("fn", 300),
            reference("unreviewed", 2000),
        ],
        [window(-5, 1445)],
        MatchPolicy(dt.timedelta(minutes=5), dt.timedelta(minutes=5)),
    )
    metrics = result["metrics"]
    assert metrics == {
        "true_positives": 2,
        "false_positives": 1,
        "false_negatives": 1,
        "precision": 2 / 3,
        "recall": 2 / 3,
        "scored_station_days": 1,
        "false_alarms_per_station_day": 1,
        "lead_time_samples": 2,
        "matches_without_issue_time": 0,
        "median_lead_time_seconds": 0,
    }
    assert [pair["lead_time_seconds"] for pair in result["matches"]] == [600, -600]
    assert [pair["onset_error_seconds"] for pair in result["matches"]] == [-300, 300]
    assert result["false_alarm_ids"] == ["fp"] and result["missed_reference_ids"] == ["fn"]
    assert result["ignored_predictions"] == [{"event_id": "unknown", "reason": "unreviewed"}]
    assert result["ignored_references"] == [{"event_id": "unreviewed", "reason": "unreviewed"}]
    assert "no real-world accuracy evidence" in result["evidence_statement"]
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_unreviewed_data_cannot_produce_accuracy_or_false_alarm_rate():
    result = evaluate([detection("p", 20)], [reference("r", 20)])
    assert result["status"] == "not_evaluated"
    for key in ("precision", "recall", "false_alarms_per_station_day", "median_lead_time_seconds"):
        assert result["metrics"][key] is None
    assert result["metrics"]["true_positives"] == 0
    assert result["matches"] == []


def test_reviewed_negative_time_and_zero_prediction_denominators():
    no_events = evaluate(windows=[window()])
    assert no_events["status"] == "evaluated"
    assert no_events["metrics"]["precision"] is None
    assert no_events["metrics"]["recall"] is None
    assert no_events["metrics"]["false_alarms_per_station_day"] == 0
    false_alarm = evaluate([detection("p", 20)], windows=[window()])
    assert false_alarm["metrics"]["precision"] == 0
    assert false_alarm["metrics"]["recall"] is None
    miss = evaluate(references=[reference("r", 20)], windows=[window()])
    assert miss["metrics"]["precision"] is None and miss["metrics"]["recall"] == 0


def test_missing_issue_time_is_not_replaced_by_event_onset():
    result = evaluate(
        [detection("p", 90)],
        [reference("r", 100)],
        [window()],
        MatchPolicy(dt.timedelta(minutes=10), dt.timedelta(0)),
    )
    assert result["matches"][0]["onset_error_seconds"] == -600
    assert result["matches"][0]["lead_time_seconds"] is None
    assert result["metrics"]["median_lead_time_seconds"] is None
    assert result["metrics"]["matches_without_issue_time"] == 1


def test_one_to_one_ties_and_duplicate_alarm_penalty_are_order_independent():
    predictions = [detection("b", 20), detection("a", 20)]
    references = [reference("r", 20)]
    result = evaluate(predictions, references, [window()])
    assert result == evaluate(list(reversed(predictions)), references, [window()])
    assert result["matches"][0]["prediction_id"] == "a"
    assert result["false_alarm_ids"] == ["b"]
    assert result["metrics"]["precision"] == 0.5


def test_earliest_feasible_pair_avoids_nearest_greedy_losing_a_match():
    result = evaluate(
        [detection("p1", 1), detection("p2", 11)],
        [reference("r1", 10), reference("r2", 20)],
        [window(-30, 60)],
        MatchPolicy(dt.timedelta(minutes=9), dt.timedelta(minutes=1)),
    )
    assert [(p["prediction_id"], p["reference_id"]) for p in result["matches"]] == [
        ("p1", "r1"),
        ("p2", "r2"),
    ]


def test_matching_cardinality_against_small_exhaustive_oracle():
    def maximum_matches(predictions, references, early, late):
        def optimum(index, available):
            if index == len(predictions):
                return 0
            return max(
                [
                    optimum(index + 1, available),
                    *(
                        1 + optimum(index + 1, available - {r})
                        for r in available
                        if -early <= predictions[index] - references[r] <= late
                    ),
                ]
            )

        return optimum(0, set(range(len(references))))

    rng = random.Random(9)
    for _ in range(120):
        predictions = [rng.randrange(10, 30) for _ in range(rng.randrange(5))]
        references = [rng.randrange(10, 30) for _ in range(rng.randrange(5))]
        early, late = rng.randrange(5), rng.randrange(5)

        expected = maximum_matches(predictions, references, early, late)
        result = evaluate(
            [detection(f"p{i}", t) for i, t in enumerate(predictions)],
            [reference(f"r{i}", t) for i, t in enumerate(references)],
            [window()],
            MatchPolicy(dt.timedelta(minutes=early), dt.timedelta(minutes=late)),
        )
        assert result["metrics"]["true_positives"] == expected


@pytest.mark.parametrize(
    ("offset", "matched"), [(-5, True), (3, True), (-5.0001, False), (3.0001, False)]
)
def test_asymmetric_tolerance_is_inclusive(offset, matched):
    result = evaluate(
        [detection("p", 100 + offset)],
        [reference("r", 100)],
        [window()],
        MatchPolicy(dt.timedelta(minutes=5), dt.timedelta(minutes=3)),
    )
    assert result["metrics"]["true_positives"] == int(matched)
    assert result["metrics"]["false_positives"] == int(not matched)
    assert result["metrics"]["false_negatives"] == int(not matched)


def test_overlapping_and_adjacent_windows_union_without_double_counting_station_days():
    windows = [window(0, 720), window(360, 1440), window(1440, 2880), window(station="test_B")]
    result = evaluate([detection("a", 60), detection("b", 60, station="test_B")], windows=windows)
    assert result["metrics"]["scored_station_days"] == 3
    assert result["metrics"]["false_alarms_per_station_day"] == 2 / 3
    assert [s["metrics"]["scored_station_days"] for s in result["per_station"]] == [2, 1]
    assert result == evaluate(
        [detection("b", 60, station="test_B"), detection("a", 60)], windows=list(reversed(windows))
    )


def test_station_identity_prevents_cross_station_matches():
    result = evaluate(
        [detection("p", 60)],
        [reference("r", 60, station="test_B")],
        [window(), window(station="test_B")],
    )
    assert result["matches"] == []
    assert result["metrics"]["false_positives"] == result["metrics"]["false_negatives"] == 1


def test_gaps_and_boundary_context_are_excluded_from_false_alarm_exposure():
    result = evaluate(
        [
            detection("before_core", 4),
            detection("at_core", 5),
            detection("core_end", 25),
            detection("gap", 40),
            detection("end", 90),
        ],
        windows=[window(0, 30), window(60, 90)],
        policy=MatchPolicy(dt.timedelta(minutes=5), dt.timedelta(minutes=5)),
    )
    assert result["false_alarm_ids"] == ["at_core"]
    assert result["metrics"]["scored_station_days"] == 40 / 1440
    assert {p["event_id"]: p["reason"] for p in result["ignored_predictions"]} == {
        "before_core": "boundary_tolerance",
        "core_end": "boundary_tolerance",
        "gap": "unreviewed",
        "end": "unreviewed",
    }


@pytest.mark.parametrize("minute", [0, 9, 20, 29])
def test_positive_without_complete_matching_context_fails_instead_of_being_dropped(minute):
    with pytest.raises(ValueError, match="additional reviewed time"):
        evaluate(
            references=[reference("r", minute)],
            windows=[window(0, 30)],
            policy=MatchPolicy(dt.timedelta(minutes=5), dt.timedelta(minutes=5)),
        )


def test_short_window_has_no_scorable_time():
    result = evaluate(
        [detection("p", 5)],
        windows=[window(0, 10)],
        policy=MatchPolicy(dt.timedelta(minutes=5), dt.timedelta(minutes=5)),
    )
    assert result["status"] == "not_evaluated"
    assert result["metrics"]["false_alarms_per_station_day"] is None


def test_equivalent_offsets_normalize_to_identical_results():
    result = evaluate([detection("p", 30, issued=31)], [reference("r", 30)], [window()])
    offset = dt.timezone(dt.timedelta(hours=2))
    prediction = replace(
        detection("p", 30, issued=31),
        onset=time(30).astimezone(offset),
        issued_at=time(31).astimezone(offset),
    )
    assert result == evaluate([prediction], [reference("r", 30)], [window()])


@pytest.mark.parametrize(
    "factory",
    [
        lambda: replace(detection("p", 10), onset=dt.datetime(2026, 1, 1)),
        lambda: replace(detection("p", 10), issued_at=dt.datetime(2026, 1, 1)),
        lambda: replace(reference("r", 10), reviewer=" "),
        lambda: replace(reference("r", 10), evidence_ref=""),
        lambda: replace(window(), review_ref=""),
        lambda: window(10, 10),
        lambda: replace(detection("p", 10), event_id=""),
        lambda: replace(window(), station_id=""),
        lambda: MatchPolicy(dt.timedelta(minutes=-1), dt.timedelta(0)),
    ],
)
def test_invalid_evidence_and_timestamps_fail(factory):
    with pytest.raises(ValueError):
        factory()


def test_repeated_ids_mixed_targets_and_mixed_evidence_are_rejected():
    with pytest.raises(ValueError, match="duplicate prediction"):
        evaluate([detection("p", 10), detection("p", 20)])
    with pytest.raises(ValueError, match="duplicate reference"):
        evaluate(references=[reference("r", 10), reference("r", 20)])
    with pytest.raises(ValueError, match="one event_type"):
        evaluate([replace(detection("p", 10), event_type="overflow")])
    with pytest.raises(ValueError, match="cannot mix"):
        evaluate(references=[replace(reference("r", 10), label_origin="human_reviewed")])
    with pytest.raises(ValueError, match="cannot mix"):
        evaluate(windows=[replace(window(), label_origin="human_reviewed")])


def test_human_review_attestation_stays_explicit_without_claiming_independent_verification():
    # Controlled stand-ins exercise metadata validation; these are not real human-reviewed events.
    result = evaluate_events(
        [], [], [], event_type="flood", label_origin="human_reviewed", policy=ZERO
    )
    assert result["status"] == "not_evaluated"
    assert "caller-attested" in result["evidence_statement"]
    assert result["metrics"]["precision"] is result["metrics"]["recall"] is None


@pytest.mark.parametrize(
    ("detector", "kind", "value"),
    [(detect_rain_events, "rain", 8.0), (detect_overflow_events, "overflow", 1.2)],
)
def test_existing_detector_output_can_be_scored_without_inventing_issue_times(
    detector, kind, value
):
    frame = pd.DataFrame({"ts": [time(m) for m in range(60, 81)], "value": [value] * 21})
    events = detector(frame)
    predictions = [
        Detection(f"controlled-{i}", "test_A", kind, start)
        for i, (start, _, _) in enumerate(events)
    ]
    result = evaluate_events(
        predictions,
        [replace(reference("r", 60), event_type=kind)],
        [replace(window(), event_type=kind)],
        event_type=kind,
        label_origin="controlled",
        policy=ZERO,
    )
    assert result["metrics"]["true_positives"] == 1
    assert result["metrics"]["matches_without_issue_time"] == 1
    assert result["metrics"]["median_lead_time_seconds"] is None
