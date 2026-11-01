"""Bounded GHCNh acquisition and conservative six-hour rainfall normalization."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from floodmvp.adapters.external_ingest import IngestRecord, IngestStats
from floodmvp.adapters.rain_gauge_http import convert_units

SOURCE = "noaa_ghcnh"
METRIC = "rain_6h_mean_mmph"
FIELD = "precipitation_6_hour"
INTERVAL_MINUTES = 360
ADAPTER_VERSION = "1"
FORMAT_VERSION = "1.1.0"
DATASET_DOI = "https://doi.org/10.25921/jp3d-3v19"
BASE_URL = "https://www.ncei.noaa.gov/oa/global-historical-climatology-network/hourly/access"
ATTRIBUTES = ("Measurement_Code", "Quality_Code", "Report_Type", "Source_Code", "Source_Station_ID")
REQUIRED_COLUMNS = (
    "STATION",
    "DATE",
    "Station_name",
    "LATITUDE",
    "LONGITUDE",
    "ELEVATION",
    FIELD,
    *(f"{FIELD}_{attribute}" for attribute in ATTRIBUTES),
)


class GHCNhError(ValueError):
    """A source failure; no partially acquired batch may be persisted."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.completed_sources: list[dict[str, Any]] = []


def utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise GHCNhError("window timestamps must include a UTC offset")
    return value.astimezone(dt.UTC)


@dataclass(frozen=True)
class GHCNhRequest:
    station_id: str
    asset_id: str
    start: dt.datetime
    end: dt.datetime

    def __post_init__(self) -> None:
        if not re.fullmatch(r"PO[A-Z0-9-]{9}", self.station_id):
            raise GHCNhError("station_id must be an 11-character Portuguese GHCNh identifier")
        if not self.asset_id.strip() or len(self.asset_id) > 64:
            raise GHCNhError("asset_id must contain 1 to 64 characters")
        object.__setattr__(self, "start", utc(self.start))
        object.__setattr__(self, "end", utc(self.end))
        if not dt.timedelta(0) < self.end - self.start <= dt.timedelta(days=31):
            raise GHCNhError("request window must be positive and at most 31 days")

    @property
    def years(self) -> range:
        last = (self.end - dt.timedelta(microseconds=1)).year
        return range(self.start.year, last + 1)


@dataclass(frozen=True)
class DownloadLimits:
    timeout_seconds: float = 30.0
    budget_seconds: float = 90.0
    attempts: int = 3
    max_bytes: int = 20_000_000
    max_rows: int = 100_000

    def __post_init__(self) -> None:
        for number in (self.timeout_seconds, self.budget_seconds):
            if not math.isfinite(number) or number <= 0:
                raise GHCNhError("download time limits must be finite and positive")
        if not 1 <= self.attempts <= 5 or self.max_bytes < 1 or self.max_rows < 1:
            raise GHCNhError("invalid download attempts, byte limit or row limit")


@dataclass(frozen=True)
class SourceChunk:
    year: int
    payload: bytes
    provenance: dict[str, Any]


@dataclass
class GHCNhBatch:
    request: GHCNhRequest
    records: list[IngestRecord] = field(default_factory=list)
    stats: IngestStats = field(default_factory=IngestStats)
    sources: list[dict[str, Any]] = field(default_factory=list)
    source_rows: int = 0
    outside_window: int = 0
    duplicates: int = 0

    @property
    def dataset_version(self) -> str:
        return fingerprint(
            {
                "adapter_version": ADAPTER_VERSION,
                "station": self.request.station_id,
                "start": self.request.start.isoformat(),
                "end": self.request.end.isoformat(),
                "metric": METRIC,
                "chunks": [(s["year"], s["sha256"]) for s in self.sources],
            }
        )

    def report(self) -> dict[str, Any]:
        return {
            "status": "validated",
            "dataset_version": self.dataset_version,
            "adapter_version": ADAPTER_VERSION,
            "format_version": FORMAT_VERSION,
            "station_id": self.request.station_id,
            "asset_id": self.request.asset_id,
            "start": self.request.start.isoformat(),
            "end": self.request.end.isoformat(),
            "metric": METRIC,
            "interval_minutes": INTERVAL_MINUTES,
            "source_rows": self.source_rows,
            "outside_window": self.outside_window,
            "received": self.stats.received,
            "accepted": self.stats.accepted,
            "rejected": self.stats.rejected,
            "reasons": dict(sorted(self.stats.reasons.items())),
            "duplicates": self.duplicates,
            "inserted": 0,
            "sources": self.sources,
            "license": "CC0-1.0",
            "dataset_doi": DATASET_DOI,
            "interpretation": "Six-hour mean rates with unverified source QC; not instantaneous rainfall or flood labels.",
        }


def fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def source_url(station_id: str, year: int) -> str:
    return f"{BASE_URL}/by-year/{year}/psv/GHCNh_{station_id}_{year}.psv"


def _retry_delay(header: str | None, attempt: int) -> float:
    if header is None:
        return min(0.5 * math.pow(2, attempt - 1), 8.0)
    try:
        delay = float(header)
    except ValueError:
        try:
            delay = (utc(parsedate_to_datetime(header)) - dt.datetime.now(dt.UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError) as exc:
            raise GHCNhError("invalid upstream Retry-After header") from exc
    if not math.isfinite(delay) or delay > 30:
        raise GHCNhError("upstream Retry-After exceeds the bounded retry policy")
    return max(0.0, delay)


def download_chunk(
    client: httpx.Client,
    request: GHCNhRequest,
    year: int,
    limits: DownloadLimits,
    *,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> SourceChunk:
    """Discard interrupted bodies; retry only transient failures within a budget."""
    url = source_url(request.station_id, year)
    deadline = clock() + limits.budget_seconds
    for attempt in range(1, limits.attempts + 1):
        remaining = deadline - clock()
        if remaining <= 0:
            raise GHCNhError(f"download budget exhausted for {year}")
        retry_after = None
        failure = "transport failure"
        try:
            with client.stream(
                "GET",
                url,
                follow_redirects=False,
                headers={"Accept-Encoding": "identity", "User-Agent": "city-flood-mvp/ghcnh-1"},
                timeout=httpx.Timeout(min(limits.timeout_seconds, remaining)),
            ) as response:
                if response.status_code in {408, 429, 500, 502, 503, 504}:
                    retry_after = response.headers.get("Retry-After")
                    failure = f"HTTP {response.status_code}"
                elif response.status_code != 200:
                    raise GHCNhError(
                        f"HTTP {response.status_code} for station-year {year}; not retried"
                    )
                else:
                    body = bytearray()
                    for part in response.iter_bytes(chunk_size=65_536):
                        if len(body) + len(part) > limits.max_bytes:
                            raise GHCNhError(f"response exceeds byte limit for {year}")
                        if clock() >= deadline:
                            raise GHCNhError(f"download budget exhausted for {year}")
                        body.extend(part)
                    if clock() >= deadline:
                        raise GHCNhError(f"download budget exhausted for {year}")
                    payload = bytes(body)
                    return SourceChunk(
                        year,
                        payload,
                        {
                            "year": year,
                            "url": url,
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "bytes": len(payload),
                            "retrieved_at": dt.datetime.now(dt.UTC).isoformat(),
                            "mode": "http",
                            "attempts": attempt,
                            "etag": response.headers.get("ETag"),
                            "last_modified": response.headers.get("Last-Modified"),
                        },
                    )
        except httpx.DecodingError as exc:
            raise GHCNhError(f"invalid HTTP content encoding for {year}") from exc
        except httpx.TransportError as exc:
            failure = type(exc).__name__
        if attempt == limits.attempts:
            raise GHCNhError(f"{failure} for {year}; exhausted {attempt} attempts")
        delay = _retry_delay(retry_after, attempt)
        if delay >= deadline - clock():
            raise GHCNhError(f"retry budget exhausted for {year} after {failure}")
        sleep(delay)
    raise AssertionError("unreachable")


def load_fixture(path: Path, request: GHCNhRequest, limits: DownloadLimits) -> SourceChunk:
    """Read a checksummed, explicitly licensed manifest without network access."""
    try:
        with path.open("rb") as stream:
            manifest_bytes = stream.read(65_537)
        if len(manifest_bytes) > 65_536:
            raise GHCNhError("fixture manifest exceeds 64 KiB")
        manifest = json.loads(manifest_bytes)
        if manifest["schema_version"] != 1 or manifest["license"]["id"] != "CC0-1.0":
            raise GHCNhError("fixture requires the recorded CC0 manifest schema")
        if manifest["station"]["id"] != request.station_id:
            raise GHCNhError("fixture station does not match request")
        spec = manifest["fixture"]
        filename = spec["file"]
        if not isinstance(filename, str) or Path(filename).name != filename:
            raise GHCNhError("fixture file must be a sibling filename")
        with (path.parent / filename).open("rb") as stream:
            payload = stream.read(limits.max_bytes + 1)
        if len(payload) > limits.max_bytes:
            raise GHCNhError("fixture exceeds byte limit")
        digest = hashlib.sha256(payload).hexdigest()
        if digest != spec["sha256"] or len(payload) != spec["bytes"]:
            raise GHCNhError("fixture checksum or size mismatch")
        years = list(request.years)
        if len(years) != 1 or manifest["source"]["url"] != source_url(request.station_id, years[0]):
            raise GHCNhError("fixture must match the requested station-year")
        retrieved = utc(dt.datetime.fromisoformat(manifest["source"]["retrieved_at"]))
        return SourceChunk(
            years[0],
            payload,
            {
                "year": years[0],
                "url": manifest["source"]["url"],
                "sha256": digest,
                "bytes": len(payload),
                "retrieved_at": retrieved.isoformat(),
                "mode": "recorded_fixture",
                "original_sha256": manifest["source"]["sha256"],
                "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
            },
        )
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        if isinstance(exc, GHCNhError):
            raise
        raise GHCNhError("invalid or unreadable fixture manifest/payload") from exc


def _parse_chunk(
    chunk: SourceChunk,
    batch: GHCNhBatch,
    limits: DownloadLimits,
    seen: dict[dt.datetime, tuple[str, ...]],
) -> None:
    try:
        reader = csv.reader(
            io.StringIO(chunk.payload.decode("utf-8-sig")), delimiter="|", strict=True
        )
        header = next(reader, [])
        if len(set(header)) != len(header) or not set(REQUIRED_COLUMNS).issubset(header):
            raise GHCNhError("missing or duplicate GHCNh header columns")
        for number, fields in enumerate(reader, start=2):
            if number - 1 > limits.max_rows:
                raise GHCNhError("station-year exceeds row limit")
            if len(fields) != len(header):
                raise GHCNhError(f"malformed PSV row {number}: wrong column count")
            row = dict(zip(header, fields, strict=True))
            batch.source_rows += 1
            if row["STATION"] != batch.request.station_id:
                raise GHCNhError(f"station mismatch at row {number}")
            if "T" not in row["DATE"]:
                raise GHCNhError(f"DATE must include a time at row {number}")
            timestamp = dt.datetime.fromisoformat(row["DATE"])
            # The provider explicitly defines offset-free DATE values as UTC.
            timestamp = (
                timestamp.replace(tzinfo=dt.UTC) if timestamp.tzinfo is None else utc(timestamp)
            )
            if timestamp.year != chunk.year:
                raise GHCNhError(f"station-year timestamp mismatch at row {number}")
            if not batch.request.start <= timestamp < batch.request.end:
                batch.outside_window += 1
                continue
            batch.stats.received += 1
            signature = tuple(row[key] for key in REQUIRED_COLUMNS if key != "DATE")
            if timestamp in seen:
                if signature != seen[timestamp]:
                    raise GHCNhError(f"conflicting duplicate at {timestamp.isoformat()}")
                batch.duplicates += 1
                continue
            seen[timestamp] = signature
            _normalize_row(row, timestamp, number, chunk, batch)
    except (UnicodeError, csv.Error, ValueError, OverflowError) as exc:
        if isinstance(exc, GHCNhError):
            raise
        raise GHCNhError("malformed GHCNh encoding, timestamp or PSV structure") from exc


def _normalize_row(
    row: dict[str, str],
    timestamp: dt.datetime,
    number: int,
    chunk: SourceChunk,
    batch: GHCNhBatch,
) -> None:
    raw = row[FIELD]
    if not raw.strip():
        batch.stats.add_rejection("missing_rainfall")
        return
    try:
        depth = float(raw)
        value = convert_units(depth, "mm", INTERVAL_MINUTES)
        lat, lon, elevation = (float(row[key]) for key in ("LATITUDE", "LONGITUDE", "ELEVATION"))
        if not all(math.isfinite(n) for n in (lat, lon, elevation)) or not (
            -90 <= lat <= 90 and -180 <= lon <= 180
        ):
            raise ValueError("invalid coordinates")
    except ValueError:
        batch.stats.add_rejection("invalid_numeric_value")
        return
    attributes = {key: row[f"{FIELD}_{key}"] for key in ATTRIBUTES}
    if attributes["Measurement_Code"] == "T":
        batch.stats.add_rejection("trace_rainfall")
        return
    if attributes["Measurement_Code"]:
        batch.stats.add_rejection("unsupported_measurement_code")
        return
    if attributes["Quality_Code"]:
        batch.stats.add_rejection("source_quality_flag")
        return
    if not row["Station_name"] or not all(
        attributes[key] for key in ("Report_Type", "Source_Code", "Source_Station_ID")
    ):
        batch.stats.add_rejection("missing_source_metadata")
        return
    observation = {
        "station_id": batch.request.station_id,
        "station_name": row["Station_name"],
        "latitude": lat,
        "longitude": lon,
        "elevation_m": elevation,
        "field": FIELD,
        "raw_depth": raw,
        "depth_mm": depth,
        "interval_minutes": INTERVAL_MINUTES,
        "interval_start": (timestamp - dt.timedelta(minutes=INTERVAL_MINUTES)).isoformat(),
        "interval_end": timestamp.isoformat(),
        "attributes": attributes,
    }
    lineage = {
        "adapter_version": ADAPTER_VERSION,
        "format_version": FORMAT_VERSION,
        "license": "CC0-1.0",
        "dataset_doi": DATASET_DOI,
        "chunk": chunk.provenance,
        "source_line": number,
        "observation": observation,
        "observation_fingerprint": fingerprint(observation),
        "conversion": "depth_mm / 6; six-hour mean, not instantaneous rainfall",
    }
    batch.records.append(
        IngestRecord(
            asset_id=batch.request.asset_id,
            metric=METRIC,
            ts=timestamp,
            value=value,
            quality_flag="unverified",
            source=SOURCE,
            source_type=str(chunk.provenance["mode"]),
            source_id=batch.request.station_id,
            lineage=lineage,
        )
    )
    batch.stats.accepted += 1


def acquire(
    request: GHCNhRequest,
    *,
    client: httpx.Client | None = None,
    fixture_manifest: Path | None = None,
    expected_hashes: dict[int, str] | None = None,
    limits: DownloadLimits = DownloadLimits(),
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> GHCNhBatch:
    """Fully acquire/validate every year before exposing a batch to persistence."""
    expected_hashes = expected_hashes or {}
    if set(expected_hashes) - set(request.years) or any(
        not re.fullmatch(r"[0-9a-f]{64}", h) for h in expected_hashes.values()
    ):
        raise GHCNhError("expected hashes must name requested years and lowercase SHA-256 values")
    if client is None and fixture_manifest is None:
        with httpx.Client() as owned_client:
            return acquire(
                request,
                client=owned_client,
                expected_hashes=expected_hashes,
                limits=limits,
                sleep=sleep,
                clock=clock,
            )
    batch = GHCNhBatch(request)
    seen: dict[dt.datetime, tuple[str, ...]] = {}
    try:
        for year in request.years:
            if fixture_manifest is not None:
                chunk = load_fixture(fixture_manifest, request, limits)
            else:
                assert client is not None
                chunk = download_chunk(client, request, year, limits, sleep=sleep, clock=clock)
            if year in expected_hashes and chunk.provenance["sha256"] != expected_hashes[year]:
                raise GHCNhError(f"upstream checksum changed for {year}")
            _parse_chunk(chunk, batch, limits, seen)
            batch.sources.append(chunk.provenance)
    except GHCNhError as exc:
        exc.completed_sources = list(batch.sources)
        raise
    return batch
