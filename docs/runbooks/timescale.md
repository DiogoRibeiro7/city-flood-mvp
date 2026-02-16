# Timescale Policies (MVP)

## Retention
Raw telemetry is retained for 30 days:

```
SELECT add_retention_policy('telemetry_observation', INTERVAL '30 days');
```

## Continuous aggregate
5‑minute buckets per asset/metric:

```
CREATE MATERIALIZED VIEW telemetry_observation_5m
WITH (timescaledb.continuous) AS
SELECT
  asset_id,
  metric,
  time_bucket('5 minutes', ts) AS bucket,
  avg(value) AS avg_value,
  min(value) AS min_value,
  max(value) AS max_value,
  count(*) AS samples
FROM telemetry_observation
GROUP BY asset_id, metric, bucket;
```

Policy refreshes every 5 minutes with a 30‑day window:

```
SELECT add_continuous_aggregate_policy(
  'telemetry_observation_5m',
  start_offset => INTERVAL '30 days',
  end_offset => INTERVAL '5 minutes',
  schedule_interval => INTERVAL '5 minutes'
);
```

## Query routing
Telemetry API reads from the cagg when `granularity` is `5m`/`5min`.

## Storage estimates
Use these formulas to estimate storage for raw telemetry + rollups.

Inputs:
- `assets`: number of assets
- `metrics`: metrics per asset (e.g., rainfall, fill)
- `raw_sample_minutes`: raw sample interval in minutes (e.g., 1, 5, 15)
- `samples_per_day`: samples per metric per day (`1440 / raw_sample_minutes`)
- `retention_days`: raw retention window (default 30)

Approximate rows:
```
raw_rows = assets * metrics * samples_per_day * retention_days
rollup_rows = assets * metrics * (24 * 60 / 5) * retention_days
```

Rule of thumb row size (raw telemetry):
- 160–240 bytes per row (data + indexes), depending on indexes and TOAST.

Rule of thumb row size (5m rollup):
- 120–180 bytes per row.

Example (1000 assets, 2 metrics, 1m samples, 30 days):
```
raw_rows ~= 1000 * 2 * 1440 * 30 = 86,400,000
raw_storage ~= 13.8–20.7 GB
rollup_rows ~= 1000 * 2 * 288 * 30 = 17,280,000
rollup_storage ~= 2.1–3.1 GB
```

Validate with real data:
```
SELECT
  pg_size_pretty(pg_total_relation_size('telemetry_observation')) AS raw_size,
  pg_size_pretty(pg_total_relation_size('telemetry_observation_5m')) AS rollup_size;
```
