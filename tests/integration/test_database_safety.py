from __future__ import annotations

import pytest
from conftest import _get_database_url


def test_integration_db_requires_explicit_test_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A production or demo DATABASE_URL must never trigger table recreation."""
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@host/floodmvp")

    assert _get_database_url() is None


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://user:pass@localhost/floodmvp",
        "postgresql+asyncpg://user:pass@localhost/production",
        "sqlite+aiosqlite:///test_floodmvp",
        "not a database URL",
    ],
)
def test_integration_db_rejects_unsafe_urls(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    monkeypatch.setenv("TEST_DATABASE_URL", url)

    with pytest.raises(ValueError, match="TEST_DATABASE_URL"):
        _get_database_url()


@pytest.mark.parametrize("name", ["floodmvp_test", "test_floodmvp"])
def test_integration_db_accepts_explicit_test_database(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    url = f"postgresql+asyncpg://user:pass@localhost/{name}"
    monkeypatch.setenv("TEST_DATABASE_URL", url)

    assert _get_database_url() == url
