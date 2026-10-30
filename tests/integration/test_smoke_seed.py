from __future__ import annotations

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.models.db import City, TelemetryObservation
from scripts.seed_smoke import seed
from scripts.smoke_fixture import CITY_ID, RAIN_ID, START


async def test_smoke_seed_replay_preserves_counts_values_and_provenance(
    db_session: AsyncSession,
) -> None:
    first = await seed(db_session)
    assert await seed(db_session) == first
    rows = (await db_session.execute(select(TelemetryObservation))).scalars().all()
    assert len(rows) == 36
    assert {row.source for row in rows} == {"synthetic"}
    assert {row.lineage["sha256"] for row in rows} == {first["sha256"]}
    assert {row.ts.tzinfo is not None for row in rows} == {True}


async def test_smoke_seed_rejects_changed_measurements_without_resetting(
    db_session: AsyncSession,
) -> None:
    await seed(db_session)
    await db_session.execute(
        update(TelemetryObservation)
        .where(TelemetryObservation.asset_id == RAIN_ID, TelemetryObservation.ts == START)
        .values(value=99.0)
    )
    await db_session.commit()
    with pytest.raises(ValueError, match="differ from the deterministic fixture"):
        await seed(db_session)
    await db_session.rollback()
    value = await db_session.scalar(
        select(TelemetryObservation.value).where(
            TelemetryObservation.asset_id == RAIN_ID, TelemetryObservation.ts == START
        )
    )
    assert value == 99.0


async def test_smoke_seed_never_deletes_unexpected_data(db_session: AsyncSession) -> None:
    await seed(db_session)
    db_session.add(City(city_id="unexpected", name="Preserve me", country="PT"))
    await db_session.commit()
    with pytest.raises(ValueError, match="refusing to reset"):
        await seed(db_session)
    await db_session.rollback()
    assert set((await db_session.execute(select(City.city_id))).scalars()) == {
        CITY_ID,
        "unexpected",
    }
