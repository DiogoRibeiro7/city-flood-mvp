SHELL := /bin/bash

.PHONY: up down seed test lint loadtest

up:
	docker compose up -d --build

down:
	docker compose down

seed:
	poetry run python -m floodmvp.jobs.seed_assets
	poetry run python -m floodmvp.jobs.seed_telemetry

test:
	poetry run pytest -q

lint:
	poetry run ruff check .
	poetry run mypy src
	cd web && npx prettier --check .

loadtest:
	k6 run scripts/loadtest/k6-smoke.js
