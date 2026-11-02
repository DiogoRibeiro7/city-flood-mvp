"""Reproduce the descriptive Porto 2010 case study in a fresh disposable database."""

from __future__ import annotations

import argparse
import asyncio
import csv
import datetime as dt
import hashlib
import importlib.metadata
import json
import re
import secrets
import subprocess
import sys
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from geoalchemy2.elements import WKTElement
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from floodmvp.adapters.external_ingest import IngestRecord
from floodmvp.adapters.noaa_ghcnh import (
    FIELD,
    METRIC,
    SOURCE,
    DownloadLimits,
    GHCNhBatch,
    GHCNhError,
    GHCNhRequest,
    SourceChunk,
    iter_chunks,
    iter_source_rows,
    normalize_chunks,
    source_url,
    utc,
)
from floodmvp.analytics.noaa_quality import QualityPolicy, characterize
from floodmvp.analytics.rain_intervals import describe_rain_intervals
from floodmvp.models.db import Asset, City, DatasetImport, TelemetryObservation
from floodmvp.storage.repos.noaa_ghcnh import persist_batch
from scripts.database_test_support import migration_database

ROOT = Path(__file__).resolve().parents[1]
STATION = "POMU0068545"
ASSET = "porto_ghcnh_pedras_rubras"
CITY = "porto_case_study"
START = dt.datetime(2010, 1, 1, tzinfo=dt.UTC)
END = dt.datetime(2010, 1, 12, tzinfo=dt.UTC)
SOURCE_SHA256 = "1febfaa9832085295cb813e987de298c73298318bf6104a51abb1ba65397d1b7"
DB_IMAGE = "timescale/timescaledb-ha@sha256:1cb0764fb549213391fb5a96822b3e143da5bd72c108e5e07f5d721eddf65af9"
SMALL_ARTIFACTS = (
    "case-study.json",
    "quality.json",
    "observations.csv",
    "daily.csv",
    "timeline.csv",
    "rainfall.svg",
    "rainfall.png",
    "report.md",
)


class CaseStudyError(RuntimeError):
    """A sanitized case-study failure suitable for a public artifact."""


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )


def command(*args: str, timeout: int = 120) -> str:
    try:
        result = subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CaseStudyError(
            f"{args[0]} {args[1]} could not complete within its execution limit"
        ) from exc
    if result.returncode:
        # Do not echo subprocess arguments or driver output: they may contain credentials.
        raise CaseStudyError(f"{args[0]} {args[1]} failed (exit {result.returncode})")
    return result.stdout.strip()


def code_provenance() -> dict[str, Any]:
    try:
        versions = {
            name: importlib.metadata.version(name)
            for name in ("city-flood-mvp", "matplotlib", "SQLAlchemy", "httpx")
        }
    except importlib.metadata.PackageNotFoundError as exc:
        raise CaseStudyError(
            "Install the case-study dependency group: poetry install --with case-study"
        ) from exc
    return {
        "revision": command("git", "rev-parse", "HEAD"),
        "dirty": bool(command("git", "status", "--porcelain")),
        "python": sys.version.split()[0],
        "platform": sys.platform,
        "packages": versions,
        "poetry_lock_sha256": hashlib.sha256((ROOT / "poetry.lock").read_bytes()).hexdigest(),
    }


