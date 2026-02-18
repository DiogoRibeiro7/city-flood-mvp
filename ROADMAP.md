# City Flood MVP — Roadmap (Next Phase)

## Goals (2026 H1)
- Move from pilot-ready to production-ready
- Harden data quality and operational SLAs
- Expand decision-support UX beyond dashboards
- Enable onboarding of real-world telemetry at scale

## Milestone A — Pilot Ops Readiness (2–3 weeks)
- [x] Define pilot cities, onboarding checklist, and acceptance criteria
- [ ] Add runbook for daily ops (alerts triage + incident response)
- [ ] Add API usage analytics and per-tenant quotas
- [ ] Establish weekly QA report (coverage, gaps, anomalies)

## Milestone B — Data Quality + Governance (3–4 weeks)
- [ ] Implement automated QA rules engine (outliers, gaps, drift)
- [ ] Add telemetry lineage and source tagging per record
- [ ] Add dataset versioning + validation reports for imports
- [ ] Add data retention policies per city + compliance tags

## Milestone C — UX 2.0 for Decision Support (3–4 weeks)
- [ ] Add incident report templates (storm response, asset failure, maintenance)
- [ ] Add collaborative notes + annotations with shareable links
- [ ] Add “executive mode” summary view
- [ ] Add interactive scenario comparison panel in UI

## Milestone D — Scaling + Reliability (3–4 weeks)
- [ ] Implement horizontal job worker autoscaling
- [ ] Add SLO dashboards (API, ingest, analytics latency)
- [ ] Add failover drill automation + postmortem templates
- [ ] Add blue/green deployment playbook

## Milestone E — Real Data Integrations (4–6 weeks)
- [ ] Add ingestion connector for a public hydro API (real data)
- [ ] Add adapter SDK for partner data feeds
- [ ] Add backfill pipeline with audit logs
- [ ] Add streaming ingestion via Kafka (optional)

## Open Questions
- What is the next target pilot city and stakeholder?
- What are the minimum uptime and data freshness SLAs?
- Which compliance frameworks (if any) should be targeted?
