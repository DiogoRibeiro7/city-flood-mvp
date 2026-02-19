# Deployment Reference

This document provides a concrete cloud deployment reference for **single-tenant** and **multi-tenant** setups.
It is infrastructure-agnostic and focuses on the minimum components, boundaries, and operational tradeoffs.

## Shared assumptions

- API and web are stateless; state lives in Postgres/Timescale + object storage.
- Background jobs run separately from the API (queue worker).
- Analytics is scheduled (cron/job runner) or triggered by ops.
- Ingress terminates TLS.
- Observability includes metrics + logs.

## Single-tenant reference

### Topology

- 1x DB cluster (TimescaleDB + PostGIS)
- 1x API service (FastAPI)
- 1x Web service (Vite build served behind a static host or reverse proxy)
- 1x Job worker service
- 1x Scheduler service (analytics + periodic jobs)
- 1x Metrics + dashboards (Prometheus + Grafana)
- 1x Object storage bucket (exports, screenshots)

### Network boundaries

- API + Web behind a single public ingress (TLS termination)
- DB and internal services are private subnet only
- Worker and scheduler use internal network only

### Notes

- Use a managed Postgres + Timescale if available; otherwise run Timescale in a dedicated DB VM/cluster.
- Enable PostGIS once per database.
- Configure scheduled analytics via a managed cron job (Kubernetes CronJob, cloud scheduler).

## Multi-tenant reference

### Model

Two supported models depending on scale and data isolation:

1. **Shared DB, tenant-scoped rows**
   - Single DB cluster
   - `city_id` (or `tenant_id`) enforced on every query
   - Lowest cost, simplest ops

2. **Database-per-tenant**
   - One DB per tenant (or per region)
   - Stronger isolation, easier per-tenant maintenance
   - Higher cost and more moving parts

### Topology (shared DB model)

- 1x DB cluster (TimescaleDB + PostGIS)
- 1x API service (multi-tenant aware)
- 1x Web service (tenant selector or subdomain-based)
- N x Job workers (scaled by queue depth)
- 1x Scheduler service
- 1x Metrics + dashboards
- 1x Object storage bucket (path per tenant)

### Topology (DB-per-tenant model)

- N x DB clusters
- 1x API service (routes traffic to tenant DB)
- 1x Web service (tenant selector or subdomain-based)
- N x Job workers (per tenant or shared with routing)
- 1x Scheduler service
- 1x Metrics + dashboards (tenant labels)
- 1x Object storage bucket (path per tenant)

### Network boundaries

- Ingress routes by subdomain: `tenant-a.example.com`, `tenant-b.example.com`
- API uses tenant-aware auth (JWT claim → tenant_id)
- DB traffic never exposed publicly

### Notes

- For shared DB, enforce tenant isolation in API and analytics layers.
- For DB-per-tenant, keep a control plane for tenant registry and credentials.
- Apply per-tenant quotas (exports, job queue, ingest rate).

## Deployment checklist (minimal)

- DB migrations applied
- PostGIS extension enabled
- Queue worker running
- Scheduler running
- API and web behind TLS
- Object storage configured
- Secrets stored in managed secrets service

