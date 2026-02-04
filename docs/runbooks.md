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
