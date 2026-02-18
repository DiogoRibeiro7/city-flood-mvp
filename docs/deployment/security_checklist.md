# Security Review Checklist + Compliance Notes

Use this checklist before production deployments or pilot rollouts.

## Access control

- JWT auth enabled for report/export jobs and admin endpoints
- Roles validated server-side (`admin`, `analyst`, `viewer`)
- Ingest token rotated and stored in secrets manager

## Data protection

- TLS enforced on all public endpoints
- DB in private subnet only
- PostGIS enabled with least-privilege DB role
- Object storage bucket private + scoped per tenant

## Application security

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

