# IaC + Secrets Management

This guide outlines a pragmatic Infrastructure-as-Code (IaC) baseline and secrets management approach.
It is provider-agnostic and works for both single-tenant and multi-tenant deployments.

## Recommended IaC structure

- `infra/`
  - `network/` (VPC/VNet, subnets, routing, security groups)
  - `database/` (Postgres/Timescale + backups)
  - `compute/` (API, worker, scheduler, web)
  - `observability/` (metrics + dashboards)
  - `storage/` (object storage buckets)

Use Terraform, Pulumi, or OpenTofu based on your team's standard. Keep environments separate:

- `dev`
- `staging`
- `prod`

## Secrets management

Use a managed secrets store (recommended):

- AWS Secrets Manager
- Azure Key Vault
- GCP Secret Manager
- HashiCorp Vault

Never store secrets in Git, Dockerfiles, or `.env` files committed to the repo.

## Required secrets (minimum)

- `DATABASE_URL`
- `INGEST_TOKEN`
- `JWT_SECRET` (if JWT auth enabled)
- `JWT_ISSUER` (optional)
- `JWT_AUDIENCE` (optional)
- `ANALYTICS_API_KEY` (legacy fallback)
- `EXPORT_BUCKET` (if exports stored in object storage)

## Recommended secrets (optional)

- `SENTRY_DSN` (error tracking)
- `CDSAPI_URL` / `CDSAPI_KEY` (ERA5 / real data)
- `GRAFANA_ADMIN_PASSWORD`

## Injection patterns

Prefer direct environment variable injection from the secrets manager.

If you use Kubernetes, mount secrets as environment variables on:

- API
- Worker
- Scheduler

## Rotation guidance

- Rotate `INGEST_TOKEN` and `JWT_SECRET` quarterly.
- Rotate DB credentials at least every 6 months.
- Use short-lived tokens where possible.

