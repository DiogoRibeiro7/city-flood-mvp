from __future__ import annotations

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.errors import AppError
from floodmvp.common.ids import new_id
from floodmvp.models.db import AnalyticsEvent, Asset, City, Note


async def list_notes(
    session: AsyncSession,
    city_id: str,
    asset_id: str | None = None,
    event_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Note]:
    q = select(Note).where(Note.city_id == city_id)
    if asset_id:
        q = q.where(Note.asset_id == asset_id)
    if event_id:
        q = q.where(Note.event_id == event_id)
    q = q.order_by(desc(Note.created_at)).offset(offset).limit(limit)
    res = await session.execute(q)
    return list(res.scalars().all())


async def get_note(session: AsyncSession, note_id: str) -> Note | None:
    res = await session.execute(select(Note).where(Note.note_id == note_id))
    return res.scalar_one_or_none()


async def create_note(
    session: AsyncSession,
    city_id: str,
    asset_id: str | None,
    event_id: str | None,
    title: str,
    body: str,
    author: str,
) -> Note:
    """Create a note only when its optional references belong to its city.

    A foreign key on ``asset_id`` establishes existence but cannot prevent a
    note from linking assets in a different city. Events have no note FK.
    Validate both associations explicitly before inserting the note.
    """
    if await session.scalar(select(City.city_id).where(City.city_id == city_id)) is None:
        raise AppError(code="CITY_NOT_FOUND", message="City not found", status_code=404)

    if (
        asset_id is not None
        and await session.scalar(
            select(Asset.asset_id).where(Asset.asset_id == asset_id, Asset.city_id == city_id)
        )
        is None
    ):
        raise AppError(code="ASSET_NOT_FOUND", message="Asset not found in city", status_code=404)

    if (
        event_id is not None
        and await session.scalar(
            select(AnalyticsEvent.event_id).where(
                AnalyticsEvent.event_id == event_id, AnalyticsEvent.city_id == city_id
            )
        )
        is None
    ):
        raise AppError(code="EVENT_NOT_FOUND", message="Event not found in city", status_code=404)

    row = Note(
        note_id=new_id("note"),
        city_id=city_id,
        asset_id=asset_id,
        event_id=event_id,
        title=title,
        body=body,
        author=author,
    )
    session.add(row)
    await session.flush()
    return row


async def delete_note(session: AsyncSession, note_id: str) -> bool:
    res = await session.execute(delete(Note).where(Note.note_id == note_id))
    return bool(getattr(res, "rowcount", 0))
