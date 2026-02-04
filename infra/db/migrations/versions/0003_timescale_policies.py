"""timescale retention and caggs

Revision ID: 0003_timescale_policies
Revises: 0002_ingest_idempotency
Create Date: 2026-01-30
"""

from __future__ import annotations

from alembic import op

revision = "0003_timescale_policies"
down_revision = "0002_ingest_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Retain raw telemetry for 30 days
    op.execute(
        """
        DO $$
        BEGIN
            PERFORM add_retention_policy(
                'telemetry_observation',
                INTERVAL '30 days',
                if_not_exists => TRUE
            );
        EXCEPTION
            WHEN undefined_function THEN
                -- Timescale extension not installed
                NULL;
            WHEN feature_not_supported THEN
                -- Timescale license does not allow retention policies
                NULL;
        END $$;
        """
    )

    # Continuous aggregate for 5-minute buckets
    with op.get_context().autocommit_block():
        op.execute(
            """
            DO $$
            BEGIN
                EXECUTE $sql$
                CREATE MATERIALIZED VIEW IF NOT EXISTS telemetry_observation_5m
                WITH (timescaledb.continuous) AS
                SELECT
                    asset_id,
                    metric,
                    time_bucket('5 minutes', ts) AS bucket,
                    avg(value) AS avg_value,
                    min(value) AS min_value,
                    max(value) AS max_value,
                    count(*) AS samples
                FROM telemetry_observation
                GROUP BY asset_id, metric, bucket;
                $sql$;
            EXCEPTION
                WHEN undefined_function THEN
                    -- Timescale extension not installed
                    NULL;
                WHEN feature_not_supported THEN
                    -- Timescale license does not allow continuous aggregates
                    NULL;
                WHEN active_sql_transaction THEN
                    -- Some timescaledb operations require autocommit
                    NULL;
            END $$;
            """
        )

    op.execute(
        """
        DO $$
        BEGIN
            PERFORM add_continuous_aggregate_policy(
                'telemetry_observation_5m',
                start_offset => INTERVAL '30 days',
                end_offset => INTERVAL '5 minutes',
                schedule_interval => INTERVAL '5 minutes',
                if_not_exists => TRUE
            );
        EXCEPTION
            WHEN undefined_function THEN
                -- Timescale extension not installed
                NULL;
            WHEN feature_not_supported THEN
                -- Timescale license does not allow CAGG policies
                NULL;
            WHEN undefined_table THEN
                -- CAGG view does not exist
                NULL;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            PERFORM remove_continuous_aggregate_policy('telemetry_observation_5m');
        EXCEPTION
            WHEN undefined_function THEN
                NULL;
            WHEN feature_not_supported THEN
                NULL;
        END $$;
        """
    )
    op.execute("DROP MATERIALIZED VIEW IF EXISTS telemetry_observation_5m;")
    op.execute(
        """
        DO $$
        BEGIN
            PERFORM remove_retention_policy('telemetry_observation');
        EXCEPTION
            WHEN undefined_function THEN
                NULL;
            WHEN feature_not_supported THEN
                NULL;
        END $$;
        """
    )
