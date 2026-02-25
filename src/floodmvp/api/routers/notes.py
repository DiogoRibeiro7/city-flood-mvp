from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.errors import AppError
from floodmvp.models.domain import NoteIn, NoteOut
from floodmvp.storage.db import get_session
from floodmvp.storage.repos.notes import create_note, delete_note, get_note, list_notes

router = APIRouter(tags=["notes"])


@router.get("/notes", response_model=list[NoteOut])
async def notes(
    city_id: str = Query(...),
    asset_id: str | None = Query(default=None),
    event_id: str | None = Query(default=None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[NoteOut]:
    rows = await list_notes(
        session,
        city_id=city_id,
        asset_id=asset_id,
        event_id=event_id,
        limit=limit,
        offset=offset,
    )
    return [
        NoteOut(
            note_id=r.note_id,
            city_id=r.city_id,
            asset_id=r.asset_id,
            event_id=r.event_id,
            title=r.title,
            body=r.body,
            author=r.author,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get("/notes/{note_id}", response_model=NoteOut)
async def note(
    note_id: str,
    session: AsyncSession = Depends(get_session),
) -> NoteOut:
    row = await get_note(session, note_id)
    if row is None:
        raise AppError(code="NOTE_NOT_FOUND", message="Note not found", status_code=404)
    return NoteOut(
        note_id=row.note_id,
        city_id=row.city_id,
        asset_id=row.asset_id,
        event_id=row.event_id,
        title=row.title,
        body=row.body,
        author=row.author,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.post("/notes", response_model=NoteOut)
async def create(
    payload: NoteIn,
    session: AsyncSession = Depends(get_session),
) -> NoteOut:
    row = await create_note(
        session,
        city_id=payload.city_id,
        asset_id=payload.asset_id,
        event_id=payload.event_id,
        title=payload.title,
        body=payload.body,
        author=payload.author,
    )
    await session.commit()
    return NoteOut(
        note_id=row.note_id,
        city_id=row.city_id,
        asset_id=row.asset_id,
        event_id=row.event_id,
        title=row.title,
        body=row.body,
        author=row.author,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.delete("/notes/{note_id}")
async def remove(
    note_id: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    deleted = await delete_note(session, note_id)
    if not deleted:
        raise AppError(code="NOTE_NOT_FOUND", message="Note not found", status_code=404)
    await session.commit()
    return {"status": "deleted", "note_id": note_id}