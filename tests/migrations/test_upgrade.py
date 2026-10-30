"""Exercise data backfills, integrity and bounded migration failure/recovery."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from floodmvp.models.db import Base
from scripts.database_test_support import MigrationDatabase

SEED = Path(__file__).with_name("legacy_seed.sql")


def _rows(connection: sa.Connection, table: str) -> list[dict[str, Any]]:
    # Table names come exclusively from the application's metadata below.
    return list(connection.scalars(sa.text(f'SELECT to_jsonb(t) FROM "{table}" AS t')))


def test_seeded_upgrade_preserves_rows_and_enforces_integrity(
    migrated_db: MigrationDatabase,
) -> None:
    migrated_db.upgrade("0012_job_queue")
    with migrated_db.engine.begin() as connection:
        connection.exec_driver_sql(SEED.read_text(encoding="utf-8"))
        tables = set(sa.inspect(connection).get_table_names()) & Base.metadata.tables.keys()
        before = {table: _rows(connection, table) for table in tables}

    migrated_db.upgrade()
    with migrated_db.engine.begin() as connection:
        for table, original in before.items():
            current = _rows(connection, table)
            assert len(current) == len(original), table
            if original:
                projected = [{key: row[key] for key in original[0]} for row in current]
                assert sorted(
                    map(lambda row: json.dumps(row, sort_keys=True), projected)
                ) == sorted(map(lambda row: json.dumps(row, sort_keys=True), original)), table

        for table in ("analytics_event", "analytics_hotspot_daily"):
            assert connection.execute(sa.text(f"SELECT run_id, confidence FROM {table}")).all() == [
                ("run_latest", 0.5)
            ]
        observation = connection.execute(
            sa.text("SELECT ts, value, source_type, lineage, import_id FROM telemetry_observation")
        ).one()
        assert observation == (dt.datetime(2030, 1, 1, tzinfo=dt.UTC), 0.75, "unknown", {}, None)
        assert connection.execute(
            sa.text("SELECT outlier_count, drift_count FROM telemetry_qa_daily")
        ).one() == (0, 0)
        assert (
            connection.scalar(
                sa.text(
                    "SELECT response->>'payload_hash' FROM ingest_idempotency WHERE idempotency_key='key_legacy'"
                )
            )
            == "fixture"
        )

        invalid_statements = [
            "INSERT INTO asset (asset_id,city_id,asset_type,name) VALUES ('orphan','missing','node','Bad')",
            "UPDATE telemetry_observation SET import_id='missing'",
            "UPDATE telemetry_observation SET scenario_id='missing'",
            "UPDATE analytics_event SET run_id='missing'",
            "UPDATE analytics_hotspot_daily SET run_id='missing'",
            "INSERT INTO ingest_idempotency (idempotency_key,device_id,response) "
            "VALUES ('key_legacy','asset_legacy','{}')",
            # Telemetry uniqueness intentionally remains (asset, metric, ts),
            # including across scenario values: changing it requires a separate design.
            "INSERT INTO telemetry_observation (asset_id,metric,ts,value) "
            "VALUES ('asset_legacy','fill_ratio','2030-01-01 00:00:00+00',0.9)",
        ]
        for statement in invalid_statements:
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(sa.text(statement))
        connection.execute(
            sa.text(
                "INSERT INTO note (note_id,city_id,asset_id,title,body) "
                "VALUES ('note_after','city_legacy','asset_legacy','After upgrade','Fixture')"
            )
        )
        created_at, transaction_now = connection.execute(
            sa.text("SELECT created_at, now() FROM note WHERE note_id='note_after'")
        ).one()
        assert created_at == transaction_now
        assert created_at.utcoffset() == dt.timedelta(0)

    assert "Running upgrade" not in migrated_db.upgrade()


def test_legacy_analytics_without_runs_blocks_until_explicit_repair(
    migrated_db: MigrationDatabase,
) -> None:
    migrated_db.upgrade("0012_job_queue")
    with migrated_db.engine.begin() as connection:
        connection.exec_driver_sql(SEED.read_text(encoding="utf-8"))
        connection.execute(sa.text("DELETE FROM analytics_run"))
    with pytest.raises(AssertionError, match="contains null values"):
        migrated_db.upgrade()
    with migrated_db.engine.begin() as connection:
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version"))
            == "0012_job_queue"
        )
        assert connection.scalar(sa.text("SELECT count(*) FROM analytics_event")) == 1
        # The operator supplies an explicit legacy provenance record, rather
        # than the migration inventing an analytics run or deleting old results.
        connection.execute(
            sa.text(
                "INSERT INTO analytics_run (run_id,city_id,start_ts,end_ts,status,version,params) "
                "VALUES ('run_recovered','city_legacy','2030-01-01 00:00:00+00',"
                "'2030-01-01 01:00:00+00','completed','legacy-fixture',"
                "json_build_object('migration_repair', true))"
            )
        )
    migrated_db.upgrade()
    with migrated_db.engine.connect() as connection:
        assert connection.scalar(sa.text("SELECT run_id FROM analytics_event")) == "run_recovered"


def test_table_lock_times_out_without_advancing_revision(migrated_db: MigrationDatabase) -> None:
    migrated_db.upgrade("0015_analytics_threshold_override")
    with migrated_db.engine.begin() as blocker:
        blocker.execute(sa.text("LOCK TABLE city IN ACCESS EXCLUSIVE MODE"))
        with pytest.raises(AssertionError, match="lock timeout"):
            migrated_db.upgrade()
        assert blocker.scalar(sa.text("SELECT version_num FROM alembic_version")) == (
            "0015_analytics_threshold_override"
        )
    # Retry only after the competing transaction has released the lock.
    migrated_db.upgrade()
