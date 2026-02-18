# Pilot Readiness

## Pilot Cities (Initial)
- `city_porto_mvp` — coastal, dense urban core, high rainfall variability
- `city_oslo_mvp` — colder climate, snowmelt-driven events, mixed topo
- `city_houston_mvp` — flat topology, floodplain exposure, high runoff peaks

## Onboarding Checklist
- Confirm data sources (telemetry, assets, boundaries)
- Validate ingest contracts and idempotency keys
- Run seed and QA checks for telemetry + assets
- Verify analytics pipelines and report exports
- Configure API access (JWT roles or API keys)
- Define stakeholder contacts and escalation path
- Set baseline KPIs (latency, coverage, freshness)

## Acceptance Criteria
- Telemetry coverage >= 95% for the last 30 days
- End-to-end ingest + analytics latency <= 15 minutes
- Hotspot and event detection stable across 3 consecutive runs
- Export jobs succeed > 99% over 7 days
- UI usability sign-off from at least 2 stakeholders
