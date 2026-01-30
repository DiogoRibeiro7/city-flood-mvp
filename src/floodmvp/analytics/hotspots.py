from __future__ import annotations

import datetime as dt
from dataclasses import dataclass


@dataclass(frozen=True)
class HotspotScore:
    asset_id: str
    score: float
    details: dict[str, object]


def overflow_minutes_score(events: list[tuple[dt.datetime, dt.datetime, float]]) -> float:
    mins = 0.0
    for s, e, _ in events:
        mins += max(0.0, (e - s).total_seconds() / 60.0)
    return mins
