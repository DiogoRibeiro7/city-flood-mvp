# Analytics Calibration

This runbook provides tooling for calibrating analytics thresholds per city and season.

## Recommendations
Generate recommended thresholds from recent telemetry:

```
GET /v1/analytics/calibration/recommendations?city_id=city_porto_mvp&seasonality=all
```

Monthly seasonality:
```
GET /v1/analytics/calibration/recommendations?city_id=city_porto_mvp&seasonality=monthly
```

Custom window:
```
GET /v1/analytics/calibration/recommendations?city_id=city_porto_mvp&from=2026-01-01T00:00:00Z&to=2026-02-01T00:00:00Z
```

## Overrides
Store a threshold override for a city (applied at analytics runtime):

```
POST /v1/analytics/calibration/overrides
{
  "city_id": "city_porto_mvp",
  "season": "all",
  "thresholds": {
    "rain_event_threshold_mmph": 6.5,
    "overflow_fill_threshold": 1.02,
    "risk_fill_watch": 1.1,
    "risk_fill_warning": 1.35
  },
  "notes": "Updated after January storm review"
}
```

Seasonal overrides use:
- `season = "all"` for global
- `season = "month-01"` ... `season = "month-12"` for monthly overrides

List overrides:
```
GET /v1/analytics/calibration/overrides?city_id=city_porto_mvp
```

## Notes
- Overrides are applied by month if present, otherwise fall back to `season=all`.
- Recommended thresholds are percentiles of telemetry values (rain gauge + pipe fill ratio).
