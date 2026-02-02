from __future__ import annotations

import os

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from floodmvp.models.db import Base


def _get_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")


@pytest.fixture()
async def db_session() -> AsyncSession:
    database_url = _get_database_url()
    if not database_url:
        pytest.skip("DATABASE_URL or TEST_DATABASE_URL not set")

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
