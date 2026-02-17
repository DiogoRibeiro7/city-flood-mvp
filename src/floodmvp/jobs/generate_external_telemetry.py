from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any, cast

from floodmvp.generators.external import (
    RainGaugeGenConfig,
    RiverLevelGenConfig,
    generate_rain_gauge,
    generate_river_level,
    write_json,
)


def _parse_dt(value: str) -> dt.datetime:
    ts = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.UTC)
    return ts


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate external telemetry JSON")
    parser.add_argument("--out", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--pattern", choices=["steady", "storm_bursts", "seasonal", "random_walk"], required=True)
    parser.add_argument("--rain-count", type=int, default=1)
    parser.add_argument("--river-count", type=int, default=1)
    parser.add_argument("--rain-prefix", default="rain_gauge_")
    parser.add_argument("--river-prefix", default="river_gauge_")
    parser.add_argument("--rain-base", type=float, default=0.5)
    parser.add_argument("--rain-peak", type=float, default=35.0)
    parser.add_argument("--rain-noise", type=float, default=0.6)
    parser.add_argument("--river-base", type=float, default=1.2)
    parser.add_argument("--river-peak", type=float, default=3.2)
    parser.add_argument("--river-noise", type=float, default=0.03)
    parser.add_argument("--rain-pattern-overrides")
    parser.add_argument("--river-pattern-overrides")
    parser.add_argument("--rain-device-overrides")
    parser.add_argument("--river-device-overrides")
    parser.add_argument("--outage-count", type=int, default=0)
    parser.add_argument("--outage-min-minutes", type=int, default=10)
    parser.add_argument("--outage-max-minutes", type=int, default=120)
    parser.add_argument("--seed", type=int, default=42)

    args = parser.parse_args()

    start = _parse_dt(args.start)
    end = _parse_dt(args.end)

    def _load_overrides(value: str | None) -> dict[str, dict[str, float]]:
        if not value:
            return {}
        if value.startswith("@"):
            path = Path(value[1:])
            return cast(dict[str, dict[str, float]], json.loads(path.read_text(encoding="utf-8")))
        return cast(dict[str, dict[str, float]], json.loads(value))

    rain_overrides = _load_overrides(args.rain_pattern_overrides)
    river_overrides = _load_overrides(args.river_pattern_overrides)
    rain_device_overrides = _load_overrides(args.rain_device_overrides)
    river_device_overrides = _load_overrides(args.river_device_overrides)

    records: list[dict[str, object]] = []
    for i in range(args.rain_count):
        device_id = f"{args.rain_prefix}{i}"
        device_cfg_rain: dict[str, Any] = rain_device_overrides.get(device_id, {})
        rain_cfg = RainGaugeGenConfig(
            device_id=device_id,
            start=start,
            end=end,
            cadence_seconds=60,
            pattern=args.pattern,
            base_mmph=float(device_cfg_rain.get("base", args.rain_base)),
            peak_mmph=float(device_cfg_rain.get("peak", args.rain_peak)),
            noise_sigma=float(device_cfg_rain.get("noise_sigma", args.rain_noise)),
            pattern_overrides=cast(
                dict[str, dict[str, float]],
                device_cfg_rain.get("pattern_overrides", rain_overrides),
            ),
            outage_count=int(device_cfg_rain.get("outage_count", args.outage_count)),
            outage_min_minutes=int(
                device_cfg_rain.get("outage_min_minutes", args.outage_min_minutes)
            ),
            outage_max_minutes=int(
                device_cfg_rain.get("outage_max_minutes", args.outage_max_minutes)
            ),
            seed=int(device_cfg_rain.get("seed", args.seed + i * 7)),
        )
        records.extend(generate_rain_gauge(rain_cfg))

    for i in range(args.river_count):
        device_id = f"{args.river_prefix}{i}"
        device_cfg_river: dict[str, Any] = river_device_overrides.get(device_id, {})
        river_cfg = RiverLevelGenConfig(
            device_id=device_id,
            start=start,
            end=end,
            cadence_seconds=60,
            pattern=args.pattern,
            base_m=float(device_cfg_river.get("base", args.river_base)),
            peak_m=float(device_cfg_river.get("peak", args.river_peak)),
            noise_sigma=float(device_cfg_river.get("noise_sigma", args.river_noise)),
            pattern_overrides=cast(
                dict[str, dict[str, float]],
                device_cfg_river.get("pattern_overrides", river_overrides),
            ),
            outage_count=int(device_cfg_river.get("outage_count", args.outage_count)),
            outage_min_minutes=int(
                device_cfg_river.get("outage_min_minutes", args.outage_min_minutes)
            ),
            outage_max_minutes=int(
                device_cfg_river.get("outage_max_minutes", args.outage_max_minutes)
            ),
            seed=int(device_cfg_river.get("seed", args.seed + 100 + i * 7)),
        )
        records.extend(generate_river_level(river_cfg))

    records.sort(key=lambda r: (str(r.get("ts", "")), str(r.get("device_id", ""))))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_json(str(out_path), records)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
