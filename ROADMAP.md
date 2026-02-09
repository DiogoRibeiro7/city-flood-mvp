# City Flood MVP — Roadmap

## Goals
- Move from demo-ready to pilot-ready: multi-city support, real data adapters, and stronger reliability.
- Make analytics configurable, auditable, and comparable across cities and scenarios.
- Improve UX for investigations, reports, and stakeholder communication.

## New milestones (post-MVP)

### Milestone 7 — Multi-city + tenancy (2–3 weeks)
- [ ] Seed and validate 2–3 distinct city datasets (different topology, scale, and climate).
- [ ] Add city-aware configuration (thresholds, assets, event definitions) with overrides.
- [ ] Ensure all endpoints and analytics are fully city-scoped and isolated.
- [ ] Add data export by city and a simple city switcher in the UI.

### Milestone 8 — Real data adapters (2–4 weeks)
- [ ] Define ingestion contracts for external telemetry (CSV + JSON + streaming).
- [ ] Build at least one real-world adapter (rain gauge or water level feeds).
- [ ] Add validation + normalization pipeline with rejection reasons and stats.
- [ ] Document onboarding steps for a new city data source.

### Milestone 9 — Reliability + scale (2–4 weeks)
- [ ] Add background job queue with retries for analytics and exports.
- [ ] Add DB retention + rollup policies with storage cost estimates.
- [ ] Add load testing and establish performance budgets per endpoint.
- [ ] Add alerting rules tied to SLA objectives (API, ingest, analytics delays).

### Milestone 10 — Analytics evolution (2–4 weeks)
- [ ] Add calibration tools for event thresholds (per city / seasonality).
- [ ] Support scenario comparison and “what-if” deltas in the API.
- [ ] Add confidence scores for events/hotspots.
- [ ] Version analytics outputs and surface diffs between versions.

### Milestone 11 — Decision-ready UX (2–3 weeks)
- [ ] Add incident timeline view and event drill-downs.
- [ ] Add report builder (PDF/CSV) for stakeholder summaries.
- [ ] Improve map storytelling (annotations, bookmarks, shareable links).
- [ ] Add role-based access and saved views.

### Milestone 12 — Deployment hardening (2–3 weeks)
- [ ] Define cloud deployment reference (single-tenant + multi-tenant).
- [ ] Add IaC templates and secrets management guidance.
- [ ] Add backup/restore drills and disaster recovery RTO/RPO targets.
- [ ] Finalize security review checklist and compliance notes.

## Open questions
- Which city should be the first real-data pilot?
- What level of operational uptime is required (business hours vs 24/7)?
- Which analytics outputs need formal sign-off (regulatory or contractual)?
