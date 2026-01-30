from __future__ import annotations

SCENARIOS: dict[str, dict[str, object]] = {
    "normal": {"label": "Normal day", "heavy_rain": False, "high_river": False},
    "heavy_rain_low_river": {"label": "Heavy rain, low river", "heavy_rain": True, "high_river": False},
    "heavy_rain_high_river": {"label": "Heavy rain + high river", "heavy_rain": True, "high_river": True},
}
