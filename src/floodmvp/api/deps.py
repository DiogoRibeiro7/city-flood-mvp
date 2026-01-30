from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.storage.db import get_session


SessionDep = Depends(get_session)


async def session_dep(session: AsyncSession = SessionDep) -> AsyncSession:
    return session
