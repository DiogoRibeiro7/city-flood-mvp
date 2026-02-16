"""
tests/test_at_home_check.py

Pytest unit tests for:
- _process_event_flags
- remove_activations_between_doors
- at_home_check

These tests:
- Stub `mysenseds.*` imports so the package is not required.
- Force TESTING=1 so `ds_api` is not imported.
"""

from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

import pandas as pd
import pytest

# TODO: change this to your real module path
MODULE_UNDER_TEST = "your_module_name"


# -----------------------------
# Helpers
# -----------------------------
def utc_ms(dt_str: str) -> int:
    """
    Convert a UTC datetime string like '2026-02-10 02:00' into epoch milliseconds.
    """
    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def build_user_info(*, at_home: bool, in_bed: bool, last_door_ts: int) -> Dict[str, Any]:
    """
    Minimal user_info shape required by at_home_check.
    """
    return {
        "cid": "cid-123",
        "sleep": {"inBed": in_bed},
        "atHome": at_home,
        "outAtNight": False,
        "doorUsed": False,
        "lastDoorTS": last_door_ts,
        "lastDoorOpenNightTS": 0,
        "nightWindow": {"start": "23:00", "end": "06:00"},
        "RSSI": {
            # keys must match df["thingType"]
            "things": {"thingA": -50},
            "avg": 0.0,
        },
        "frailtyEventSent": {"userOutLateSent": -999},  # different from midday_ts(0)
    }


def build_records() -> Tuple[Dict[str, Any], Dict[str, Any]]:
    stat_record = {"timeOut": []}
    yesterday_stats = {"timeOut": []}
    return stat_record, yesterday_stats


# -----------------------------
# Import stubbing (mysenseds.*)
# -----------------------------
@pytest.fixture(scope="module")
def mod():
    """
    Import the module under test with stubbed dependencies.

    This fixture:
    - Inserts stub modules into sys.modules for:
      - mysenseds.math.mysense_stats (ewma)
      - mysenseds.utils.time_utils (get_day, hour, now_ts, midday_ts, get_timestamp_for_hour)
    - Sets TESTING=1 so ds_api is not imported.
    """
    # Force TESTING
    import os

    os.environ["TESTING"] = "1"

    # Create package/module structure stubs
    mysenseds = types.ModuleType("mysenseds")
    mysenseds_math = types.ModuleType("mysenseds.math")
    mysense_stats = types.ModuleType("mysenseds.math.mysense_stats")
    mysenseds_utils = types.ModuleType("mysenseds.utils")
    time_utils = types.ModuleType("mysenseds.utils.time_utils")

    # --- ewma stub ---
    def ewma_stub(x: float, avg: float, _: float) -> Tuple[float, float]:
        # Keep avg stable (good for deterministic tests)
        return float(avg), 0.0

    mysense_stats.ewma = ewma_stub

    # --- time utils stubs ---
    def get_day_stub(ts_ms: int) -> datetime:
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc)

    # We'll override hour/now_ts/midday_ts per-test when needed.
    def hour_stub() -> int:
        return 12

    def now_ts_stub() -> int:
        return utc_ms("2026-02-10 00:00")

    def midday_ts_stub(_: int) -> int:
        # a stable "day marker"
        return 123456789

    def get_timestamp_for_hour_stub(_day_offset: int, hour_value: int) -> int:
        # fixed: 07:00 on 2026-02-10
        assert hour_value == 7
        return utc_ms("2026-02-10 07:00")

    # The code imports hour_of_ts but doesn't use it; still provide it.
    def hour_of_ts_stub(ts_ms: int) -> int:
        return get_day_stub(ts_ms).hour

    time_utils.get_day = get_day_stub
    time_utils.hour = hour_stub
    time_utils.now_ts = now_ts_stub
    time_utils.midday_ts = midday_ts_stub
    time_utils.get_timestamp_for_hour = get_timestamp_for_hour_stub
    time_utils.hour_of_ts = hour_of_ts_stub

    # Register modules in sys.modules
    sys.modules["mysenseds"] = mysenseds
    sys.modules["mysenseds.math"] = mysenseds_math
    sys.modules["mysenseds.math.mysense_stats"] = mysense_stats
    sys.modules["mysenseds.utils"] = mysenseds_utils
    sys.modules["mysenseds.utils.time_utils"] = time_utils

    # Import target module
    imported = importlib.import_module(MODULE_UNDER_TEST)
    # Ensure any prior state is refreshed (helps when iterating locally)
    imported = importlib.reload(imported)

    return imported


