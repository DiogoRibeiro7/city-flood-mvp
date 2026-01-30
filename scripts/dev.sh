#!/usr/bin/env bash
set -euo pipefail
docker compose up -d --build
echo "API docs: http://localhost:8000/docs"
echo "Web:      http://localhost:5173"
