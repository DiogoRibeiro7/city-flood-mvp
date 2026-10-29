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
Reading or writing stored overrides requires the `admin` JWT role outside
local development. If JWT is not configured, trusted server-side clients can
use the legacy `X-API-Key` header. Do not embed that key in a browser app.

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

Override values must be finite and nonnegative. Duration thresholds must be
positive whole minutes, and an explicitly supplied `risk_fill_watch` cannot
exceed an explicitly supplied `risk_fill_warning`. Risk and overflow fill
thresholds may exceed 1.0, as they do in the configured city defaults.
Unknown threshold names and malformed values return HTTP 422. An unknown
`city_id` returns HTTP 404 rather than a database error.

List overrides:
```
GET /v1/analytics/calibration/overrides?city_id=city_porto_mvp
```
Responses include operator notes and use `Cache-Control: private, no-store`.

## Notes
- Overrides are applied by month if present, otherwise fall back to `season=all`.
- Recommended thresholds are percentiles of telemetry values (rain gauge + pipe fill ratio).
