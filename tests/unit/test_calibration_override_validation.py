"""Ensure operator-defined calibration thresholds are physically meaningful."""

from __future__ import annotations

import math
from typing import Any

import pytest
from pydantic import ValidationError

from floodmvp.models.domain import CalibrationOverrideIn


@pytest.mark.parametrize(
    "thresholds",
    [
        {"rain_event_threshold_mmph": -0.1},
        {"rain_event_threshold_mmph": math.nan},
        {"rain_event_min_duration_minutes": 0},
        {"overflow_fill_threshold": -1.0},
        {"overflow_min_duration_minutes": -4},
        {"risk_fill_watch": math.inf},
        {"risk_fill_warning": -0.2},
        {"risk_fill_watch": 1.4, "risk_fill_warning": 1.1},
        {"risk_fill_wathc": 1.2},
    ],
)
def test_invalid_thresholds_fail_request_validation(thresholds: dict[str, Any]) -> None:
    """Invalid overrides must fail before any database writes are attempted."""
    with pytest.raises(ValidationError):
        CalibrationOverrideIn.model_validate({"city_id": "city_a", "thresholds": thresholds})


@pytest.mark.parametrize(
    "thresholds",
    [
        {},
        {"rain_event_threshold_mmph": 0.0},
        {"overflow_fill_threshold": 1.05},
        {"risk_fill_watch": 1.2},
        {"risk_fill_watch": 1.1, "risk_fill_warning": 1.4},
        {"rain_event_min_duration_minutes": 1, "overflow_min_duration_minutes": 30},
    ],
)
def test_valid_partial_thresholds_remain_supported(thresholds: dict[str, Any]) -> None:
    """Preserve partial overrides and supported fill ratios above 100 percent."""
    payload = CalibrationOverrideIn.model_validate({"city_id": "city_a", "thresholds": thresholds})
    for name, value in thresholds.items():
        assert getattr(payload.thresholds, name) == value
