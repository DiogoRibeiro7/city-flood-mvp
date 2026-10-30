from __future__ import annotations

from unittest.mock import Mock

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

from scripts import database_test_support as support


@pytest.mark.parametrize(
    "url",
    [
        "postgresql://user:pass@localhost/floodmvp",
        "postgresql://user:pass@localhost/production",
        "postgresql://user:pass@localhost/",
        "sqlite:///floodmvp_test",
        "not a URL",
        "postgresql://localhost/floodmvp_test?dbname=production",
        "postgresql://localhost/floodmvp_test?service=production",
    ],
)
def test_unsafe_migration_targets_are_rejected_before_connecting(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    connect = Mock(side_effect=AssertionError("must not connect"))
    monkeypatch.setattr(support, "create_engine", connect)
    with pytest.raises(ValueError, match="TEST_DATABASE_URL"), support.migration_database(url):
        pytest.fail("unsafe target accepted")
    connect.assert_not_called()


def test_missing_test_target_never_falls_back_to_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/production")
    assert support.get_test_database_url() is None


def test_revision_chain_has_one_base_and_head() -> None:
    scripts = ScriptDirectory.from_config(Config(str(support.ROOT / "alembic.ini")))
    assert len(scripts.get_bases()) == len(scripts.get_heads()) == 1
    revisions = list(reversed(list(scripts.walk_revisions())))
    assert revisions[0].revision == "0001_init"
    previous = None
    for revision in revisions:
        assert revision.down_revision == previous
        assert revision.dependencies is None
        previous = revision.revision
    assert previous == scripts.get_current_head()
