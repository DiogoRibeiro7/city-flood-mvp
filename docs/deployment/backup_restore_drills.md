# Backup/Restore Drills + DR Targets

This document defines backup/restore procedures and DR targets (RTO/RPO) for City Flood MVP.

## Targets

- **RTO (Recovery Time Objective):** 4 hours
- **RPO (Recovery Point Objective):** 15 minutes

Adjust based on tenant SLA and regulatory requirements.

## Backup strategy

### Database

- Point-in-time recovery (PITR) enabled.
- Full backup daily, WAL/archives every 15 minutes.
- Retain backups for 30 days (prod), 7 days (staging).

### Object storage (exports)

- Versioning enabled.
- Lifecycle rule: retain 30 days.

## Drill cadence

- **Quarterly** full restore drill in staging.
- **Monthly** backup verification (spot-restore single table).

## Restore drill checklist

1. Provision a new DB instance from the latest backup.
2. Replay WAL to target point-in-time.
3. Run schema verification: `alembic current`.
4. Run smoke tests (`tests/unit`).
5. Validate API health and a sample query:
   - `/v1/health`
   - `/v1/cities`
6. Validate exports bucket access.
7. Record restore duration and update runbook.

## Failover notes

- Use read-only mode during cutover to avoid data drift.
- Reconcile queued jobs after restore.
- Notify stakeholders if RPO exceeded.

