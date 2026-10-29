from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from floodmvp.models.db import Base


def _get_database_url() -> str | None:
    """Return an explicitly configured, unmistakably test-only PostgreSQL URL.

    The integration fixture recreates application tables. Never infer its target
    from DATABASE_URL, which may point to a running demo or real deployment.
    """
    database_url = os.environ.get("TEST_DATABASE_URL")
    if not database_url:
        return None

    try:
        url = make_url(database_url)
    except sa.exc.ArgumentError as exc:
        raise ValueError("TEST_DATABASE_URL must be a valid SQLAlchemy URL") from exc

    database_name = url.database or ""
    if url.get_backend_name() != "postgresql" or not (
        database_name.startswith("test_") or database_name.endswith("_test")
    ):
        raise ValueError(
            "TEST_DATABASE_URL must target a dedicated PostgreSQL test database "
            "whose name starts with 'test_' or ends with '_test'"
        )
    return database_url


@pytest.fixture()
async def db_session() -> AsyncSession:
    database_url = _get_database_url()
    if not database_url:
        pytest.skip("TEST_DATABASE_URL not set; integration tests require an isolated database")

    engine = create_async_engine(database_url, pool_pre_ping=True)
    async_session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async with engine.begin() as conn:
        await conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis;"))
        await conn.execute(
            sa.text(
                "DO $$ BEGIN "
                "CREATE EXTENSION IF NOT EXISTS timescaledb; "
                "EXCEPTION WHEN undefined_file THEN NULL; "
                "END $$;"
            )
        )
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as session:
        yield session

    await engine.dispose()
