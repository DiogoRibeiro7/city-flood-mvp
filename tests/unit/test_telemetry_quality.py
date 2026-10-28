from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from floodmvp.jobs.qa_telemetry import METRIC_RULES, mark_outliers


@pytest.mark.asyncio
async def test_outlier_query_uses_visible_cte_alias() -> None:
    """The flagged CTE must refer to the named subquery, not its inner alias."""
    session = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.all.return_value = [("city_demo", "rain_mmph", 2)]
    session.execute.return_value = result

    counts = await mark_outliers(session, lookback_days=1)

    assert counts == {("city_demo", "rain_mmph"): 2 * len(METRIC_RULES)}
    statement = str(session.execute.await_args_list[0].args[0])
    assert "SELECT t.asset_id, t.metric, t.ts" in statement
    assert "FROM telemetry_observation obs" in statement
