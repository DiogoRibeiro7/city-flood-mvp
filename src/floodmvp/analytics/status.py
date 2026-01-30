from __future__ import annotations

def risk_from_fill(peak_fill: float) -> tuple[str, float]:
    """Map peak fill_ratio to (status, risk_score)."""
    if peak_fill >= 1.4:
        return "warning", 0.95
    if peak_fill >= 1.15:
        return "watch", 0.7
    return "normal", 0.2
