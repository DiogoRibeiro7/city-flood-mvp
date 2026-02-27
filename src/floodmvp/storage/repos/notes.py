from __future__ import annotations

from sqlalchemy import delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.ids import new_id
from floodmvp.models.db import Note


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