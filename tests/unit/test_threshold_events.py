from __future__ import annotations

import datetime as dt
from collections.abc import Callable

import pandas as pd
import pytest

from floodmvp.analytics.overflow_events import detect_overflow_events
from floodmvp.analytics.rain_events import detect_rain_events

Detector = Callable[..., list[tuple[dt.datetime, dt.datetime, float]]]
BASE = dt.datetime(2026, 1, 1, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("detector", "threshold", "min_duration"),
    [
        (detect_rain_events, 5.0, 15),
        (detect_overflow_events, 1.0, 10),
    ],
)
def test_long_telemetry_gap_does_not_create_event(
    detector: Detector, threshold: float, min_duration: int
) -> None:
    """Isolated exceedances must not masquerade as continuous flooding."""
    frame = pd.DataFrame(
        {
            "ts": [BASE + dt.timedelta(minutes=m) for m in (0, 1, 60, 61)],
            "value": [threshold + 1] * 4,
        }
    )

    assert detector(frame, threshold, min_duration) == []


@pytest.mark.parametrize(
    ("detector", "threshold", "min_duration"),
    [
        (detect_rain_events, 5.0, 15),
        (detect_overflow_events, 1.0, 10),
    ],
)
def test_continuous_exceedance_preserves_event_duration(
    detector: Detector, threshold: float, min_duration: int
) -> None:
    """Regular one-minute telemetry should retain its original event duration."""
    frame = pd.DataFrame(
        {
            "ts": [BASE + dt.timedelta(minutes=m) for m in range(min_duration + 1)],
            "value": [threshold + 0.5] * (min_duration + 1),
        }
    )

    assert detector(frame, threshold, min_duration) == [
        (BASE, BASE + dt.timedelta(minutes=min_duration + 1), threshold + 0.5)
    ]


@pytest.mark.parametrize(
    ("detector", "threshold", "min_duration"),
    [
        (detect_rain_events, 5.0, 15),
        (detect_overflow_events, 1.0, 10),
    ],
)
def test_five_minute_cadence_is_supported(
    detector: Detector, threshold: float, min_duration: int
) -> None:
    """The inferred cadence also supports regular five-minute telemetry."""
    frame = pd.DataFrame(
        {
            "ts": [BASE + dt.timedelta(minutes=m) for m in (0, 5, 10, 15)],
            "value": [threshold + 1] * 4,
        }
    )

    assert detector(frame, threshold, min_duration) == [
        (BASE, BASE + dt.timedelta(minutes=20), threshold + 1)
    ]


@pytest.mark.parametrize("detector", [detect_rain_events, detect_overflow_events])
def test_invalid_gap_configuration_is_rejected(detector: Detector) -> None:
    frame = pd.DataFrame({"ts": [BASE], "value": [8.0]})

    with pytest.raises(ValueError, match="max_gap_minutes"):
        detector(frame, max_gap_minutes=0)


@pytest.mark.parametrize("detector", [detect_rain_events, detect_overflow_events])
def test_duplicate_timestamps_do_not_extend_events(detector: Detector) -> None:
    frame = pd.DataFrame(
        {
            "ts": [BASE, BASE, BASE + dt.timedelta(minutes=1)],
            "value": [12.0, 13.0, 14.0],
        }
    )

    assert detector(frame) == []