def load_cached_source(path: Path, request: GHCNhRequest) -> list[SourceChunk]:
    """Load a complete pinned annual payload; never promote an excerpt to full coverage."""
    with path.open("rb") as stream:
        manifest_bytes = stream.read(65_537)
    if len(manifest_bytes) > 65_536:
        raise CaseStudyError("source manifest exceeds 64 KiB")
    manifest = json.loads(manifest_bytes)
    if (
        manifest.get("schema_version") != 1
        or manifest.get("scope") != "complete_station_year"
        or manifest.get("license") != "CC0-1.0"
        or manifest.get("station_id") != STATION
        or len(manifest.get("files", [])) != 1
    ):
        raise CaseStudyError("cache must contain the complete CC0 Porto 2010 station-year")
    spec = manifest["files"][0]
    name, provenance = spec["file"], spec["provenance"]
    if not isinstance(name, str) or Path(name).name != name or name in (".", ".."):
        raise CaseStudyError("cached payload must be a sibling filename")
    with (path.parent / name).open("rb") as stream:
        payload = stream.read(DownloadLimits().max_bytes + 1)
    if (
        len(payload) > DownloadLimits().max_bytes
        or len(payload) != provenance["bytes"]
        or hashlib.sha256(payload).hexdigest() != SOURCE_SHA256
        or provenance["sha256"] != SOURCE_SHA256
        or provenance["year"] != 2010
        or provenance["url"] != source_url(request.station_id, 2010)
        or provenance["mode"] != "http"
    ):
        raise CaseStudyError(
            "cached source does not match the approved station-year checksum/metadata"
        )
    utc(dt.datetime.fromisoformat(provenance["retrieved_at"]))
    # Preserve the original HTTP retrieval; the run manifest separately records cache use.
    return [SourceChunk(2010, payload, provenance)]


def archive_sources(output: Path, chunks: list[SourceChunk], scope: str) -> None:
    directory = output / "source"
    directory.mkdir()
    files = []
    for chunk in chunks:
        filename = f"GHCNh_{STATION}_{chunk.year}.psv"
        (directory / filename).write_bytes(chunk.payload)
        files.append({"file": filename, "provenance": chunk.provenance})
    write_json(
        directory / "manifest.json",
        {
            "schema_version": 1,
            "scope": scope,
            "station_id": STATION,
            "license": "CC0-1.0",
            "files": files,
        },
    )