# -----------------------------
# Unit tests: _process_event_flags
# -----------------------------
def test_process_event_flags_skips_late_heartrate(mod):
    last_door_ts = utc_ms("2026-02-10 10:00")
    row_ts = last_door_ts + (31 * 60 * 1000)  # 31 minutes later

    door_used, at_home, out_at_night = mod._process_event_flags(
        row_ts=row_ts,
        row_type="HeartRate",
        last_door_ts=last_door_ts,
        door_used=True,
        at_home=False,
        out_at_night=True,
    )

    # Must not change anything because HR is too late
    assert door_used is True
    assert at_home is False
    assert out_at_night is True


def test_process_event_flags_resets_on_motionuse(mod):
    last_door_ts = utc_ms("2026-02-10 10:00")
    row_ts = last_door_ts + 1_000

    door_used, at_home, out_at_night = mod._process_event_flags(
        row_ts=row_ts,
        row_type="MotionUse",
        last_door_ts=last_door_ts,
        door_used=True,
        at_home=False,
        out_at_night=True,
    )

    assert door_used is False
    assert at_home is True
    assert out_at_night is False


# -----------------------------
# Unit tests: remove_activations_between_doors
# -----------------------------
def test_remove_activations_between_doors_drops_between_open_close(mod):
    df = pd.DataFrame(
        [
            # open
            {"ts": 1, "type": "FrontDoorUse", "event": "opened"},
            # should be removed
            {"ts": 2, "type": "MotionUse", "event": "activation"},
            {"ts": 3, "type": "TapUse", "event": "activation"},
            # close
            {"ts": 4, "type": "FrontDoorUse", "event": "closed"},
            # should remain
            {"ts": 5, "type": "MotionUse", "event": "activation"},
        ]
    )

    out = mod.remove_activations_between_doors(
        df,
        sensor_col="event",
        type_col="type",
        door_type="FrontDoorUse",
        door_open_value="opened",
        door_close_value="closed",
    )

    # Expect indices for ts=2 and ts=3 removed
    assert out["ts"].tolist() == [1, 4, 5]
    assert out["type"].tolist() == ["FrontDoorUse", "FrontDoorUse", "MotionUse"]


# -----------------------------
# Unit tests: at_home_check (core behaviours)
# -----------------------------
def test_at_home_check_returns_unchanged_when_no_data(mod):
    user_info = build_user_info(at_home=True, in_bed=False, last_door_ts=utc_ms("2026-02-10 08:00"))
    stat_record, yesterday_stats = build_records()

    sensor_data = pd.DataFrame()
    iot_data = pd.DataFrame()

    out_user, out_stat, out_yday, events = mod.at_home_check(
        sensor_data=sensor_data,
        iot_data=iot_data,
        user_info=user_info,
        stat_record=stat_record,
        yesterday_stats=yesterday_stats,
    )

    assert out_user is user_info
    assert out_stat is stat_record
    assert out_yday is yesterday_stats
    assert events == []


def test_at_home_check_enter_updates_timeOut_to_stat_record(mod, monkeypatch):
    """
    If user was not at home and door opens, function should:
    - append (lastDoorTS, door_open_ts) into stat_record["timeOut"] if lastDoorTS >= get_timestamp_for_hour(0,7)
    - set atHome=True
    """
    # Patch get_timestamp_for_hour to 07:00
    monkeypatch.setattr(mod, "get_timestamp_for_hour", lambda _d, _h: utc_ms("2026-02-10 07:00"))

    last_door_ts = utc_ms("2026-02-10 08:00")  # >= 07:00, should go to stat_record
    user_info = build_user_info(at_home=False, in_bed=False, last_door_ts=last_door_ts)
    stat_record, yesterday_stats = build_records()

    sensor_data = pd.DataFrame(
        [
            {"ts": utc_ms("2026-02-10 09:00"), "type": "FrontDoorUse", "event": "opened"},
        ]
    )
    iot_data = pd.DataFrame()

    out_user, out_stat, out_yday, _events = mod.at_home_check(
        sensor_data=sensor_data,
        iot_data=iot_data,
        user_info=user_info,
        stat_record=stat_record,
        yesterday_stats=yesterday_stats,
    )

    assert out_user["atHome"] is True
    assert out_stat["timeOut"] == [(last_door_ts, utc_ms("2026-02-10 09:00"))]
    assert out_yday["timeOut"] == []


