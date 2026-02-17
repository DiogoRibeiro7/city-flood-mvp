#!/usr/bin/env bash
set -euo pipefail

# Run migrations and seed data from inside the backend container (ensures deps available)

env_args=()
for var in TELEMETRY_REALISM TELEMETRY_YEARS TELEMETRY_DAYS TELEMETRY_SCENARIO PIPE_TELEMETRY_LIMIT; do
  if [[ -n "${!var:-}" ]]; then
    env_args+=("-e" "${var}=${!var}")
  fi
done

echo "Running migrations..."
docker compose exec -T "${env_args[@]}" backend alembic upgrade head
echo "Seeding assets..."
docker compose exec -T "${env_args[@]}" backend python -m floodmvp.jobs.seed_assets
echo "Seeding telemetry..."
docker compose exec -T "${env_args[@]}" backend python -m floodmvp.jobs.seed_telemetry
echo "Running analytics..."
docker compose exec -T "${env_args[@]}" backend python -m floodmvp.jobs.run_analytics

echo "Seed complete."
