# Disposable recovery drill and proposed targets

Run from the repository root with Python 3.12+ and Docker Compose v2 available:

```sh
poetry run python -m scripts.recovery_drill
```

This builds the backend, provisions two new databases, migrates and seeds only
synthetic data, backs up and restores it, exercises worker recovery, writes
evidence, and removes its containers, volumes, network and backend image tag.
The host runner uses the standard library; application dependencies run inside
the image. A cold build can take several minutes. No application stack, real
provider access or pre-existing database is required.

## Isolation and failure behavior

`docker-compose.recovery.yml` is separate from the application Compose file.
Every invocation generates a fresh `city-flood-recovery-<12 hex>` project and
refuses to adopt existing resources or an image tag. The runner supplies its
own env file, ignores ambient `COMPOSE_*` settings, and uses literal test DB
URLs rather than host `DATABASE_URL` / `TEST_DATABASE_URL`. No DB port is
published. The recovered API binds only a random loopback port. Credentials
in this file are disposable fixture values, not deployment credentials.

Before fault injection or database commands, the runner resolves a full container
ID and verifies its Compose project and service labels. The helper also requires
`APP_ENV=test`, the recovery project prefix, the exact source/restored host,
database, driver, user and port, and no connection query overrides. Restore
refuses a nonempty application schema. There is no arbitrary database argument,
`--clean`, `--create`, volume replacement, or automatic stale-job reset.

Artifacts live in ignored `test-results/recovery/<project>/`: `result.json`,
command/service logs, source/restored fingerprints, a custom-format backup and
the recovered CSV. `--artifacts <directory>` changes the parent only; each run
creates a new child. `--timeout` bounds polling (120 seconds by default), and
`--build-timeout` bounds the image build (1,200 seconds by default). Individual
commands also have timeouts. A failed assertion or cleanup returns nonzero and
records the failed phase. Proposed-target misses are recorded as false; they
do not turn a functionally successful drill into an established service level.

Exercise the archive-integrity failure path separately:

```sh
poetry run python -m scripts.recovery_drill --inject-failure corrupt-backup
```

Expect exit **1**, phase `archive_integrity`, a checksum-mismatch error, and
`cleanup: completed`. It corrupts only that run's local copy of the synthetic
archive and refuses to restore it. Normal failures and interruption attempt
cleanup. If the host is forcibly terminated or Docker becomes unavailable,
use the printed project and retained env file to inspect resources and verify
their project labels before manually removing that exact Compose project;
never use a global Docker prune to clean up a drill.

## What the drill establishes

1. The fixed smoke fixture contains one city, three assets and 36 observations,
   plus a queued export. A committed checkpoint precedes the backup. Both DB
   servers use the same pinned PostgreSQL 16.11 / TimescaleDB 2.25.0 OSS image.
2. `pg_dump --format=custom` writes inside the source container. Binary data
   travels with `docker cp`, avoiding shell text-redirection corruption.
   SHA-256 is checked on the source, host artifact and restored container.
3. One extra synthetic observation is committed **after** the backup. The
   source is stopped. The empty destination enters `timescaledb_pre_restore()`,
   receives serial `pg_restore --exit-on-error --no-owner --no-acl`, then exits
   restore mode with `timescaledb_post_restore()`.
4. Canonical row counts/hashes for every mapped application table and the
   Alembic version must match the pre-backup source. Column, constraint, index,
   hypertable and extension fingerprints must also match. Restored API health,
   city and rainfall reads must succeed. The extra post-backup row is absent.
5. A guarded helper pauses the **real export handler** after the worker claims
   the recovered export. A diagnostic `FOR UPDATE SKIP LOCKED` cannot acquire
   its row. The runner sends SIGKILL to that owned worker and observes exit 137,
   release of the lock, and the original queued state with zero committed
   attempts. Restarting the same container processes one committed attempt;
   its CSV must contain the exact 12 fixture rainfall rows.
6. A separate malformed SQL aggregate fails through the real worker. The
   retry remains queued with one attempt, a retained error, cleared locks and
   five-second backoff; an immediate claim must be excluded. The harness repairs
   only this synthetic export query, preserves its schedule, and lets the
   normal worker CLI complete attempt two. Its exact CSV is checked again.
7. Controlled ten-minute-old timestamps exercise the independent queue snapshot
   for both active unfinished work and a deliberately persisted `running` row.
   The latter remains running: age detection does **not** authorize requeue.
   This does not wait out the alert's five-minute hold or test notifications;
   predicate/hold tests are covered in the [observability runbook](../runbooks/observability.md).

