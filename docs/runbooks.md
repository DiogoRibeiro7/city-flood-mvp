# Ops runbooks

## Backup

Use the [disposable recovery drill](deployment/backup_restore_drills.md) to
exercise a logical backup on synthetic data with checksums and recorded
database/extension versions: `poetry run python -m scripts.recovery_drill`.
It copies the binary archive without shell text redirection. Configure secure
storage, schedules, retention and PITR separately for an actual deployment.

## Restore

Restore to a separate empty destination and preserve the source. Follow the
[Timescale restore and manual cutover steps](deployment/backup_restore_drills.md#manual-recovery-decisions),
including pre/post restore calls, fail-on-error behavior, data/schema validation
and write reconciliation. Do not replace the application's database or volume
to test a backup. Physical snapshots require a deployment-specific consistency
and recovery procedure; they are not tested by the logical drill.

## Retention

### Timescale policies
- Verify policies:
  `docker compose exec -T db psql -U ${POSTGRES_USER:-postgres} -d ${POSTGRES_DB:-floodmvp} -c "SELECT * FROM timescaledb_information.jobs ORDER BY job_id;"`
- If policies are missing, re-run migrations or add policies in `infra/db/migrations`.

### Data pruning
- Use Timescale retention policies where possible.
- For ad-hoc cleanup, remove old telemetry with a `DELETE` scoped by timestamp and city.
- Run the analytics scheduler for bounded seven-day ingestion idempotency
  cleanup. Requests only expire their own keyed records; see the
  [ingestion runbook](runbooks/ingest.md) for maintenance and index details.

## Scaling

### Backend
- Request quotas are process-local. Adding API replicas or `uvicorn` workers
  changes their effective limits; a shared-state strategy or an explicit
  single-worker deployment constraint must be verified before scaling.
- Tenant attribution in request metrics does not establish tenant data
  isolation. See the [deployment limitations](deployment/reference.md) and
  [release security gate](releases/v1-acceptance.md) before exposing shared data.

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
### Queue state
- Inspect `GET /v1/jobs/queue` with an administrator credential when investigating
  exports or analytics workers. The worker keeps its claim and handler in one
  transaction, so a queued row can represent active locked work. Confirm worker
  activity and DB locks; persisted lock fields alone do not prove a live owner.
- A queued retry retains `last_error` for diagnosis until it succeeds or is
  manually retried. Check `scheduled_at` before assuming the queue is stalled.
- Use the [recovery decision guide](deployment/backup_restore_drills.md#manual-recovery-decisions)
  before restarting workers or repairing an abandoned job. Automatic backoff,
  killed-claim rollback and stale-job detection are covered by the disposable drill.

### Alerts triage
1) Check Prometheus alerts and identify the impacted service (API, ingest, analytics).
2) Confirm recent deploys or config changes for the affected service.
3) Review `docker compose logs -f backend` (or production logs) for the request_id.
4) Validate database health (`/metrics`, `pg_stat_activity`, and CPU/IO saturation).
5) If telemetry ingestion is impacted, pause exports and notify stakeholders.

### Incident response
1) Open an incident record with time, scope, and primary responder.
2) Mitigate impact (scale backend, pause heavy jobs, or apply rate limits).
3) Validate recovery using `/v1/health`, actual data reads, queue outcomes and
   `/metrics`; record recovery duration and the last protected write using the
   [drill measurement definitions](deployment/backup_restore_drills.md#measurement-definitions).
4) Communicate resolution with a short summary and next actions.
5) Schedule a postmortem if impact lasted > 30 minutes.

## Weekly QA report
Generate a coverage + gaps + anomaly summary for the last 7 days:
```
python -m floodmvp.jobs.qa_weekly_report --days 7
```
The report is saved in `data/exports/` by default. Use `--out` to override.
