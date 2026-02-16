# External Telemetry Adapters

This runbook defines the ingestion contracts for external telemetry and how to load them into the system.

## Supported formats

### 1) CSV
Columns (required):
- `device_id` or `asset_id`
- `metric` (alias: `type`)
- `ts` (ISO 8601)
- `value`

Optional:
- `quality_flag` (default: `ok`)

Example:
```
device_id,metric,ts,value,quality_flag
rain_gauge_0,rain_mmph,2026-02-01T00:00:00Z,3.4,ok
river_gauge_0,water_level_m,2026-02-01T00:00:00Z,1.8,ok
```
Sample file: `docs/examples/external_telemetry.csv`

### 2) JSON
Supported shapes:

List of records:
```
[
  {"device_id":"rain_gauge_0","metric":"rain_mmph","ts":"2026-02-01T00:00:00Z","value":3.4}
]
```

Object with records:
```
{"records":[{"device_id":"rain_gauge_0","metric":"rain_mmph","ts":"2026-02-01T00:00:00Z","value":3.4}]}
```

Ingest API-compatible payload:
```
{
  "device_id":"rain_gauge_0",
  "events":[
    {"type":"rain_mmph","ts":"2026-02-01T00:00:00Z","value":3.4}
  ]
}
```

### 3) NDJSON (streaming)
Each line is a JSON object with the same fields as a record:
```
{"device_id":"rain_gauge_0","metric":"rain_mmph","ts":"2026-02-01T00:00:00Z","value":3.4}
{"device_id":"river_gauge_0","metric":"water_level_m","ts":"2026-02-01T00:00:00Z","value":1.8}
```

You can pipe NDJSON via stdin.
Sample file: `docs/examples/external_telemetry.ndjson`

## Validation rules
- `device_id`/`asset_id` must resolve to a known asset
- `metric` is required
- `ts` must be ISO 8601
- `value` must be a finite number
- Optional city scoping rejects assets outside the target city

Rejected rows are reported with reasons.

## Asset mapping
If external device IDs differ from internal asset IDs, provide a mapping file:

JSON mapping (`external_id -> asset_id`):
```
{
  "rg-001": "rain_gauge_0",
  "rg-002": "rain_gauge_1"
}
```

CSV/TSV mapping with headers:
```
external_id,asset_id
rg-001,rain_gauge_0
rg-002,rain_gauge_1
```

## Run the adapter

CSV:
```
poetry run python -m floodmvp.jobs.ingest_external --format csv --path data/external.csv --city-id city_porto_mvp
```

JSON:
```
poetry run python -m floodmvp.jobs.ingest_external --format json --path data/external.json
```

NDJSON (file):
```
poetry run python -m floodmvp.jobs.ingest_external --format ndjson --path data/external.ndjson
```

NDJSON (stdin):
```
type data/external.ndjson | poetry run python -m floodmvp.jobs.ingest_external --format ndjson --path -
```

Dry run (validation only):
```
poetry run python -m floodmvp.jobs.ingest_external --format csv --path data/external.csv --dry-run
```

Report output:
```
poetry run python -m floodmvp.jobs.ingest_external --format csv --path data/external.csv --report data/ingest_report.json
```

## Rain gauge HTTP adapter (real data source)
This adapter pulls rain gauge telemetry from an HTTP endpoint that returns JSON or CSV.
You provide the field mappings for device ID, timestamp, and value.

Example (JSON list):
```
poetry run python -m floodmvp.jobs.ingest_rain_gauge_http \
  --url https://example.org/rain_gauge.json \
  --format json \
  --device-field station_id \
  --ts-field timestamp \
  --value-field rain_mm \
  --units mm \
  --interval-minutes 5 \
  --metric rain_mmph \
  --city-id city_porto_mvp
```

Example (CSV):
```
poetry run python -m floodmvp.jobs.ingest_rain_gauge_http \
  --url https://example.org/rain_gauge.csv \
  --format csv \
  --device-field station_id \
  --ts-field timestamp \
  --value-field rain_mmph \
  --units mmph
```

Notes:
- `units=mm` will be converted to `mmph` using `interval-minutes`.
- `--header "Authorization: Bearer ..."` supports auth.

## River level HTTP adapter (real data source)
This adapter pulls river level telemetry from an HTTP endpoint that returns JSON or CSV.
You provide the field mappings for device ID, timestamp, and value.

Example (JSON list):
```
poetry run python -m floodmvp.jobs.ingest_river_level_http \
  --url https://example.org/river_level.json \
  --format json \
  --device-field station_id \
  --ts-field timestamp \
  --value-field level_cm \
  --units cm \
  --metric water_level_m \
  --city-id city_porto_mvp
```

Example (CSV):
```
poetry run python -m floodmvp.jobs.ingest_river_level_http \
  --url https://example.org/river_level.csv \
  --format csv \
  --device-field station_id \
  --ts-field timestamp \
  --value-field water_level_m \
  --units m
```

Notes:
- `units` converts to meters. Supported: `m`, `cm`, `mm`, `ft`, `in`.
- `--header "Authorization: Bearer ..."` supports auth.

## Synthetic generators (JSON output)
Generate 1-minute telemetry for rain gauge (mmph) and river level (meters).

Examples:
```
poetry run python -m floodmvp.jobs.generate_external_telemetry \
  --out data/generated_steady.json \
  --start 2026-02-01T00:00:00Z \
  --end 2026-02-01T03:00:00Z \
  --pattern steady
```

```
poetry run python -m floodmvp.jobs.generate_external_telemetry \
  --out data/generated_storm.json \
  --start 2026-02-01T00:00:00Z \
  --end 2026-02-01T06:00:00Z \
  --pattern storm_bursts \
  --rain-count 3 \
  --river-count 2 \
  --outage-count 1
```

Overrides (JSON string or @file):
```
poetry run python -m floodmvp.jobs.generate_external_telemetry \
  --out data/generated_custom.json \
  --start 2026-02-01T00:00:00Z \
  --end 2026-02-01T06:00:00Z \
  --pattern seasonal \
  --rain-pattern-overrides '{"seasonal":{"base":0.2,"peak":12.0,"noise_sigma":0.4,"cycles":2}}' \
  --river-pattern-overrides '@data/river_overrides.json'
```

Per-device overrides (JSON string or @file):
```
poetry run python -m floodmvp.jobs.generate_external_telemetry \
  --out data/generated_devices.json \
  --start 2026-02-01T00:00:00Z \
  --end 2026-02-01T02:00:00Z \
  --pattern storm_bursts \
  --rain-count 2 \
  --rain-device-overrides '{"rain_gauge_1":{"base":2.0,"peak":20.0,"noise_sigma":0.8,"outage_count":2}}' \
  --river-count 1 \
  --river-device-overrides '{"river_gauge_0":{"base":0.9,"peak":2.4,"noise_sigma":0.05}}'
```

## Onboarding a new city data source
1. Create the city and assets (seed or import). Ensure `asset_id` values are stable.
2. Collect a sample of the external telemetry and identify device identifiers and metrics.
3. Create an asset map if external IDs do not match internal `asset_id`.
4. Run a dry-run ingestion and review rejection reasons.
5. Ingest a full day of data, then run analytics + QA jobs to validate coverage.
