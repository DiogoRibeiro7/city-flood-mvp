"""Fast feedback for city-scoped note creation without a database."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.common.errors import AppError
from floodmvp.storage.repos.notes import create_note


def note_session(results: list[str | None]) -> AsyncSession:
    """Return a session double that produces the requested reference lookups."""
    session = MagicMock(spec=AsyncSession)
    session.scalar = AsyncMock(side_effect=results)
    session.flush = AsyncMock()
    return cast(AsyncSession, session)


async def insert_note(
    session: AsyncSession,
    asset_id: str | None = None,
    event_id: str | None = None,
) -> None:
    """Call the repository with consistent note fields across test cases."""
    await create_note(
        session,
        city_id="city_porto",
        asset_id=asset_id,
        event_id=event_id,
        title="Inspection",
        body="Clear drain",
        author="Inspector",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_id", "event_id", "lookup_results", "error_code"),
    [
        (None, None, [None], "CITY_NOT_FOUND"),
        ("asset_missing", None, ["city_porto", None], "ASSET_NOT_FOUND"),
        (None, "event_missing", ["city_porto", None], "EVENT_NOT_FOUND"),
        ("asset_1", "event_missing", ["city_porto", "asset_1", None], "EVENT_NOT_FOUND"),
    ],
)
async def test_invalid_note_reference_is_rejected_before_insertion(
    asset_id: str | None,
    event_id: str | None,
    lookup_results: list[str | None],
    error_code: str,
) -> None:
    session = note_session(lookup_results)

    with pytest.raises(AppError) as exc:
        await insert_note(session, asset_id, event_id)

    assert exc.value.code == error_code
    assert exc.value.status_code == 404
    session.add.assert_not_called()  # type: ignore[attr-defined]
    session.flush.assert_not_awaited()  # type: ignore[attr-defined]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("asset_id", "event_id", "lookup_results"),
    [
        (None, None, ["city_porto"]),
        ("asset_1", None, ["city_porto", "asset_1"]),
        (None, "event_1", ["city_porto", "event_1"]),
        ("asset_1", "event_1", ["city_porto", "asset_1", "event_1"]),
    ],
)
async def test_valid_note_references_are_checked_with_city_predicates(
    asset_id: str | None,
    event_id: str | None,
    lookup_results: list[str | None],
) -> None:
    session = note_session(lookup_results)

    await insert_note(session, asset_id, event_id)

    session.add.assert_called_once()  # type: ignore[attr-defined]
    session.flush.assert_awaited_once()  # type: ignore[attr-defined]
    queries = [
        str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        for call in session.scalar.await_args_list  # type: ignore[attr-defined]
    ]
    assert "city.city_id = 'city_porto'" in queries[0]
    if asset_id is not None:
        asset_query = next(query for query in queries if "FROM asset" in query)
        assert "asset.city_id = 'city_porto'" in asset_query
        assert f"asset.asset_id = '{asset_id}'" in asset_query
    if event_id is not None:
        event_query = next(query for query in queries if "FROM analytics_event" in query)
        assert "analytics_event.city_id = 'city_porto'" in event_query
        assert f"analytics_event.event_id = '{event_id}'" in event_query
