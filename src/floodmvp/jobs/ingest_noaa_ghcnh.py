"""Preview or import a bounded historical Portuguese GHCNh rainfall window."""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from floodmvp.adapters.noaa_ghcnh import GHCNhBatch, GHCNhError, GHCNhRequest, acquire


async def _persist(batch: GHCNhBatch, city_id: str) -> dict[str, Any]:
    # Dry runs do not import settings, create an engine or access a database.
    from sqlalchemy.exc import SQLAlchemyError

    try:
        from floodmvp.storage.db import SessionLocal
        from floodmvp.storage.repos.noaa_ghcnh import persist_batch

        async with SessionLocal.begin() as session:
            report = await persist_batch(session, batch, city_id)
        return report
    except SQLAlchemyError as exc:
        # Driver messages can contain connection credentials. Do not print them.
        raise GHCNhError("database operation failed; transaction rolled back") from exc


def _write_report(path: Path, report: dict[str, Any]) -> None:
    """Replace only the requested report after a complete JSON write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = stream.name
            json.dump(report, stream, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--station-id", default="POMU0068545")
    parser.add_argument(
        "--asset-id", required=True, help="Explicit destination asset; checked only on --write"
    )
    parser.add_argument("--city-id", required=True)
    parser.add_argument("--start", required=True, help="Inclusive UTC/offset report timestamp")
    parser.add_argument(
        "--end", required=True, help="Exclusive UTC/offset report timestamp; at most 31 days"
    )
    parser.add_argument(
        "--fixture-manifest", type=Path, help="Offline CC0 recorded-fixture manifest"
    )
    parser.add_argument("--expected-sha256", action="append", default=[], metavar="YEAR=SHA256")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_true", help="Default: no database access or writes"
    )
    mode.add_argument("--write", action="store_true", help="Atomically persist using DATABASE_URL")
    parser.add_argument(
        "--report", type=Path, help="Optional JSON report; always also written to stdout"
    )
    args = parser.parse_args(argv)
    exit_code = 0
    report: dict[str, Any]
    batch: GHCNhBatch | None = None
    try:
        if not args.city_id.strip() or len(args.city_id) > 64:
            raise GHCNhError("city_id must contain 1 to 64 characters")
        expected: dict[int, str] = {}
        for item in args.expected_sha256:
            year_text, digest = item.split("=", 1)
            year = int(year_text)
            if year in expected:
                raise GHCNhError("only one expected checksum per year is allowed")
            expected[year] = digest
        request = GHCNhRequest(
            args.station_id,
            args.asset_id,
            dt.datetime.fromisoformat(args.start),
            dt.datetime.fromisoformat(args.end),
        )
        batch = acquire(request, fixture_manifest=args.fixture_manifest, expected_hashes=expected)
        if args.write:
            report = asyncio.run(_persist(batch, args.city_id))
        else:
            report = batch.report()
            report.update(dry_run=True, city_id=args.city_id, asset_validation="not_checked")
    except (GHCNhError, ValueError) as exc:
        exit_code = 2
        report = {
            "status": "failed",
            "dry_run": not args.write,
            "inserted": 0,
            "error": str(exc) if isinstance(exc, GHCNhError) else "invalid argument or input value",
            "completed_sources": (
                batch.sources
                if batch is not None
                else exc.completed_sources
                if isinstance(exc, GHCNhError)
                else []
            ),
        }
    print(json.dumps(report, indent=2, allow_nan=False))
    if args.report:
        try:
            _write_report(args.report, report)
        except OSError:
            print(
                "Could not save report; stdout above records the outcome. A completed import remains committed.",
                file=sys.stderr,
            )
            return 2
    return exit_code


if __name__ == "__main__":
    raise SystemExit(run())
