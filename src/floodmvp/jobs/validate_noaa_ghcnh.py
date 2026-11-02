"""Characterize a NOAA rainfall window without importing database settings."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from floodmvp.adapters.noaa_ghcnh import GHCNhError, GHCNhRequest, iter_chunks
from floodmvp.analytics.noaa_quality import QualityPolicy, characterize, render_markdown


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station-id", default="POMU0068545")
    parser.add_argument("--start", required=True, help="Inclusive UTC/offset report timestamp")
    parser.add_argument(
        "--end", required=True, help="Exclusive UTC/offset timestamp; at most 31 days"
    )
    parser.add_argument(
        "--fixture-manifest", type=Path, help="Offline selected rows; no station coverage claims"
    )
    parser.add_argument("--expected-sha256", action="append", default=[], metavar="YEAR=SHA256")
    parser.add_argument(
        "--expected-cadence-minutes",
        type=int,
        default=360,
        help="Assumed schedule, anchored at the Unix epoch in UTC",
    )
    parser.add_argument(
        "--stale-after-minutes",
        type=int,
        default=1440,
        help="Assumed threshold, evaluated at window end",
    )
    parser.add_argument("--json-report", type=Path)
    parser.add_argument("--markdown-report", type=Path)
    args = parser.parse_args(argv)
    if (
        args.json_report
        and args.markdown_report
        and args.json_report.resolve() == args.markdown_report.resolve()
    ):
        parser.error("JSON and Markdown report paths must differ")
    report: dict[str, Any]
    exit_code = 0
    try:
        expected: dict[int, str] = {}
        for item in args.expected_sha256:
            year_text, digest = item.split("=", 1)
            year = int(year_text)
            if year in expected:
                raise GHCNhError("only one expected checksum per year is allowed")
            expected[year] = digest
        request = GHCNhRequest(
            args.station_id,
            args.station_id,
            dt.datetime.fromisoformat(args.start),
            dt.datetime.fromisoformat(args.end),
        )
        report = characterize(
            request,
            iter_chunks(request, fixture_manifest=args.fixture_manifest, expected_hashes=expected),
            policy=QualityPolicy(args.expected_cadence_minutes, args.stale_after_minutes),
        )
    except ValueError as exc:
        exit_code = 2
        report = {
            "schema_version": 1,
            "status": "failed",
            "station_id": args.station_id,
            "start": args.start,
            "end": args.end,
            "error": str(exc) if isinstance(exc, GHCNhError) else "invalid argument or input value",
            "completed_sources": exc.completed_sources if isinstance(exc, GHCNhError) else [],
            "coverage": None,
            "limitation": "Acquisition or validation did not complete. No observed coverage metrics are available; no synthetic substitute was used.",
        }
    serialized = json.dumps(report, indent=2, allow_nan=False) + "\n"
    print(serialized, end="")
    try:
        if args.json_report:
            _write_text(args.json_report, serialized)
        if args.markdown_report:
            _write_text(args.markdown_report, render_markdown(report))
    except OSError:
        print(
            "Could not save all reports; stdout contains the outcome. Compare analysis versions before pairing report files.",
            file=sys.stderr,
        )
        return 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run())
