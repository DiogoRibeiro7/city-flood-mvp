#!/usr/bin/env bash
set -euo pipefail

# Full environment reset for demo reproducibility.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "Stopping stack and removing volumes..."
docker compose down -v

echo "Starting core services..."
docker compose up -d --build db backend web prometheus grafana

echo "Waiting for DB to become healthy..."
for i in {1..30}; do
  if docker compose exec -T db pg_isready -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-floodmvp}" >/dev/null 2>&1; then
    echo "DB is ready."
    break
  fi
  sleep 2
  if [ "$i" -eq 30 ]; then
    echo "DB did not become ready in time." >&2
    exit 1
  fi
done

echo "Running migrations and seeding demo data..."
./scripts/seed_all.sh

echo "Demo reset complete."
