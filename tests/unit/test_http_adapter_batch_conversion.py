"""Batch-conversion contracts for the two HTTP telemetry adapters."""

from collections.abc import Callable
from typing import Any

import pytest

from floodmvp.adapters.rain_gauge_http import apply_unit_conversion as convert_rain
from floodmvp.adapters.river_level_http import apply_unit_conversion as convert_river


@pytest.mark.parametrize(
    ("converter", "units", "interval"),
    [
        (convert_rain, "in", 15),
        (convert_rain, "mmph", None),
        (convert_river, "ft", None),
        (convert_river, "m", None),
    ],
)
def test_invalid_later_row_does_not_partially_convert(
    converter: Callable[..., None], units: str, interval: int | None
) -> None:
    rows: list[dict[str, Any]] = [{"value": "2"}, {"value": "not-a-number"}]
    with pytest.raises(ValueError):
        if converter is convert_rain:
            converter(rows, units, interval)
        else:
            converter(rows, units)
    assert rows == [{"value": "2"}, {"value": "not-a-number"}]


def test_empty_batches_reject_unknown_units() -> None:
    with pytest.raises(ValueError, match="units must be"):
        convert_rain([], "unknown", None)
    with pytest.raises(ValueError, match="units must be"):
        convert_river([], "unknown")


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf")])
def test_river_levels_must_be_finite(invalid: float) -> None:
    with pytest.raises(ValueError, match="river level must be finite"):
        convert_river([{"value": invalid}], "m")


def test_negative_river_datum_and_missing_readings_are_preserved() -> None:
    rows: list[dict[str, Any]] = [{"value": "-100"}, {"value": None}]
    convert_river(rows, "cm")
    assert rows == [{"value": -1.0}, {"value": None}]


def test_rainfall_native_units_are_validated() -> None:
    with pytest.raises(ValueError, match="finite and nonnegative"):
        convert_rain([{"value": "-0.1"}], "mmph", None)
