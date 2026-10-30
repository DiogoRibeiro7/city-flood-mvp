"""Inspect actual migrated PostgreSQL objects, never metadata-created substitutes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from floodmvp.models.db import Base
from scripts.database_test_support import ROOT, MigrationDatabase

# Historical revisions allow NULL for these server-generated timestamps. Keep
# this exact, visible exception set until a reviewed data-repair/constraint migration.
LEGACY_NULLABLE_TIMESTAMPS = {
    ("city", "created_at"),
    ("asset", "created_at"),
    ("asset_tag", "created_at"),
    ("telemetry_observation", "ingested_at"),
    ("ingest_idempotency", "created_at"),
    ("scenario_run", "created_at"),
    ("export_job", "created_at"),
    ("export_job", "updated_at"),
    ("export_job_log", "created_at"),
    ("dataset_import", "created_at"),
    ("note", "created_at"),
    ("note", "updated_at"),
    ("job_queue", "created_at"),
    ("job_queue", "updated_at"),
    ("analytics_event", "created_at"),
    ("asset_status_latest", "updated_at"),
    ("analytics_run", "created_at"),
    ("analytics_run", "updated_at"),
    ("telemetry_qa_daily", "created_at"),
    ("analytics_threshold_override", "created_at"),
}


def _include_columns(obj: Any, name: str, kind: str, reflected: bool, compare_to: Any) -> bool:
    if kind == "table":
        return name in Base.metadata.tables
    return kind == "column"


def _assert_schema(engine: sa.Engine) -> None:
    inspector = sa.inspect(engine)
    assert set(inspector.get_table_names()) == set(Base.metadata.tables) | {
        "alembic_version",
        "spatial_ref_sys",
    }
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"include_object": _include_columns})
        differences = compare_metadata(context, Base.metadata)
    nullable_drift = set()
    for group in differences:
        assert isinstance(group, list), group
        for diff in group:
            assert diff[0] == "modify_nullable", diff
            assert diff[-2:] == (True, False), diff
            nullable_drift.add((diff[2], diff[3]))
    assert nullable_drift == LEGACY_NULLABLE_TIMESTAMPS

    for table in Base.metadata.sorted_tables:
        assert inspector.get_pk_constraint(table.name)["constrained_columns"] == [
            column.name for column in table.primary_key
        ]
        actual_fks = {
            (
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
                fk.get("options", {}).get("ondelete"),
                fk.get("options", {}).get("onupdate"),
            )
            for fk in inspector.get_foreign_keys(table.name)
        }
        model_fks = {
            (
                tuple(fk.column_keys),
                fk.referred_table.name,
                tuple(e.column.name for e in fk.elements),
                fk.ondelete,
                fk.onupdate,
            )
            for fk in table.foreign_key_constraints
        }
        assert actual_fks == model_fks, table.name
        assert {
            tuple(item["column_names"]) for item in inspector.get_unique_constraints(table.name)
        } == {
            tuple(column.name for column in constraint.columns)
            for constraint in table.constraints
            if isinstance(constraint, sa.UniqueConstraint)
        }
        indexes = inspector.get_indexes(table.name)
        for index in table.indexes:
            names = [column.name for column in index.columns]
            # A wider index with the same leading columns covers the ORM lookup;
            # legacy migration names need not equal ORM-generated index names.
            assert any(
                item["column_names"][: len(names)] == names
                and not item.get("dialect_options", {}).get("postgresql_where")
                for item in indexes
            ), (table.name, index.name)
        for column in inspector.get_columns(table.name):
            if isinstance(column["type"], sa.DateTime):
                assert column["type"].timezone, (table.name, column["name"])
            if (table.name, column["name"]) in LEGACY_NULLABLE_TIMESTAMPS:
                assert column["default"] == "now()"


def test_migration_from_zero_matches_models_and_repeat_is_noop(
    migrated_db: MigrationDatabase, record_testsuite_property: Callable[[str, object], None]
) -> None:
    first = migrated_db.upgrade()
    assert "Running upgrade  -> 0001_init" in first
    _assert_schema(migrated_db.engine)
    with migrated_db.engine.connect() as connection:
        expected_head = ScriptDirectory.from_config(
            Config(str(ROOT / "alembic.ini"))
        ).get_current_head()
        assert (
            connection.scalar(sa.text("SELECT version_num FROM alembic_version")) == expected_head
        )
        extensions = dict(
            connection.execute(sa.text("SELECT extname, extversion FROM pg_extension")).all()
        )
        assert {"postgis", "timescaledb", "uuid-ossp", "pg_trgm"} <= extensions.keys()
        record_testsuite_property("extensions", str(extensions))
        assert (
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM timescaledb_information.hypertables "
                    "WHERE hypertable_schema = 'public' AND hypertable_name = 'telemetry_observation'"
                )
            )
            == 1
        )
        dimensions = connection.execute(
            sa.text(
                "SELECT column_name, column_type FROM timescaledb_information.dimensions "
                "WHERE hypertable_name = 'telemetry_observation'"
            )
        ).all()
        assert dimensions == [("ts", "timestamp with time zone")]
        record_testsuite_property(
            "continuous_aggregates",
            connection.scalar(
                sa.text("SELECT count(*) FROM timescaledb_information.continuous_aggregates")
            ),
        )
        record_testsuite_property(
            "retention_policies",
            connection.scalar(
                sa.text(
                    "SELECT count(*) FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention'"
                )
            ),
        )
        before = connection.execute(
            sa.text(
                "SELECT indexrelid, pg_get_indexdef(indexrelid), indisvalid, indisready "
                "FROM pg_index WHERE indrelid IN "
                "(SELECT oid FROM pg_class WHERE relnamespace = 'public'::regnamespace) "
                "ORDER BY indexrelid"
            )
        ).all()
        assert all(row.indisvalid and row.indisready for row in before)
        definitions = "\n".join(row.pg_get_indexdef for row in before)
        for fragment in [
            "ix_asset_geom_gist ON public.asset USING gist (geom)",
            "ix_telemetry_observation_ts_brin ON public.telemetry_observation USING brin (ts)",
            "(asset_id, metric, ts DESC) WHERE (scenario_id IS NULL)",
            "(city_id, event_type, start_ts)",
            "(city_id, metric, score DESC)",
            "(run_id, metric, score)",
            "(created_at, idempotency_key)",
            "(city_id, created_at)",
            "(job_id, created_at)",
        ]:
            assert fragment in definitions, fragment

    assert "Running upgrade" not in migrated_db.upgrade()
    with migrated_db.engine.connect() as connection:
        after = connection.execute(
            sa.text(
                "SELECT indexrelid, pg_get_indexdef(indexrelid), indisvalid, indisready "
                "FROM pg_index WHERE indrelid IN "
                "(SELECT oid FROM pg_class WHERE relnamespace = 'public'::regnamespace) "
                "ORDER BY indexrelid"
            )
        ).all()
    assert after == before


def test_metadata_timestamp_defaults_are_functions(migrated_db: MigrationDatabase) -> None:
    """A quoted 'now()' freezes defaults at DDL time when create_all is used."""
    Base.metadata.create_all(migrated_db.engine)
    inspector = sa.inspect(migrated_db.engine)
    for table, column in LEGACY_NULLABLE_TIMESTAMPS:
        reflected = {item["name"]: item for item in inspector.get_columns(table)}
        assert reflected[column]["default"] == "now()", (table, column)
