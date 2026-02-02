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
