from __future__ import annotations

from collections.abc import AsyncGenerator

import time

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from floodmvp.config.settings import settings
from floodmvp.observability.metrics import DB_QUERY_COUNT, DB_QUERY_ERRORS, DB_QUERY_LATENCY, classify_operation


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


@event.listens_for(engine.sync_engine, "before_cursor_execute")
def _before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("query_start_time", []).append(time.perf_counter())
    conn.info["last_statement"] = statement


@event.listens_for(engine.sync_engine, "after_cursor_execute")
def _after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    start_times = conn.info.get("query_start_time")
    if not start_times:
        return
    start = start_times.pop(-1)
    duration = time.perf_counter() - start
    operation = classify_operation(statement)
    DB_QUERY_COUNT.labels(operation=operation).inc()
    DB_QUERY_LATENCY.labels(operation=operation).observe(duration)


@event.listens_for(engine.sync_engine, "handle_error")
def _handle_error(exception_context):
    operation = classify_operation(exception_context.statement)
    DB_QUERY_ERRORS.labels(operation=operation).inc()
