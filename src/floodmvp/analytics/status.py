from __future__ import annotations


def risk_from_fill(
    peak_fill: float,
    watch_threshold: float,
    warning_threshold: float,
) -> tuple[str, float]:
    """Map peak fill_ratio to (status, risk_score)."""
    if peak_fill >= warning_threshold:
        return "warning", 0.95
    if peak_fill >= watch_threshold:
        return "watch", 0.7
    return "normal", 0.2
