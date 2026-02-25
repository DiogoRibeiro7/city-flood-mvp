# Ops runbooks

## Backup

### Database logical backup
1) Create a logical dump from the host:
   `docker compose exec -T db pg_dump -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-floodmvp} -Fc > backup.dump`
2) Store the dump in secure storage.

### Volume snapshot (fast path)
- For local Docker: stop the stack and copy the volume folder (`db_data`).
- For production: take a storage snapshot of the Postgres volume.

## Restore

### Restore from pg_dump
1) Ensure the target DB is empty or drop/recreate it.
2) Restore:
   `docker compose exec -T db pg_restore -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-floodmvp} --clean --if-exists < backup.dump`
3) Restart backend to re-init caches if needed.

### Restore from volume snapshot
- Replace the Postgres data volume with the snapshot, then start services.

## Retention

### Timescale policies
- Verify policies:
  `docker compose exec -T db psql -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-floodmvp} -c "SELECT * FROM timescaledb_information.jobs ORDER BY job_id;"`
- If policies are missing, re-run migrations or add policies in `infra/db/migrations`.

### Data pruning
- Use Timescale retention policies where possible.
- For ad-hoc cleanup, remove old telemetry with a `DELETE` scoped by timestamp and city.

## Scaling

### Backend
- Horizontal scale the `backend` service and place it behind a load balancer.
- Increase `uvicorn` workers and keep request timeout aligned with analytics jobs.

### Database
- Increase Postgres resources (CPU/RAM/IOPS) first.
- Consider read replicas for analytics-heavy workloads.
- Keep indexes in sync with query patterns and run `VACUUM`/`ANALYZE` regularly.

### Observability
- Persist Prometheus data to a volume for longer retention.
- Increase scrape interval for lower overhead if needed.
- Use Grafana provisioning for dashboards and datasources in `infra/observability/grafana`.

## Performance
- See `docs/runbooks/performance.md` for load testing and p95 latency budgets.

## Telemetry realism
- See `docs/runbooks/realism.md` for Tier 2 data-driven telemetry (Porto).

## Analytics calibration
- See `docs/runbooks/calibration.md` for threshold recommendations and overrides.

## Daily ops
### Alerts triage
1) Check Prometheus alerts and identify the impacted service (API, ingest, analytics).
2) Confirm recent deploys or config changes for the affected service.
3) Review `docker compose logs -f backend` (or production logs) for the request_id.
4) Validate database health (`/metrics`, `pg_stat_activity`, and CPU/IO saturation).
5) If telemetry ingestion is impacted, pause exports and notify stakeholders.

### Incident response
1) Open an incident record with time, scope, and primary responder.
2) Mitigate impact (scale backend, pause heavy jobs, or apply rate limits).
3) Validate recovery using `/v1/health` and `/metrics`.
4) Communicate resolution with a short summary and next actions.
5) Schedule a postmortem if impact lasted > 30 minutes.

## Weekly QA report
Generate a coverage + gaps + anomaly summary for the last 7 days:
```
python -m floodmvp.jobs.qa_weekly_report --days 7
```
The report is saved in `data/exports/` by default. Use `--out` to override.
