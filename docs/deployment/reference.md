# Deployment Reference

The target release supports a **dedicated single-tenant deployment with one API
process and one API replica**. `DEPLOYMENT_TENANT_ID` binds authenticated data
access to that tenant; all records in its database/export store belong to it.
Quotas remain process-local. Do not scale the API, including overlapping rollout
replicas, until shared enforcement is implemented and measured. The backend image
passes `--workers 1` explicitly; the Compose backend declares one replica.
Worker scraping is configured separately. See the [security review](../releases/security-review.md).
The repository's demo Compose ports bind only to loopback. Remote service
exposure must be configured explicitly behind the deployment's trusted ingress.
The cloud and multi-tenant topologies below are future design options, not
verified deployment capabilities. Operational readiness still requires the
[acceptance evidence](../releases/v1-acceptance.md).

## Shared assumptions

- API and web are stateless; state lives in Postgres/Timescale + object storage.
- Background jobs run separately from the API (queue worker).
- Analytics is scheduled (cron/job runner) or triggered by ops.
- Ingress terminates TLS.
- Observability includes metrics + logs.

## Single-tenant reference

### Topology

- 1x DB cluster (TimescaleDB + PostGIS)
- 1x API service (FastAPI), exactly one process / one replica
- 1x Web service (Vite build served behind a static host or reverse proxy)
- 1x Job worker service
- 1x Scheduler service (analytics + periodic jobs)
- 1x Metrics + dashboards (Prometheus + Grafana)
- 1x Object storage bucket (exports, screenshots)

### Network boundaries

- API + Web behind a single public ingress (TLS termination); allow only known
  proxy peers for forwarded headers and prohibit direct API access
- Metrics, database and management/schema endpoints remain private at ingress
- DB and internal services are private subnet only
- Worker and scheduler use internal network only

### Notes

- Use a managed Postgres + Timescale if available; otherwise run Timescale in a dedicated DB VM/cluster.
- Enable PostGIS once per database.
- Configure scheduled analytics via a managed cron job (Kubernetes CronJob, cloud scheduler).

## Multi-tenant reference

### Model

Two possible future models, each requiring implementation and isolation tests:

Neither model is enabled by the deployment-tenant setting. It rejects tokens
for other tenants; it does not select a database or filter individual rows.

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

