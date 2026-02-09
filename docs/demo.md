# Demo script (2–3 minutes)

## Prep
- Ensure the stack is up: `docker compose up -d --build`
- Seed data: `./scripts/seed_all.sh`
- Open web UI at `http://localhost:5173`

## Screenshots
- Map layers: `docs/screenshots/01-map-layers.png`
- Hotspot detail: `docs/screenshots/02-hotspot-asset.png`
- Events card: `docs/screenshots/03-events-card.png`
- Grafana dashboard: `docs/screenshots/04-grafana-dashboard.png`

## Storyline
1) Open the map and explain the synthetic asset network (pipes, rivers, gauges).
2) Toggle layers to show data density and hotspots.
3) Use tag filters to focus on a basin/neighborhood.
4) Click a hotspot pipe and show the telemetry chart (range 24h → 7d).
5) Highlight event summaries (rain/overflow) and severity badges.
6) Show API docs at `http://localhost:8000/docs` and point to hotspots/events endpoints.
7) (Optional) Open Grafana at `http://localhost:3000` and show the API latency + DB panels.

## Expected outcomes
- Map renders with multiple layers.
- Hotspot list highlights risk assets.
- Telemetry chart updates with time range and metric.
- Events list shows recent rain/overflow entries.

## Troubleshooting
- If data is missing, run `./scripts/reset_demo.sh`.
- If Grafana is empty, confirm Prometheus is up and `/metrics` responds.