def verify_container_owner(container: str, owner: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{64}", container):
        raise CaseStudyError("refusing cleanup: invalid container ID")
    identity = command(
        "docker",
        "inspect",
        "--format",
        '{{.Id}}|{{index .Config.Labels "city-flood.case-study"}}',
        container,
    )
    if identity != f"{container}|{owner}":
        raise CaseStudyError("refusing cleanup: container identity/ownership label mismatch")


@contextmanager
def disposable_server(output: Path) -> Iterator[tuple[URL, dict[str, Any]]]:
    """Create one labelled container; cleanup is limited to its exact verified ID."""
    owner = uuid.uuid4().hex
    password = secrets.token_hex(24)
    resources: dict[str, Any] = {"owner_label": owner, "image": DB_IMAGE, "cleanup": "pending"}
    container: str | None = None
    try:
        container = command(
            "docker",
            "create",
            "--name",
            f"city-flood-case-{owner}",
            "--label",
            f"city-flood.case-study={owner}",
            "-e",
            f"POSTGRES_PASSWORD={password}",
            "-e",
            "POSTGRES_DB=test_case_study",
            "-p",
            "127.0.0.1::5432",
            DB_IMAGE,
            timeout=300,
        )
        resources["container_id"] = container
        write_json(output / "resources.json", resources)
        verify_container_owner(container, owner)
        command("docker", "start", container)
        ports = json.loads(
            command("docker", "inspect", "--format", "{{json .NetworkSettings.Ports}}", container)
        )
        binding = ports["5432/tcp"][0]
        if binding["HostIp"] != "127.0.0.1":
            raise CaseStudyError("disposable database is not restricted to loopback")
        resources["image_id"] = command("docker", "inspect", "--format", "{{.Image}}", container)
        url = URL.create(
            "postgresql+psycopg2",
            username="postgres",
            password=password,
            host="127.0.0.1",
            port=int(binding["HostPort"]),
            database="test_case_study",
        )
        # The image briefly starts a Unix-socket-only bootstrap server. Probe the
        # actual published TCP endpoint so that server cannot produce a false ready.
        probe = create_engine(url, connect_args={"connect_timeout": 2})
        deadline = time.monotonic() + 90
        try:
            while True:
                try:
                    with probe.connect() as connection:
                        connection.execute(text("SELECT 1"))
                    break
                except OperationalError:
                    if time.monotonic() >= deadline:
                        raise CaseStudyError(
                            "disposable PostgreSQL did not become ready within 90 seconds"
                        ) from None
                    time.sleep(0.5)
        finally:
            probe.dispose()
        yield url, resources
    finally:
        if container is not None:
            try:
                verify_container_owner(container, owner)
                command("docker", "rm", "--force", "--volumes", container)
                resources["cleanup"] = "removed"
            except Exception:
                resources["cleanup"] = "failed_or_refused"
                raise
            finally:
                write_json(output / "resources.json", resources)


async def ingest_and_readback(
    url: URL, batch: GHCNhBatch
) -> tuple[list[IngestRecord], dict[str, Any]]:
    """Use the real repository twice, then derive analytics inputs from committed rows."""
    engine = create_async_engine(
        url.set(drivername="postgresql+asyncpg"), connect_args={"command_timeout": 60}
    )
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    try:
        observation = batch.records[0].lineage["observation"]
        async with sessions.begin() as session:
            session.add(
                City(city_id=CITY, name="Porto historical case-study mapping", country="PT")
            )
            await session.flush()
            session.add(
                Asset(
                    asset_id=ASSET,
                    city_id=CITY,
                    asset_type="rain_gauge",
                    name=observation["station_name"],
                    geom=WKTElement(
                        f"POINT({observation['longitude']} {observation['latitude']})", srid=4326
                    ),
                    props={"source": SOURCE, "station_id": STATION},
                )
            )
        async with sessions.begin() as session:
            first = await persist_batch(session, batch, CITY)
        async with sessions.begin() as session:
            replay = await persist_batch(session, batch, CITY)
        async with sessions() as session:
            rows = (
                await session.scalars(
                    select(TelemetryObservation)
                    .where(
                        TelemetryObservation.asset_id == ASSET,
                        TelemetryObservation.metric == METRIC,
                    )
                    .order_by(TelemetryObservation.ts)
                )
            ).all()
            audits = (await session.scalars(select(DatasetImport))).all()
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
            stored = [
                IngestRecord(
                    asset_id=row.asset_id,
                    metric=row.metric,
                    ts=row.ts,
                    value=row.value,
                    quality_flag=row.quality_flag,
                    source=row.source,
                    source_type=row.source_type,
                    source_id=row.source_id,
                    lineage=row.lineage,
                )
                for row in rows
            ]
        expected = sorted(batch.records, key=lambda record: record.ts)
        if (
            stored != expected
            or first["inserted"] != len(expected)
            or replay["inserted"] != 0
            or replay["existing"] != len(expected)
            or len(audits) != 2
            or {audit.import_id: audit.validation_report for audit in audits}
            != {first["import_id"]: first, replay["import_id"]: replay}
        ):
            raise CaseStudyError("stored observations, replay or import audit verification failed")
        return stored, {
            "first_import": first,
            "replay": replay,
            "stored_observations": len(stored),
            "stored_import_audits": len(audits),
            "provenance_preserved": True,
            "migration_revision": revision,
        }
    finally:
        await engine.dispose()


def timeline_rows(
    analytics: dict[str, Any],
    quality: dict[str, Any],
    chunks: list[SourceChunk],
    request: GHCNhRequest,
) -> list[dict[str, Any]]:
    rows = [
        {
            "start": i["interval_start"],
            "end": i["interval_end"],
            "kind": i["classification"],
            "depth_mm": i["depth_mm"],
            "six_hour_mean_mmph": i["six_hour_mean_mmph"],
            "detail": "Source QC unverified; sub-hourly timing unknown; no confirmed flood incident.",
        }
        for i in analytics["intervals"]
    ]
    for chunk in chunks:
        for _, timestamp, row in iter_source_rows(chunk, request, DownloadLimits()):
            if request.start <= timestamp < request.end and row[f"{FIELD}_Measurement_Code"] == "T":
                rows.append(
                    {
                        "start": timestamp.isoformat(),
                        "end": timestamp.isoformat(),
                        "kind": "source_trace_report",
                        "depth_mm": None,
                        "six_hour_mean_mmph": None,
                        "detail": "Source measurement flag T; amount is unknown, not observed zero.",
                    }
                )
    if quality["coverage"] is not None:
        for gap in quality["coverage"]["interval_support"]["unsupported_intervals"]:
            rows.append(
                {
                    "start": gap["start"],
                    "end": gap["end"],
                    "kind": "unknown_amount_interval",
                    "depth_mm": None,
                    "six_hour_mean_mmph": None,
                    "detail": "No quantitative support from selected reports; includes censored window edges.",
                }
            )
    return sorted(rows, key=lambda row: (row["start"], row["end"], row["kind"]))


def write_csv(path: Path, columns: list[str], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def plot_intervals(
    output: Path, analytics: dict[str, Any], quality: dict[str, Any], timeline: list[dict[str, Any]]
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    def date(value: str) -> float:
        return float(mdates.date2num(dt.datetime.fromisoformat(value)))  # type: ignore[no-untyped-call]

    with plt.rc_context({"svg.hashsalt": "city-flood-porto-2010-v1", "font.family": "DejaVu Sans"}):
        fig, (amount, support) = plt.subplots(
            2, 1, figsize=(11, 5.5), sharex=True, layout="constrained"
        )
        intervals = analytics["intervals"]
        amount.scatter(
            [date(i["report_timestamp"]) for i in intervals],
            [i["depth_mm"] for i in intervals],
            color="#176b87",
            zorder=3,
        )
        amount.set_ylabel("Reported six-hour depth (mm)")
        amount.set_ylim(bottom=0)
        amount.grid(axis="y", alpha=0.25)
        amount.set_title(
            f"Porto / Pedras Rubras, 2010 — {quality['scope']}\nDescriptive observations; no verified flood incidents"
        )
        for interval in intervals:
            left, right = date(interval["interval_start"]), date(interval["interval_end"])
            support.broken_barh([(left, right - left)], (-0.3, 0.6), facecolors="#176b87")
        for row in timeline:
            if row["kind"] == "source_trace_report":
                support.scatter([date(row["start"])], [1], marker="x", color="#b86b00", zorder=4)
            elif row["kind"] == "unknown_amount_interval":
                left, right = date(row["start"]), date(row["end"])
                support.broken_barh([(left, right - left)], (1.7, 0.6), facecolors="#bfc5ca")
        support.set_yticks(
            [0, 1, 2], ["Quantitative support", "Trace report (unknown amount)", "Unknown amount"]
        )
        support.set_ylim(-0.7, 2.7)
        support.set_xlim(mdates.date2num(START), mdates.date2num(END))  # type: ignore[no-untyped-call]
        support.xaxis.set_major_locator(mdates.DayLocator(interval=1, tz=dt.UTC))  # type: ignore[no-untyped-call]
        support.xaxis.set_major_formatter(mdates.DateFormatter("%d %b", tz=dt.UTC))  # type: ignore[no-untyped-call]
        support.set_xlabel(
            "UTC; points are report timestamps, bars are six-hour accumulation support"
        )
        fig.text(
            0.5,
            -0.035,
            "No interpolation. The first report covers time before the window. Trace is not zero; unknown is not dry.",
            ha="center",
            fontsize=9,
        )
        if quality["coverage"] is None:
            support.text(
                0.5,
                0.86,
                "Selected rows only: missing intervals and coverage are not assessed.",
                transform=support.transAxes,
                ha="center",
                fontsize=9,
            )
        fig.savefig(
            output / "rainfall.svg",
            metadata={"Date": None, "Creator": "City Flood descriptive case study"},
            bbox_inches="tight",
        )
        fig.savefig(
            output / "rainfall.png",
            dpi=140,
            metadata={"Software": "City Flood descriptive case study"},
            bbox_inches="tight",
        )
        plt.close(fig)


def write_outputs(
    output: Path,
    analytics: dict[str, Any],
    quality: dict[str, Any],
    ingestion: dict[str, Any],
    timeline: list[dict[str, Any]],
) -> None:
    case = {
        "schema_version": 1,
        "station_id": STATION,
        "start": START.isoformat(),
        "end": END.isoformat(),
        "scope": quality["scope"],
        "interpretation": "Descriptive case study; no confirmed flood incidents or validated predictions.",
        "analytics": analytics,
        "ingestion": ingestion,
    }
    write_json(output / "case-study.json", case)
    write_json(output / "quality.json", quality)
    columns = [
        "station_id",
        "asset_id",
        "report_timestamp",
        "interval_start",
        "interval_end",
        "depth_mm",
        "six_hour_mean_mmph",
        "classification",
        "minutes_inside_window",
        "quality_flag",
        "source_sha256",
        "source_line",
    ]
    write_csv(output / "observations.csv", columns, analytics["intervals"])
    daily = [
        {
            "start": d["start"],
            "end": d["end"],
            "states_json": json.dumps(d["states"], sort_keys=True),
            "supported_minutes": d["supported_minutes"],
            "window_minutes": d["window_minutes"],
        }
        for d in quality["daily"]
    ]
    write_csv(
        output / "daily.csv",
        ["start", "end", "states_json", "supported_minutes", "window_minutes"],
        daily,
    )
    write_csv(
        output / "timeline.csv",
        ["start", "end", "kind", "depth_mm", "six_hour_mean_mmph", "detail"],
        timeline,
    )
    plot_intervals(output, analytics, quality, timeline)
    lines = [
        "# Porto historical rainfall case study",
        "",
        "**Descriptive only: no verified flood incident, prediction accuracy or warning lead time is established.**",
        "",
        f"Station `{STATION}`, report-time window `[{START.isoformat()}, {END.isoformat()})`; scope **{quality['scope']}**.",
        "",
        "![Recorded rainfall and interval support](rainfall.svg)",
        "",
        f"The real repository inserted {ingestion['first_import']['inserted']} observations; a replay inserted {ingestion['replay']['inserted']} and verified {ingestion['replay']['existing']} existing rows. Analytics use the committed database readback. Both import audits and original lineage were verified.",
        "",
        f"Interval analysis classified {analytics['reported_wet_intervals']} positive-depth reports and {analytics['observed_zero_intervals']} observed-zero reports. Maximum reported six-hour depth: {analytics['maximum_reported_depth_mm']} mm. These totals do not locate rainfall within each six-hour interval.",
        "",
        f"Source timestamp states: `{quality['counts']['states_by_unique_timestamp']}`.",
        "",
    ]
    if quality["coverage"] is not None:
        support = quality["coverage"]["interval_support"]
        lines += [
            f"Clipped quantitative support: {support['supported_minutes'] / 60:g} / {support['window_minutes'] / 60:g} hours ({support['supported_fraction']:.2%}). Unknown intervals are not dry. This excludes accumulations reported at/after the right edge; the first report ends at the left edge and supplies no in-window support.",
            "",
        ]
    else:
        lines += [
            "This fixture is noncontiguous. Station coverage, sampling, freshness and missing intervals are not assessed.",
            "",
        ]
    lines += [
        "The operational 15-minute detector was not run on six-hour totals. Interval classification uses the explicit depth > 0 mm rule, not a calibrated flood-alert threshold. No independent labels or reviewed negative periods exist here: precision, recall, false-alarm rate and lead time remain null.",
        "",
        "## Observation and incident-review timeline",
        "",
        "These are rainfall observations and unknown periods for incident review, not confirmed flood incidents. The trace entry has unknown amount. All numeric values retain unverified source QC.",
        "",
        "| Start UTC | End UTC | Evidence | Depth (mm) |",
        "| --- | --- | --- | ---: |",
        *[
            f"| {r['start']} | {r['end']} | {r['kind']} | {r['depth_mm'] if r['depth_mm'] is not None else 'unknown'} |"
            for r in timeline
        ],
        "",
        "See [observations.csv](observations.csv), [daily.csv](daily.csv), [timeline.csv](timeline.csv), [quality.json](quality.json), [case-study.json](case-study.json) and [manifest.json](manifest.json) for exact counts, provenance, configuration and artifact hashes.",
        "",
        "Source: Menne et al., NOAA NCEI GHCNh, [DOI 10.25921/jp3d-3v19](https://doi.org/10.25921/jp3d-3v19), CC0-1.0. No NOAA endorsement.",
        "",
    ]
    (output / "report.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Fresh directory; never overwrite a previous run",
    )
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument(
        "--source-manifest",
        type=Path,
        help="Complete pinned HTTP archive from an earlier run; no new source download",
    )
    inputs.add_argument(
        "--fixture-manifest",
        type=Path,
        help="Pipeline demonstration on selected fixture rows; no station coverage claims",
    )
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError:
        print(
            "Output must be a new writable directory; existing runs are never overwritten.",
            file=sys.stderr,
        )
        return 2
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "status": "running",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "seed": None,
        "randomness": "No stochastic analytics or simulated data; disposable resource/import IDs vary.",
        "configuration": {
            "station_id": STATION,
            "asset_id": ASSET,
            "city_id": CITY,
            "start": START.isoformat(),
            "end": END.isoformat(),
            "metric": METRIC,
            "expected_source_sha256": SOURCE_SHA256,
            "expected_cadence_minutes": 360,
            "stale_after_minutes": 1440,
            "wet_depth_threshold_mm": 0.0,
            "database_image": DB_IMAGE,
        },
    }
    stage = "preflight"
    try:
        manifest["code"] = code_provenance()
        if command("docker", "info", "--format", "{{.OSType}}") != "linux":
            raise CaseStudyError("Docker must be running Linux containers")
        request = GHCNhRequest(STATION, ASSET, START, END)
        stage = "acquisition"
        print("Acquiring or loading the pinned NOAA source...", flush=True)
        if args.source_manifest:
            chunks = load_cached_source(args.source_manifest, request)
            mode = "recorded_http_cache"
        else:
            chunks = list(
                iter_chunks(
                    request,
                    fixture_manifest=args.fixture_manifest,
                    expected_hashes=None if args.fixture_manifest else {2010: SOURCE_SHA256},
                )
            )
            mode = "selected_fixture" if args.fixture_manifest else "live_http"
        manifest["acquisition"] = {"mode": mode, "sources": [c.provenance for c in chunks]}
        input_manifest = args.source_manifest or args.fixture_manifest
        if input_manifest:
            manifest["acquisition"]["input_manifest_sha256"] = hashlib.sha256(
                input_manifest.read_bytes()
            ).hexdigest()
        archive_sources(
            output,
            chunks,
            "selected_rows_only" if args.fixture_manifest else "complete_station_year",
        )
        stage = "quality_and_normalization"
        quality = characterize(request, chunks, policy=QualityPolicy())
        batch = normalize_chunks(request, chunks)
        if not batch.records:
            raise CaseStudyError("case study has no eligible quantitative rainfall observations")
        stage = "disposable_database"
        print("Starting an isolated database and applying migrations...", flush=True)
        with disposable_server(output) as (parent, resources):
            manifest["database"] = resources
            with migration_database(parent.render_as_string(hide_password=False)) as database:
                database.bootstrap()
                database.upgrade()
                stage = "ingestion_and_replay"
                print("Ingesting, replaying and reading committed observations...", flush=True)
                records, ingestion = asyncio.run(ingest_and_readback(database.url, batch))
        stage = "analytics_and_artifacts"
        print("Computing descriptive interval analytics and writing tables/figures...", flush=True)
        analytics = describe_rain_intervals(records, START, END)
        timeline = timeline_rows(analytics, quality, chunks, request)
        write_outputs(output, analytics, quality, ingestion, timeline)
        manifest["artifacts"] = {
            name: {
                "sha256": hashlib.sha256((output / name).read_bytes()).hexdigest(),
                "bytes": (output / name).stat().st_size,
            }
            for name in SMALL_ARTIFACTS
        }
        manifest.update(status="completed", completed_at=dt.datetime.now(dt.UTC).isoformat())
    except (Exception, KeyboardInterrupt) as exc:
        manifest.update(
            status="failed",
            failed_stage=stage,
            error=str(exc)
            if isinstance(exc, (CaseStudyError, GHCNhError))
            else f"{stage} failed ({type(exc).__name__}); no successful case study is claimed",
        )
        print(manifest["error"], file=sys.stderr)
    finally:
        write_json(output / "manifest.json", manifest)
    print(f"{manifest['status']}: {output / 'manifest.json'}", flush=True)
    return 0 if manifest["status"] == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(run())
