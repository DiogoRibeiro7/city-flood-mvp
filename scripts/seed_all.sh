#!/usr/bin/env bash
set -euo pipefail

# Run migrations and seed data from inside the backend container (ensures deps available)

docker compose exec -T backend alembic upgrade head
docker compose exec -T backend python -m floodmvp.jobs.seed_assets
docker compose exec -T backend python -m floodmvp.jobs.seed_telemetry
docker compose exec -T backend python -m floodmvp.jobs.run_analytics

echo "Seed complete."
