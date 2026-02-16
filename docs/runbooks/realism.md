# Telemetry Realism (Tier 2, Porto)

This runbook enables data-driven synthetic telemetry using ERA5-Land hourly precipitation for Porto,
disaggregated to 5-minute rain, then propagated to river level and pipe hydraulics.

## Prerequisites
- Create a Copernicus Data Store account and accept the ERA5-Land license.
- Create a `~/.cdsapirc` file with your CDS API key:
  ```
  url: https://cds.climate.copernicus.eu/api
  key: <UID>:<API_KEY>
  ```

## Generate Tier 2 telemetry
Set environment variables and run the seed job:
```
set TELEMETRY_REALISM=tier2_porto
set TELEMETRY_YEARS=1
set PIPE_TELEMETRY_LIMIT=150
poetry run python -m floodmvp.jobs.seed_telemetry
```

Artifacts are cached under `data/realism/`:
- `era5_land_hourly_precip.nc` (hourly totals)
- `porto_realism_stats.json` (P95/P99 summaries)

## Notes
- 1 year at 5-minute resolution is large. Adjust `PIPE_TELEMETRY_LIMIT` if needed.
- ERA5-Land total precipitation values are hourly accumulations in meters; they are converted to mm
  and disaggregated into 5-minute intensities.
