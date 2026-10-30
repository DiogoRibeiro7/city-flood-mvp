"""Provision migration databases only on an explicitly configured test server."""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]


def get_test_database_url() -> str | None:
    """Never infer a destructive test target from the application's DATABASE_URL."""
    value = os.environ.get("TEST_DATABASE_URL")
    if value is not None:
        validate_test_database_url(value)
    return value


def validate_test_database_url(value: str) -> URL:
    try:
        url = make_url(value)
    except ArgumentError as exc:
        raise ValueError("TEST_DATABASE_URL must be a valid SQLAlchemy URL") from exc
    name = url.database or ""
    if url.get_backend_name() != "postgresql" or not (
        name.startswith("test_") or name.endswith("_test")
    ):
        raise ValueError("TEST_DATABASE_URL must name a PostgreSQL test_... or ..._test database")
    # libpq query options such as dbname/service can override the parsed target.
    if url.query:
        raise ValueError("TEST_DATABASE_URL must not contain connection query overrides")
    return url


@dataclass
class MigrationDatabase:
    url: URL
    engine: Engine

    def bootstrap(self) -> None:
        """Use the same extension prerequisites as a newly provisioned stack."""
        with self.engine.begin() as connection:
            connection.exec_driver_sql((ROOT / "infra/db/init.sql").read_text(encoding="utf-8"))

    def upgrade(self, revision: str = "head") -> str:
        """Exercise the real CLI/env.py in a child process with a bounded timeout."""
        env = os.environ.copy()
        env["DATABASE_URL"] = self.url.render_as_string(hide_password=False)
        env["PGOPTIONS"] = "-c timezone=UTC -c lock_timeout=5s -c statement_timeout=60s"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        output = result.stdout + result.stderr
        if result.returncode:
            raise AssertionError(f"Alembic upgrade {revision} failed:\n{output}")
        return output


@contextmanager
def migration_database(test_url: str) -> Iterator[MigrationDatabase]:
    """Create/drop only a fresh random child DB; never reset the supplied DB."""
    parent = validate_test_database_url(test_url).set(drivername="postgresql+psycopg2")
    name = f"test_migrations_{uuid.uuid4().hex}"
    admin = create_engine(parent, isolation_level="AUTOCOMMIT")
    child = create_engine(
        parent.set(database=name),
        connect_args={"options": "-c timezone=UTC -c lock_timeout=5s -c statement_timeout=60s"},
    )
    created = False
    try:
        with admin.connect() as connection:
            # The name is generated internally, never accepted from the caller.
            connection.execute(text(f'CREATE DATABASE "{name}" TEMPLATE template0'))
            created = True
        yield MigrationDatabase(parent.set(database=name), child)
    finally:
        child.dispose()
        try:
            if created:
                with admin.connect() as connection:
                    connection.execute(text(f'DROP DATABASE "{name}"'))
        finally:
            admin.dispose()
