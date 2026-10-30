"""Regression tests for rain-gauge accumulation-to-rate conversion."""

import pytest

from floodmvp.adapters.rain_gauge_http import apply_unit_conversion, convert_units


@pytest.mark.parametrize(
    ("value", "units", "interval", "expected"),
    [
        (2.0, "mm", 15, 8.0),
        (0.1, "in", 15, 10.16),
        (0.1, "inph", None, 2.54),
        (3.0, "mmph", None, 3.0),
    ],
)
def test_convert_units(value: float, units: str, interval: int | None, expected: float) -> None:
    assert convert_units(value, units, interval) == pytest.approx(expected)


@pytest.mark.parametrize("interval", [None, 0, -5, 1.5, True])
@pytest.mark.parametrize("units", ["mm", "in"])
def test_accumulations_require_positive_integer_interval(units: str, interval: object) -> None:
    with pytest.raises(ValueError, match="positive interval_minutes"):
        convert_units(1.0, units, interval)  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [-1.0, float("nan"), float("inf"), -float("inf")])
def test_invalid_rainfall_rejected(value: float) -> None:
    with pytest.raises(ValueError, match="finite and nonnegative"):
        convert_units(value, "inph")


def test_row_conversion_for_inches_accumulated() -> None:
    rows: list[dict[str, object]] = [{"value": "0.1"}]
    apply_unit_conversion(rows, "in", 15)
    assert rows[0]["value"] == pytest.approx(10.16)
