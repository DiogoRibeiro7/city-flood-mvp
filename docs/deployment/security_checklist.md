# Security Review Checklist + Compliance Notes

Use this checklist before production deployments or pilot rollouts.

## Access control

- JWT auth enabled for report/export jobs and admin endpoints
- Roles validated server-side (`admin`, `analyst`, `viewer`)
- `APP_ENV=prod` (or other non-development setting), with `JWT_SECRET`
  configured; without JWT or `ANALYTICS_API_KEY`, privileged requests return 503
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
- Rate limiting enabled (per-IP)
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

