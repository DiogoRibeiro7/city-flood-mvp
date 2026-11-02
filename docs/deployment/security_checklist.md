# Security Review Checklist + Compliance Notes

Use this checklist before production deployments or pilot rollouts.

## Access control

- Dedicated tenant DB/export store and matching `DEPLOYMENT_TENANT_ID`; no
  other tenant's data present in those stores
- JWT auth enabled for all data reads and privileged operations
- Roles validated server-side (`admin`, `analyst`, `viewer`)
- `APP_ENV=prod` (or other non-development setting), with `JWT_SECRET`
  configured; without a deployment ID and JWT or `ANALYTICS_API_KEY`, data
  requests return 503. JWTs require expiry, subject, role and matching tenant
- Note reads and writes authenticated; note reads require at least the `viewer`
  JWT role (or the configured legacy API key when JWT is disabled)
- Note responses marked `Cache-Control: private, no-store`
- `INGEST_TOKEN` set to a unique deployment secret (not `dev-ingest-token`),
  rotated and stored in a secrets manager; production startup must reject
  missing or demo credentials

## Data protection

- TLS enforced on all public endpoints
- DB in private subnet only
- PostGIS enabled with least-privilege DB role
- Object storage bucket private + scoped per tenant

## Application security

- Browser CORS allowlist configured for deployed UI origins; no wildcard
  outside local development (`CORS_ALLOWED_ORIGINS`)
- Input validation at API boundaries
- Exactly one API process (`uvicorn --workers 1`) and one replica, including
  during rollouts; process-local quotas do not support horizontal API scaling
- Only intended reverse proxies trusted for forwarded headers; direct access blocked
- Runtime browser token only; no signing secret/API key/ingest token in `VITE_*`
- Private ingress for metrics and management endpoints
- Dependency scan (Dependabot) enabled
- Non-root containers where possible

## Observability + audit

- Access logs stored centrally
- Job queue failures alerting configured
- Export jobs logged with metadata

## Compliance notes

This project is **not** a compliance-certified product. For regulated environments:

- Run a dedicated security review (threat model + pen test)
- Enforce least-privilege IAM policies
- Enable audit logging and retention
- Review data residency requirements
- Document data retention policies

