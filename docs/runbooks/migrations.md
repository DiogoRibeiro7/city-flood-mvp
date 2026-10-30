# Migration verification and deployment procedure

The migration suite runs the real Alembic CLI against fresh disposable
PostgreSQL/TimescaleDB databases. Ordinary integration tests recreate ORM
tables and cannot establish that the migration chain works.

## Reproduce the checks

Use Python 3.12 and a **new disposable database container**, following the
[test database setup](../releases/v1-acceptance.md#disposable-postgresql-integration-checks).
Set `TEST_DATABASE_URL` to that container's loopback port and `floodmvp_test`
database. The test role needs `CREATEDB` and permission to enable the extensions
in `infra/db/init.sql`; the disposable container's `postgres` role supplies both.
Run from the repository root:

```text
poetry run pytest -q tests/unit/test_migration_database_safety.py tests/integration/test_database_safety.py
poetry run pytest -q tests/migrations --junitxml=test-results/migrations.xml
poetry run pytest -q tests/integration
```

With no `TEST_DATABASE_URL`, database-dependent tests skip; a skip is not
migration evidence. Application/non-test names, non-PostgreSQL URLs, malformed
URLs, and URL query overrides such as `?dbname=production` fail before connection.
The shared safeguard never falls back to `DATABASE_URL`.

Each migration test creates a unique `test_migrations_<uuid>` database from
`template0`, enables the actual extension bootstrap, and sets the child Alembic
process's `DATABASE_URL` explicitly. It never resets the supplied parent DB.
Cleanup closes its connections and drops only the child database successfully
created by that invocation, including after a failed assertion or upgrade.
The ordinary integration suite still recreates tables in the supplied test DB;
keep the entire server disposable. Remove the test container after the run.

The test migration process has a 120-second timeout, a 5-second PostgreSQL lock
timeout, and a 60-second statement timeout. These are test bounds, not measured
deployment service objectives. The backend CI database job runs both suites.

## Verified coverage

- One base and one head, a continuous revision chain, fresh upgrade to head,
  and a repeat upgrade with no migration execution or index replacement.
- Application tables, columns/types, primary and unique keys, foreign keys and
  their update/delete behavior against ORM metadata. All datetime columns are
  timezone-aware. The exact 20 legacy nullability exceptions below remain visible.
- PostGIS, TimescaleDB, UUID and trigram extensions; telemetry hypertable/time
  dimension; valid/ready indexes, ORM lookup coverage by leading index columns,
  and critical GIST, BRIN, partial, analytics and idempotency-expiry indexes.
- Upgrade from `0012_job_queue` with representative synthetic rows across 14
  tables, including a spatial asset, tagged/scenario telemetry, idempotency
  response, queued export/log, two analytics runs, event, hotspot and QA row.
  Existing values survive; latest-run backfill, confidence and provenance/QA
  defaults are checked. Fixture timestamps in 2030 avoid retention expiry.
- Rejection of orphan foreign keys and duplicate idempotency/telemetry keys;
  offset timestamp round-trip and server-generated transaction timestamps.
- A legacy city with analytics results but no run blocks at `0013`; data and
  revision are retained. An explicit synthetic provenance repair permits retry.
- A competing table lock blocks `0016`, times out without advancing the
  revision, and succeeds on retry after releasing the lock.

## Manual deployment steps

1. Identify the exact host/database and current revision, retain a backup with
   a tested restore procedure, and review the upgrade on a restored disposable
   copy. Run `poetry run alembic current`, `heads`, and `history` using an explicit
   deployment `DATABASE_URL`. Alembic's local fallback is not a target selector.
2. Enable `infra/db/init.sql` in the target database with an extension-capable
   role before the first Alembic revision. Installing an image containing
   extensions does not enable them per database. Revision `0001` requires both
   PostGIS geometry and Timescale `create_hypertable`; plain PostgreSQL is
   insufficient. Existing deployments normally already have these extensions.
3. When upgrading from before `0013`, inspect legacy analytics provenance with
   the read-only queries below. Resolve missing runs or ambiguous latest-run
   timestamps from actual provenance before proceeding. The migration assigns
   every existing event/hotspot in a city to its latest run; verify that this
   assignment is appropriate for the historical data. It cannot reconstruct
   original event-to-run history.
4. Use **one migration process per database**, coordinated by the deployment
   system/operator. The current Alembic environment has no cross-process
   advisory lock. Pause affected writers and schedule a maintenance window for
   table alterations/backfills. Set an explicit `PGOPTIONS` lock/statement
   timeout suitable for the data volume and approved window.
5. Run `poetry run alembic upgrade head`, then verify `alembic current`, extension
   state, invalid indexes, row counts and representative application reads.
   Run the smoke workflow against disposable resources before releasing the
   application change. Retain the command output and revision in deployment logs.

Preflight at revision `0012`:

```sql
WITH result_cities AS (
    SELECT city_id FROM analytics_event
    UNION SELECT city_id FROM analytics_hotspot_daily
)
SELECT c.city_id
FROM result_cities c
WHERE NOT EXISTS (SELECT 1 FROM analytics_run r WHERE r.city_id = c.city_id);

-- Review ties, especially at each city's latest created_at.
SELECT city_id, created_at, count(*)
FROM analytics_run
GROUP BY city_id, created_at HAVING count(*) > 1;
```

If a city lacks an actual run record, stop and establish an explicit, reviewed
legacy provenance record or another data-preserving migration plan. Do not
delete analytics to make the upgrade pass or label reconstructed history as a
new observed run. Tests demonstrate failure/retry with synthetic data only.

### Transaction and index caveats

Revisions `0003`, `0009`, and `0018` use Alembic autocommit blocks. An entire
`upgrade head` is therefore **not one atomic transaction**: earlier work may
already be committed when a later step fails. Inspect the actual revision and
objects before retrying; do not use an automatic downgrade as a recovery plan.

`0009` creates two ordinary-table indexes concurrently, but its index drops and
telemetry hypertable index creation use ordinary DDL. Backfills, primary-key
changes and `SET NOT NULL` also acquire locks. Concurrent index creation does
not make the full migration lock-free.

After interrupted concurrent index creation, inspect validity:

```sql
SELECT n.nspname, c.relname, i.indisvalid, i.indisready,
       pg_get_indexdef(i.indexrelid)
FROM pg_index i
JOIN pg_class c ON c.oid = i.indexrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND (NOT i.indisvalid OR NOT i.indisready);
```

`CREATE INDEX IF NOT EXISTS` does not repair an existing invalid index. Have the
operator inspect its ownership/constraints, remove the invalid index using the
appropriate DDL, and recreate it from the reviewed revision before retrying.
No automatic deletion or forced session termination is part of this harness.

## Audit findings and remaining differences

The 2026-10-30 audit starts at `develop`
`11df3ef0e94cf0696ea2023d888148bd8d22f3ca`, after prompt 3. Eighteen revisions
lead from `0001_init` to `0018_ingest_expiry`; `0015` widens Alembic's version
column to 64 characters. Historical revisions are unchanged by this follow-up.

**Fixed ORM timestamp defaults:** `server_default="now()"` generated a quoted
literal which PostgreSQL resolved at table creation. Reflected defaults showed
a constant timestamp. All 20 model timestamp defaults now use `text("now()")`,
matching migration-created defaults. This fixes new ORM-created databases;
`create_all()` does not alter existing columns. For an existing database created
from ORM metadata, inspect `information_schema.columns.column_default` and plan
explicit `ALTER TABLE ... ALTER COLUMN ... SET DEFAULT now()` repairs for each
affected column. Changing defaults fixes future inserts; recovering historical
timestamps requires independent provenance. Migration-created databases already
have function defaults and need no new revision for this fix.

**Nullability:** the migrations permit NULL on 20 generated timestamp columns
while the ORM requires values. The exact table/column set is asserted in
[`test_schema.py`](../../tests/migrations/test_schema.py). New/unexpected drift
fails the suite. Resolving existing NULL values and adding constraints requires
a reviewed repair/backfill migration; tests do not claim complete schema identity.

**Defaults/indexes:** ORM client defaults and migration server defaults are not
interchangeable for direct SQL writers. Migration indexes additionally include
specialized/compound definitions; the suite checks valid indexes and ORM lookup
coverage, not identical index names/counts. `server_onupdate` markers do not
create PostgreSQL update triggers; application updates remain responsible for
`updated_at` values. Telemetry uniqueness still excludes `scenario_id`, so two
scenarios cannot store the same asset/metric/timestamp independently. Note event
and cross-city reference consistency remain application checks where no database
constraint expresses them.

**Optional Timescale features:** revision `0003` catches unsupported retention
and continuous-aggregate operations (and a transaction restriction when creating
the aggregate). Passing migrations alone does not prove these features exist.
The suite records actual extension versions, aggregate count and retention job
count in JUnit properties. This audit's OSS image had **zero continuous aggregates
and zero retention policies**. Retention guarantees require separate verification
on the intended deployment edition/configuration.

## Observed local verification

Python 3.12.10; fresh `timescale/timescaledb-ha:pg16.11-ts2.25.0-all-oss`
container without host data mounts; TimescaleDB 2.25.0, PostGIS 3.6.1.

- Unit suite: **359 passed**. Database suites: **38 integration + 5 migration
  tests passed**, no skips. Failure/retry cases are expected assertions.
- Local JUnit artifacts: `test-results/migration-unit.xml` and
  `test-results/migration-postgres.xml`; no child migration databases remained.
- `ruff check .` passed. `ruff format --check .` still flags **51 existing
  files** (52 at baseline); the touched model file is now formatted.
- `mypy src scripts/export_openapi.py scripts/database_test_support.py`: passed.
- Alembic emits its existing `path_separator` deprecation warning.
- No web changes or public schema changes; web checks and the full-stack smoke
  were not repeated for this database-focused change. The public-schema snapshot
  assertion passed in the unit suite. No remote CI result is claimed.

G2 has automated fresh/seeded verification but remains partial for legacy
nullability repair and deployment-specific policy/locking/upgrade review.