The restore sequence follows the [Timescale logical-backup procedure](https://github.com/timescale/Tiger-Data-Docs/blob/main/src/content/docs/deploy/self-hosted/backup-and-restore/logical-backup.mdx).
The serial restore deliberately avoids `-j`; the [PostgreSQL restore reference](https://www.postgresql.org/docs/16/app-pgrestore.html)
documents the fail-on-error and ownership/ACL options.

## Measurement definitions

Targets below are proposals for review, not tenant SLAs or observed production
attainment. Durations use a monotonic clock; timestamps identify the run.

| Measure | Proposed target | Start / end and interpretation |
| --- | --- | --- |
| Database RTO | 4 hours (14,400 s) | Source-stop request through archive transfer, restore, fingerprint comparison and restored API data read. Destination DB and image are pre-provisioned; provisioning, human detection, routing cutover and real load are excluded. |
| RPO exposure upper bound | 15 minutes (900 s) | Start of the last protected checkpoint action to the source-stop request. Checkpoint commit occurs after this start, so the interval conservatively bounds the checkpoint-to-fault gap. It is not an exact `pg_dump` snapshot timestamp or a backup-frequency guarantee. |
| Worker recovery | 5 minutes (300 s) | SIGKILL request through rollback observation, restart and verified CSV download. Proposed specifically for this drill; separate from the database RTO. |
| Failed-attempt retry | 5 minutes (300 s) | Begin malformed-query attempt through backoff, controlled query repair, second attempt and verified CSV. Includes orchestration and diagnosis probes. |

The observed loss is one deliberately committed post-backup observation. An
equal pre-backup fingerprint proves restoration of the protected fixture;
it does not imply zero RPO. Total elapsed time separately includes builds,
provisioning, all probes and cleanup. Small synthetic timings are not capacity
or disaster-recovery benchmarks.

## Manual recovery decisions

For a real incident, identify the affected environment, exact DB, code revision,
backup age/checksum, extension versions and incident start before changing data.
Preserve the source and restore into a separately provisioned empty destination.
Use the correct backup tooling for that deployment; this runner deliberately
cannot target it. With matching Timescale versions, bracket a serial logical
restore with the pre/post restore calls above and stop on any restore error.
Discard a failed disposable destination and investigate; do not expose a
partially restored database or automatically drop an application database.

Verify migration head, representative row values/counts, constraints, API reads
and export storage before cutover. Pause writers and schedulers while reconciling
the last protected write against subsequent source/provider records; document
the measured loss and an approved replay window. Route applications to the
verified destination only after this reconciliation. Retain the old instance
for investigation rather than overwriting it as part of validation.

For jobs, use administrator `GET /v1/jobs/queue` and inspect worker logs,
`pg_stat_activity` / locks, schedule, attempts, errors and external outputs.
The current worker holds its claim and handler in one transaction: observers
can still see a **queued** row while its handler holds a lock. A killed attempt
rolls back its claim; a replacement worker can claim it after rollback. Check
for external side effects before replay because database rollback does not
undo a file write and does not guarantee exactly-once execution.

Leave future retries scheduled and repair their underlying fault. After
exhaustion, administrator `POST /v1/jobs/queue/{job_id}/retry` supports only
`failed` or `cancelled` jobs; it is not a stuck-running reset. A committed
`running` row with no live owner requires a reviewed, job-specific repair:
stop competing workers, preserve its state, verify no active transaction or
output conflict, reconcile the paired export/analytics state, and agree the
transition before restarting workers. There is intentionally no generic SQL
reset in this runbook. Age alone cannot distinguish slow work from abandonment.

## Remaining deployment work

PITR/WAL shipping, off-site backup storage, restore of roles/ACLs, recovery of
existing external export files, automated schedules, retention policies and
production-scale cutover remain unimplemented or unverified here. This drill
regenerates a pending export after restoring its job row. A proposed daily full
backup, WAL archival with a 15-minute maximum loss window, 30-day production /
7-day staging retention, versioned export storage, monthly spot restore and
quarterly staging incident exercise need deployment owners and separate evidence.
Repeat on the release candidate for [gate G7](../releases/v1-acceptance.md).

## Observed local verification — 2026-11-02

The retained [successful result](recovery-drill-result.json) and
[intentional corruption result](recovery-drill-corruption-result.json) were
produced from clean implementation commit
`2133ba60996a19208f9d824b6af07707b95d6f15`. Only evidence/documentation is added
after that implementation. Host: Windows/PowerShell, Python 3.12.10,
Poetry 2.2.1, Docker Engine 29.8.2, Compose 5.6.0; the backend container uses
the repository's Python 3.14 image. Both database image IDs and exact extension
versions are retained in the result. These are local executions, not hosted CI.

| Observation | Actual result | Proposed target |
| --- | --- | --- |
| DB recovery through verified API read | 14.859 s | 14,400 s |
| Protected-checkpoint exposure upper bound | 13.000 s; one post-backup row lost | 900 s |
| Killed-worker recovery through exact CSV | 15.938 s; one committed successful attempt | 300 s |
| SQL failure, backoff and successful retry | 25.156 s; second committed attempt | 300 s |
| Backup / restore commands | 0.516 s / 1.688 s | No separate target |
| Source/restored equality | Matching row/schema fingerprints; all 36 protected observations restored | Exact match |
| Stale work | Active transaction lock detected; aged persisted running row detected and left running | No automatic reset |
| Full successful run including cleanup | 120.110 s, exit 0, cleanup completed | No separate target |
| Corrupted archive | Exit 1 at `archive_integrity`; checksum refusal before outage/restore; cleanup completed | Expected failure |
| Python checks | Ruff lint and format passed (169 files); mypy passed (83 source files); 522 unit tests passed, 3 skipped | Passing applicable checks |
| Workflow validation | Pinned actionlint passed | Passing validation |

The three skips are existing POSIX file-mode assertions on Windows in
`test_noaa_quality.py`. The real PostgreSQL/Timescale recovery path was exercised
by the drill; the separate full integration/migration pytest suites and web
checks were not rerun for this harness-only change. Raw logs, backups and
fingerprints remain in ignored `test-results/recovery-final/` and
`test-results/recovery-negative/`. The two small result files above are retained
unchanged for review. Checksums, generated job IDs and timestamps vary between
runs; restoration must match within each run.

Reproduce the static and unit checks with:

```sh
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src scripts/export_openapi.py scripts/database_test_support.py scripts/smoke_stack.py scripts/seed_smoke.py scripts/release_manifest.py scripts/recovery_drill.py scripts/recovery_probe.py
poetry run pytest tests/unit -q
```

