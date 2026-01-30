#!/usr/bin/env bash
set -euo pipefail
poetry run ruff check .
poetry run mypy src
poetry run pytest -q
