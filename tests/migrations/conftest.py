from __future__ import annotations

from collections.abc import Iterator

import pytest

from scripts.database_test_support import (
    MigrationDatabase,
    get_test_database_url,
    migration_database,
)


@pytest.fixture()
def migrated_db() -> Iterator[MigrationDatabase]:
    url = get_test_database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL required for disposable migration tests")
    with migration_database(url) as database:
        database.bootstrap()
        yield database
