"""Recorded data for normal paths; altered copies are controlled error examples."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from floodmvp.adapters.noaa_ghcnh import (
    FIELD,
    METRIC,
    DownloadLimits,
    GHCNhError,
    GHCNhRequest,
    acquire,
)
from floodmvp.jobs import ingest_noaa_ghcnh as cli

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/real_sources/noaa_ghcnh"
MANIFEST = FIXTURE / "provenance.json"
PAYLOAD = (FIXTURE / "porto_2010_excerpt.psv").read_bytes()


def request(start: str = "2010-01-01T00:00:00Z", end: str = "2010-01-12T00:00:00Z") -> GHCNhRequest:
    return GHCNhRequest(
        "POMU0068545",
        "porto_gauge",
        dt.datetime.fromisoformat(start),
        dt.datetime.fromisoformat(end),
    )


def altered(*changes: dict[str, str]) -> bytes:
    reader = csv.DictReader(io.StringIO(PAYLOAD.decode()), delimiter="|")
    row = next(reader)
    stream = io.StringIO()
    writer = csv.DictWriter(
        stream, fieldnames=reader.fieldnames or [], delimiter="|", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(dict(row, **change) for change in changes)
    return stream.getvalue().encode()


def from_http(payload: bytes, **kwargs):
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    ) as client:
        return acquire(request(), client=client, **kwargs)


def test_recorded_fixture_units_flags_and_provenance() -> None:
    batch = acquire(request(), fixture_manifest=MANIFEST)
    assert [r.value for r in batch.records] == pytest.approx([7.9 / 6, 2 / 6])
    assert {r.metric for r in batch.records} == {METRIC}
    assert {r.quality_flag for r in batch.records} == {"unverified"}
    assert batch.stats.received == 6 and batch.stats.accepted == 2
    assert batch.stats.reasons == {"missing_rainfall": 3, "trace_rainfall": 1}
    observation = batch.records[0].lineage["observation"]
    assert observation["depth_mm"] == 7.9
    assert observation["interval_start"] == "2009-12-31T18:00:00+00:00"
    assert observation["interval_end"] == "2010-01-01T00:00:00+00:00"
    assert observation["attributes"]["Quality_Code"] == ""
    assert observation["attributes"]["Source_Station_ID"] == "ICAO-LPPR"
    assert observation["latitude"] == 41.23 and observation["longitude"] == -8.68
    manifest = json.loads(MANIFEST.read_text())
    assert batch.sources[0]["sha256"] == manifest["fixture"]["sha256"]
    assert batch.sources[0]["original_sha256"] == manifest["source"]["sha256"]
    assert batch.sources[0]["mode"] == "recorded_fixture"
    assert batch.records[0].ts.tzinfo is dt.UTC
    assert batch.dataset_version == acquire(request(), fixture_manifest=MANIFEST).dataset_version


def test_half_open_window_and_offset_normalization() -> None:
    batch = acquire(
        request("2010-01-01T07:00:00+01:00", "2010-01-02T01:00:00+01:00"), fixture_manifest=MANIFEST
    )
    assert batch.stats.received == 3 and batch.outside_window == 3
    assert len(batch.records) == 1 and batch.records[0].ts.hour == 12
    assert batch.request.start == dt.datetime(2010, 1, 1, 6, tzinfo=dt.UTC)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        ("2010-01-01", "2010-01-02T00:00:00Z"),
        ("2010-01-01T00:00:00Z", "2010-01-01T00:00:00Z"),
        ("2010-01-02T00:00:00Z", "2010-01-01T00:00:00Z"),
        ("2010-01-01T00:00:00Z", "2010-02-02T00:00:00Z"),
    ],
)
def test_invalid_window(start: str, end: str) -> None:
    with pytest.raises(GHCNhError):
        request(start, end)


def test_station_path_injection_and_wrong_country_are_rejected() -> None:
    for station in ("../../2010/", "USW00003812", "PO"):
        with pytest.raises(GHCNhError, match="identifier"):
            GHCNhRequest(station, "asset", request().start, request().end)


@pytest.mark.parametrize(
    "change,reason",
    [
        ({FIELD: "nan"}, "invalid_numeric_value"),
        ({FIELD: "inf"}, "invalid_numeric_value"),
        ({FIELD: "-0.1"}, "invalid_numeric_value"),
        ({FIELD: "broken"}, "invalid_numeric_value"),
        ({"LATITUDE": "100"}, "invalid_numeric_value"),
        ({"LONGITUDE": "nan"}, "invalid_numeric_value"),
        ({FIELD + "_Measurement_Code": "X"}, "unsupported_measurement_code"),
        ({FIELD + "_Quality_Code": "3"}, "source_quality_flag"),
        ({FIELD + "_Source_Code": ""}, "missing_source_metadata"),
    ],
)
def test_invalid_or_flagged_values_are_reported_without_losing_good_rows(change, reason) -> None:
    batch = from_http(altered(change, {"DATE": "2010-01-01T12:00:00"}))
    assert batch.stats.accepted == 1 and batch.stats.reasons == {reason: 1}
    assert batch.records[0].ts.hour == 12


def test_observed_zero_is_distinct_from_trace_and_missing() -> None:
    batch = from_http(altered({FIELD: "0.0"}))
    assert batch.records[0].value == 0.0 and batch.stats.rejected == 0


@pytest.mark.parametrize(
    "payload",
    [
        b"<html>not data</html>",
        b"\xff",
        PAYLOAD.replace(b"STATION|", b"MISSING|", 1),
        PAYLOAD.replace(b"Station_name|", b"STATION|", 1),
        PAYLOAD + b"too|few|columns\n",
        altered({"DATE": "invalid"}),
        altered({"DATE": "2010-01-01"}),
        altered({"DATE": "2011-01-01T00:00:00"}),
        altered({"STATION": "POM00008549"}),
    ],
)
def test_malformed_source_aborts_whole_batch(payload: bytes) -> None:
    with pytest.raises(GHCNhError):
        from_http(payload)


def test_duplicates_are_counted_and_conflicts_fail() -> None:
    batch = from_http(altered({}, {}))
    assert batch.stats.received == 2 and batch.stats.accepted == 1 and batch.duplicates == 1
    with pytest.raises(GHCNhError, match="conflicting duplicate"):
        from_http(altered({}, {FIELD: "8.0"}))


def test_byte_row_and_checksum_bounds() -> None:
    with pytest.raises(GHCNhError, match="byte limit"):
        from_http(PAYLOAD, limits=DownloadLimits(max_bytes=100))
    with pytest.raises(GHCNhError, match="row limit"):
        from_http(PAYLOAD, limits=DownloadLimits(max_rows=1))
    with pytest.raises(GHCNhError, match="checksum changed"):
        from_http(PAYLOAD, expected_hashes={2010: "0" * 64})
    with pytest.raises(GHCNhError, match="requested years"):
        from_http(PAYLOAD, expected_hashes={2011: "0" * 64})


def test_fixture_tampering_and_wrong_year_fail(tmp_path: Path) -> None:
    manifest = json.loads(MANIFEST.read_text())
    (tmp_path / "provenance.json").write_text(json.dumps(manifest))
    (tmp_path / manifest["fixture"]["file"]).write_bytes(PAYLOAD + b"changed")
    with pytest.raises(GHCNhError, match="checksum"):
        acquire(request(), fixture_manifest=tmp_path / "provenance.json")
    with pytest.raises(GHCNhError, match="station-year"):
        acquire(request("2011-01-01T00:00:00Z", "2011-01-02T00:00:00Z"), fixture_manifest=MANIFEST)


def test_transport_retries_have_backoff_and_request_timeout() -> None:
    calls = []
    delays = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req)
        assert req.extensions["timeout"]["read"] == 30.0
        if len(calls) < 3:
            raise httpx.ReadTimeout("controlled timeout", request=req)
        return httpx.Response(200, content=PAYLOAD, headers={"ETag": "fixture"})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batch = acquire(request(), client=client, sleep=delays.append)
    assert delays == [0.5, 1.0]
    assert batch.sources[0]["attempts"] == 3 and batch.sources[0]["etag"] == "fixture"
    assert all(str(r.url).endswith("/2010/psv/GHCNh_POMU0068545_2010.psv") for r in calls)


def test_interrupted_body_is_discarded_before_retry() -> None:
    class BrokenStream(httpx.SyncByteStream):
        def __iter__(self):
            yield PAYLOAD[:10_000]
            raise httpx.ReadError("controlled interrupted body")

    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return (
            httpx.Response(200, stream=BrokenStream())
            if calls == 1
            else httpx.Response(200, content=PAYLOAD)
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batch = acquire(request(), client=client, sleep=lambda _: None)
    assert calls == 2 and batch.stats.received == 6 and batch.stats.accepted == 2


def test_retry_after_and_nonretryable_statuses() -> None:
    statuses = iter([429, 200])
    delays = []
    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(next(statuses), content=PAYLOAD, headers={"Retry-After": "2"})
        )
    ) as client:
        assert acquire(request(), client=client, sleep=delays.append).stats.accepted == 2
    assert delays == [2.0]
    for status in (301, 404):
        with (
            httpx.Client(
                transport=httpx.MockTransport(lambda _, s=status: httpx.Response(s))
            ) as client,
            pytest.raises(GHCNhError, match="not retried"),
        ):
            acquire(request(), client=client, sleep=lambda _: pytest.fail("must not retry"))
    with (
        httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(429, headers={"Retry-After": "120"})
            )
        ) as client,
        pytest.raises(GHCNhError, match="bounded retry"),
    ):
        acquire(request(), client=client, sleep=lambda _: pytest.fail("must not sleep"))


def test_download_deadline_is_checked_during_streaming() -> None:
    times = iter([0.0, 0.0, 91.0])
    with pytest.raises(GHCNhError, match="budget exhausted"):
        from_http(PAYLOAD, clock=lambda: next(times))


def test_successful_year_chunks_have_separate_provenance() -> None:
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        payload = altered({"DATE": "2009-12-31T12:00:00"}) if "/2009/" in str(req.url) else PAYLOAD
        return httpx.Response(200, content=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        batch = acquire(request("2009-12-31T00:00:00Z", "2010-01-02T00:00:00Z"), client=client)
    assert len(calls) == 2 and len(batch.records) == 3
    assert [s["year"] for s in batch.sources] == [2009, 2010]
    assert (
        batch.records[0].lineage["chunk"]["sha256"] != batch.records[1].lineage["chunk"]["sha256"]
    )


def test_invalid_http_encoding_has_a_structured_failure() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.DecodingError("controlled invalid gzip")

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
        pytest.raises(GHCNhError, match="content encoding"),
    ):
        acquire(request(), client=client, sleep=lambda _: pytest.fail("must not retry decoding"))


def test_year_chunking_and_partial_failure_never_reaches_persistence(monkeypatch, capsys) -> None:
    previous = altered({"DATE": "2009-12-31T12:00:00"})
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        return (
            httpx.Response(200, content=previous)
            if "/2009/" in str(req.url)
            else httpx.Response(503)
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:

        def fetch(req, **_):
            return acquire(req, client=client, sleep=lambda _: None)

        monkeypatch.setattr(cli, "acquire", fetch)
        monkeypatch.setattr(
            cli, "_persist", lambda *_: pytest.fail("partial data must not be persisted")
        )
        code = cli.run(
            [
                "--start",
                "2009-12-31T00:00:00Z",
                "--end",
                "2010-01-02T00:00:00Z",
                "--asset-id",
                "porto_gauge",
                "--city-id",
                "test_city",
                "--write",
            ]
        )
    report = json.loads(capsys.readouterr().out)
    assert code == 2 and report["status"] == "failed" and report["inserted"] == 0
    assert len(report["completed_sources"]) == 1 and len(calls) == 4
    assert report["completed_sources"][0]["year"] == 2009
    assert list(request("2009-12-31T00:00:00Z", "2010-01-01T00:00:00Z").years) == [2009]


def test_cli_offline_dry_run_has_no_database_dependency(tmp_path: Path) -> None:
    output = tmp_path / "report.json"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "floodmvp.jobs.ingest_noaa_ghcnh",
            "--start",
            "2010-01-01T00:00:00Z",
            "--end",
            "2010-01-12T00:00:00Z",
            "--asset-id",
            "porto_gauge",
            "--city-id",
            "test_city",
            "--fixture-manifest",
            str(MANIFEST),
            "--report",
            str(output),
            "--dry-run",
        ],
        env=dict(os.environ, DATABASE_URL="invalid://do-not-connect"),
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report == json.loads(output.read_text())
    assert report["dry_run"] and report["asset_validation"] == "not_checked"
    assert report["accepted"] == 2 and report["inserted"] == 0


def test_write_failure_keeps_completed_source_provenance(monkeypatch, capsys) -> None:
    async def fail_write(*_):
        raise GHCNhError("controlled write rejection")

    monkeypatch.setattr(cli, "_persist", fail_write)
    result = cli.run(
        [
            "--start",
            "2010-01-01T00:00:00Z",
            "--end",
            "2010-01-12T00:00:00Z",
            "--asset-id",
            "porto_gauge",
            "--city-id",
            "test_city",
            "--fixture-manifest",
            str(MANIFEST),
            "--write",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert result == 2 and report["inserted"] == 0
    assert report["completed_sources"][0]["mode"] == "recorded_fixture"
    assert (
        report["completed_sources"][0]["sha256"]
        == json.loads(MANIFEST.read_text())["fixture"]["sha256"]
    )