def test_at_home_check_enter_updates_timeOut_to_yesterday_stats(mod, monkeypatch):
    """
    If lastDoorTS < 07:00, timeOut goes to yesterday_stats.
    """
    monkeypatch.setattr(mod, "get_timestamp_for_hour", lambda _d, _h: utc_ms("2026-02-10 07:00"))

    last_door_ts = utc_ms("2026-02-10 06:00")  # < 07:00
    user_info = build_user_info(at_home=False, in_bed=False, last_door_ts=last_door_ts)
    stat_record, yesterday_stats = build_records()

    sensor_data = pd.DataFrame(
        [
            {"ts": utc_ms("2026-02-10 06:30"), "type": "FrontDoorUse", "event": "opened"},
        ]
    )
    iot_data = pd.DataFrame()

    out_user, out_stat, out_yday, _events = mod.at_home_check(
        sensor_data=sensor_data,
        iot_data=iot_data,
        user_info=user_info,
        stat_record=stat_record,
        yesterday_stats=yesterday_stats,
    )

    assert out_user["atHome"] is True
    assert out_stat["timeOut"] == []
    assert out_yday["timeOut"] == [(last_door_ts, utc_ms("2026-02-10 06:30"))]


def test_at_home_check_exit_sets_at_home_false_and_out_at_night_true(mod, monkeypatch):
    """
    Exit detection path:
    - doorUsed must be True (door opened)
    - avg < 2.0
    - atHome True
    - elapsed > 1_800_000 since lastDoorTS
    - not in bed
    Also checks night window classification by lastDoorTS time.
    """
    # Make get_day stable UTC (already stubbed) and keep ewma stable.
    # Force night window start/end (end will be adjusted from 06:00 -> 07:00 internally)
    user_info = build_user_info(
        at_home=True,
        in_bed=False,
        last_door_ts=utc_ms("2026-02-10 01:30"),
    )

    # Ensure avg is already low
    user_info["RSSI"]["avg"] = 0.5

    stat_record, yesterday_stats = build_records()

    # 1) door open at 02:00 (night)
    # 2) RSSI event at 02:31 (> 30 min after door open), triggers exit condition
    sensor_data = pd.DataFrame(
        [
            {"ts": utc_ms("2026-02-10 02:00"), "type": "FrontDoorUse", "event": "opened"},
        ]
    )
    iot_data = pd.DataFrame(
        [
            {"ts": utc_ms("2026-02-10 02:31"), "type": "sensorRSSI", "thingType": "thingA", "rssi": -50},
        ]
    )

    out_user, _out_stat, _out_yday, _events = mod.at_home_check(
        sensor_data=sensor_data,
        iot_data=iot_data,
        user_info=user_info,
        stat_record=stat_record,
        yesterday_stats=yesterday_stats,
    )

    assert out_user["atHome"] is False
    assert out_user["outAtNight"] is True


def test_at_home_check_user_out_late_event_sent_at_midnight(mod, monkeypatch):
    """
    If:
    - hour() == 0
    - not at_home
    - userOutLateSent != midday_ts(0)
    then:
    - adds USER_OUT_LATE to send_events_list
    - updates userOutLateSent to midday_ts(0)
    """
    monkeypatch.setattr(mod, "hour", lambda: 0)
    monkeypatch.setattr(mod, "midday_ts", lambda _d: 999)
    monkeypatch.setattr(mod, "now_ts", lambda: utc_ms("2026-02-10 00:05"))

    user_info = build_user_info(at_home=False, in_bed=False, last_door_ts=utc_ms("2026-02-09 23:00"))
    user_info["frailtyEventSent"]["userOutLateSent"] = -1  # not equal to midday_ts(0)=999

    stat_record, yesterday_stats = build_records()

    sensor_data = pd.DataFrame()  # no new events needed
    iot_data = pd.DataFrame(
        [
            {"ts": utc_ms("2026-02-10 00:01"), "type": "sensorRSSI", "thingType": "thingA", "rssi": -50},
        ]
    )

    out_user, _out_stat, _out_yday, events = mod.at_home_check(
        sensor_data=sensor_data,
        iot_data=iot_data,
        user_info=user_info,
        stat_record=stat_record,
        yesterday_stats=yesterday_stats,
    )

    assert any(e[2] == "USER_OUT_LATE" for e in events)
    assert out_user["frailtyEventSent"]["userOutLateSent"] == 999
