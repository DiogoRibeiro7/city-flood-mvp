# Backfill Runbook

## Goal
Seed a dev or demo environment with synthetic assets and telemetry.

## Prerequisites
- Database is running (Docker or external Postgres/Timescale)
- `DATABASE_URL` points to the target database
- Python deps installed with Poetry

## Seed assets
```
poetry run python -m floodmvp.jobs.seed_assets
```

## Seed telemetry
```
export TELEMETRY_SCENARIO=heavy_rain_high_river
poetry run python -m floodmvp.jobs.seed_telemetry
```

## Notes
- Seeding telemetry selects a subset of pipes to keep runtime reasonable.
- Telemetry scenario options: `normal`, `heavy_rain_low_river`, `heavy_rain_high_river`.
