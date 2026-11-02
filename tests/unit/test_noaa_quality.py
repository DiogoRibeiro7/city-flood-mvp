"""Recorded fixture snapshots; modified rows below are controlled test cases only."""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from floodmvp.adapters.noaa_ghcnh import (
    FIELD,
    DownloadLimits,
    GHCNhError,
    GHCNhRequest,
    SourceChunk,
    acquire,
    iter_chunks,
    load_fixture,
)
from floodmvp.analytics.noaa_quality import QualityPolicy, characterize, render_markdown
from floodmvp.jobs import validate_noaa_ghcnh as cli

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/real_sources/noaa_ghcnh"
MANIFEST = FIXTURE / "provenance.json"
PAYLOAD = (FIXTURE / "porto_2010_excerpt.psv").read_bytes()


def request(start="2010-01-01T00:00:00Z", end="2010-01-02T00:00:00Z"):
    return GHCNhRequest(
        "POMU0068545", "unused", dt.datetime.fromisoformat(start), dt.datetime.fromisoformat(end)
    )


def controlled_rows(*changes: dict[str, str]) -> bytes:
    reader = csv.DictReader(io.StringIO(PAYLOAD.decode()), delimiter="|")
    row = next(reader)
    stream = io.StringIO()
    writer = csv.DictWriter(
        stream, fieldnames=reader.fieldnames, delimiter="|", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(dict(row, **change) for change in changes)
    return stream.getvalue().encode()


def chunk(payload, year=2010, mode="http"):
    return SourceChunk(
        year,
        payload,
        {
            "year": year,
            "mode": mode,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "url": "https://example.invalid/controlled-test",
            "retrieved_at": "2026-01-01T00:00:00+00:00",
        },
    )


def test_recorded_fixture_snapshots():
    selection = request(end="2010-01-12T00:00:00Z")
    report = characterize(selection, [load_fixture(MANIFEST, selection, DownloadLimits())])
    # Manifest bytes can use platform-specific line endings; payload SHA is invariant.
    report["sources"][0].pop("manifest_sha256")
    assert report == json.loads((FIXTURE / "quality.snapshot.json").read_text())
    assert render_markdown(report) == (FIXTURE / "quality.snapshot.md").read_text()
    assert report["coverage"] is None and report["freshness"] is None
    assert report["sampling"] is None and report["daily"] == []
    assert report["counts"]["states_by_unique_timestamp"] == {
        "missing_rainfall": 3,
        "observed_positive": 2,
        "observed_zero": 0,
        "trace_rainfall": 1,
    }
    source = report["sources"][0]
    markdown = render_markdown(report)
    assert f"upstream SHA-256 `{source['original_sha256']}`" in markdown
    assert f"excerpt SHA-256 `{source['sha256']}`" in markdown


def test_missing_trace_and_zero_are_distinct_and_match_ingestion():
    payload = controlled_rows(
        {"DATE": "2010-01-01T00:00:00", FIELD: ""},
        {"DATE": "2010-01-01T06:00:00", FIELD: "0.0"},
        {"DATE": "2010-01-01T12:00:00", FIELD: "0.0", f"{FIELD}_Measurement_Code": "T"},
        {"DATE": "2010-01-01T18:00:00", FIELD: "12.0"},
    )
    report = characterize(request(), [chunk(payload)])
    assert report["counts"]["states_by_unique_timestamp"] == {
        "missing_rainfall": 1,
        "observed_positive": 1,
        "observed_zero": 1,
        "trace_rainfall": 1,
    }
    grid = report["coverage"]["assumed_grid"]
    assert grid["expected_slots"] == 4 and grid["quantitative_slots"] == 2
    assert grid["quantitative_fraction"] == 0.5
    support = report["coverage"]["interval_support"]
    assert support["supported_minutes"] == 720
    assert [gap["minutes"] for gap in support["unsupported_intervals"]] == [360, 360]
    with httpx.Client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=payload))
    ) as client:
        batch = acquire(request(), client=client)
    assert len(batch.records) == report["counts"]["quantitative_observations"]
    assert [r.value for r in batch.records] == [0.0, 2.0]


def test_duplicates_excluded_conflicts_and_overlaps_never_double_count():
    payload = controlled_rows(
        {"DATE": "2010-01-01T06:00:00"},
        {"DATE": "2010-01-01T09:00:00"},
        {"DATE": "2010-01-01T09:00:00"},
        {"DATE": "2010-01-01T12:00:00"},
        {"DATE": "2010-01-01T18:00:00", FIELD: "0"},
        {"DATE": "2010-01-01T18:00:00", FIELD: "4"},
    )
    report = characterize(request(), [chunk(payload)])
    counts = report["counts"]
    assert counts["duplicate_extra_rows"] == 2
    assert counts["exact_duplicate_extra_rows"] == 1 and counts["conflicting_timestamps"] == 1
    assert counts["quantitative_observations"] == 3
    assert report["coverage"]["interval_support"]["supported_minutes"] == 720
    sampling = report["sampling"]["quantitative_rainfall"]
    assert sampling["off_grid_timestamps"] == 1
    assert sampling["deltas_different_from_assumed_cadence"] == 2
    assert sampling["delta_minutes_histogram"] == [{"minutes": 180.0, "count": 2}]
    # A conflict still proves a weather report arrived, but supplies no usable rainfall.
    assert report["sampling"]["weather_reports"]["timestamps"] == 4
    assert report["freshness"]["weather_reports"]["latest"] == "2010-01-01T18:00:00+00:00"
    assert report["freshness"]["quantitative_rainfall"]["latest"] == "2010-01-01T12:00:00+00:00"


def test_daily_markdown_retains_rejected_and_conflicting_states():
    report = characterize(
        request(),
        [
            chunk(
                controlled_rows(
                    {"DATE": "2010-01-01T06:00:00", FIELD: "0"},
                    {"DATE": "2010-01-01T12:00:00", FIELD: "-1"},
                    {"DATE": "2010-01-01T18:00:00", FIELD: "0"},
                    {"DATE": "2010-01-01T18:00:00", FIELD: "4"},
                )
            )
        ],
    )
    assert report["daily"][0]["states"] == {
        "observed_zero": 1,
        "invalid_numeric_value": 1,
        "conflicting_duplicate": 1,
    }
    markdown = render_markdown(report)
    assert (
        "| 2010-01-01T00:00:00+00:00 | 1 | 1 | 0 | 0 | conflicting_duplicate: 1; invalid_numeric_value: 1 | 360 / 1440 |"
        in markdown
    )
    assert f"upstream SHA-256 `{report['sources'][0]['sha256']}`" in markdown
    assert "excerpt SHA-256" not in markdown


@pytest.mark.parametrize(
    ("changes", "issue"),
    [
        ({FIELD: "-1"}, "impossible_rainfall"),
        ({FIELD: "NaN"}, "impossible_rainfall"),
        ({FIELD: "inf"}, "impossible_rainfall"),
        ({FIELD: "oops"}, "invalid_rainfall_number"),
        ({FIELD: "2 in"}, "embedded_unit_token"),
        ({FIELD: "2 mm/h"}, "embedded_unit_token"),
        ({"LATITUDE": "91"}, "impossible_coordinates"),
        ({"LONGITUDE": "-181"}, "impossible_coordinates"),
        ({"ELEVATION": "NaN"}, "impossible_coordinates"),
        ({"LATITUDE": "oops"}, "invalid_coordinate_number"),
        ({f"{FIELD}_Quality_Code": "1"}, "source_quality_flag"),
        ({f"{FIELD}_Measurement_Code": "X"}, "unsupported_measurement_code"),
    ],
)
def test_impossible_values_and_unit_contract_evidence(changes, issue):
    report = characterize(request(), [chunk(controlled_rows(changes))])
    assert report["counts"]["issues_by_raw_row"][issue] == 1
    assert report["counts"]["quantitative_observations"] == 0
    assert report["coverage"]["interval_support"]["supported_minutes"] == 0
    assert report["unit_check"]["status"] == "contract_only"


def test_no_rainfall_does_not_mean_silent_station_or_dry_weather():
    report = characterize(
        request(), [chunk(controlled_rows({"DATE": "2010-01-01T23:00:00", FIELD: ""}))]
    )
    assert report["freshness"]["weather_reports"]["age_minutes"] == 60
    assert report["freshness"]["quantitative_rainfall"]["status"] == "no_observation_in_window"
    assert report["coverage"]["assumed_grid"]["states"] == {"no_weather_report": 4}
    assert report["coverage"]["interval_support"]["unsupported_minutes"] == 1440


def test_staleness_relative_to_historical_window_not_current_time():
    payload = controlled_rows(
        {"DATE": "2010-01-01T06:00:00"}, {"DATE": "2010-01-01T23:00:00", FIELD: ""}
    )
    report = characterize(
        request(), [chunk(payload)], policy=QualityPolicy(stale_after_minutes=360)
    )
    assert report["freshness"]["quantitative_rainfall"]["status"] == "stale_at_window_end"
    assert report["freshness"]["weather_reports"]["status"] == "within_threshold_at_window_end"
    boundary = characterize(
        request(), [chunk(payload)], policy=QualityPolicy(stale_after_minutes=1080)
    )
    assert (
        boundary["freshness"]["quantitative_rainfall"]["status"] == "within_threshold_at_window_end"
    )


def test_window_edges_offsets_and_daily_support():
    selection = request("2010-01-01T22:00:00+01:00", "2010-01-02T02:00:00Z")
    payload = controlled_rows(
        {"DATE": "2010-01-01T20:00:00"},
        {"DATE": "2010-01-01T21:00:00"},
        {"DATE": "2010-01-02T01:00:00"},
        {"DATE": "2010-01-02T02:00:00"},
    )
    report = characterize(selection, [chunk(payload)])
    assert report["counts"]["outside_window"] == 2
    assert report["counts"]["quantitative_observations"] == 2
    assert report["coverage"]["interval_support"]["supported_minutes"] == 240
    assert [day["supported_minutes"] for day in report["daily"]] == [180, 60]
    assert [day["window_minutes"] for day in report["daily"]] == [180, 120]


def test_empty_window_and_grid_without_slots():
    selection = request("2010-01-01T01:00:00Z", "2010-01-01T02:00:00Z")
    report = characterize(selection, [chunk(controlled_rows({}))])
    assert report["counts"]["selected_rows"] == 0
    assert report["coverage"]["assumed_grid"]["quantitative_fraction"] is None
    assert report["coverage"]["interval_support"]["supported_fraction"] == 0
    assert report["freshness"]["weather_reports"]["latest"] is None
    assert "not dry" in render_markdown(report)


@pytest.mark.parametrize(
    "payload", [b"bad", PAYLOAD.replace(FIELD.encode(), b"precipitation_6_hour_inches")]
)
def test_malformed_or_wrong_unit_schema_cannot_produce_coverage(payload):
    with pytest.raises(GHCNhError, match="header"):
        characterize(request(), [chunk(payload)])


def test_missing_or_repeated_year_cannot_produce_coverage():
    for chunks in ([], [chunk(PAYLOAD), chunk(PAYLOAD)]):
        with pytest.raises(GHCNhError, match="year|annual chunk"):
            characterize(request(), chunks)


def test_acquisition_failure_preserves_completed_sources_without_partial_metrics(
    monkeypatch, capsys
):
    selection = request("2009-12-31T00:00:00Z", "2010-01-02T00:00:00Z")

    def partial(*args, **kwargs):
        yield chunk(controlled_rows({"DATE": "2009-12-31T18:00:00"}), year=2009)
        raise GHCNhError("HTTP 503; exhausted 3 attempts")

    monkeypatch.setattr(cli, "iter_chunks", partial)
    assert (
        cli.run(["--start", selection.start.isoformat(), "--end", selection.end.isoformat()]) == 2
    )
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed" and report["coverage"] is None
    assert len(report["completed_sources"]) == 1
    assert "No coverage metrics" in render_markdown(report)


def test_checksum_failure_and_bounded_source_parsing():
    with (
        httpx.Client(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=PAYLOAD))
        ) as client,
        pytest.raises(GHCNhError, match="checksum"),
    ):
        characterize(
            request(), iter_chunks(request(), client=client, expected_hashes={2010: "0" * 64})
        )
    with pytest.raises(GHCNhError, match="row limit"):
        characterize(request(), [chunk(PAYLOAD)], limits=DownloadLimits(max_rows=1))


@pytest.mark.parametrize(
    "policy",
    [
        {"expected_cadence_minutes": 0},
        {"stale_after_minutes": -1},
        {"expected_cadence_minutes": 44641},
    ],
)
def test_invalid_policy(policy):
    with pytest.raises(GHCNhError):
        QualityPolicy(**policy)


def test_offline_cli_has_no_database_dependency(tmp_path):
    json_path, md_path = tmp_path / "report.json", tmp_path / "report.md"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "floodmvp.jobs.validate_noaa_ghcnh",
            "--start",
            "2010-01-01T00:00:00Z",
            "--end",
            "2010-01-12T00:00:00Z",
            "--fixture-manifest",
            str(MANIFEST),
            "--json-report",
            str(json_path),
            "--markdown-report",
            str(md_path),
        ],
        env=dict(os.environ, DATABASE_URL="not-a-database-url"),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report == json.loads(json_path.read_text())
    assert md_path.read_text() == render_markdown(report)


def test_report_write_failure_is_explicit(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "_write_text", lambda *args: (_ for _ in ()).throw(OSError()))
    assert (
        cli.run(
            [
                "--start",
                "2010-01-01T00:00:00Z",
                "--end",
                "2010-01-02T00:00:00Z",
                "--fixture-manifest",
                str(MANIFEST),
                "--json-report",
                str(tmp_path / "report.json"),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert json.loads(captured.out)["status"] == "characterized"
    assert "Could not save" in captured.err


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--start", "not-a-date"),
        ("--end", "not-a-date"),
        ("--start", "2010-01-01T00:00:00"),
        ("--start", "0001-01-01T00:00:00+01:00"),
        ("--end", "9999-12-31T23:00:00-02:00"),
        ("--expected-sha256", "no-separator"),
        ("--expected-sha256", "year=" + "a" * 64),
        ("--expected-sha256", "2010=too-short"),
    ],
)
def test_argument_errors_name_the_option_and_emit_failure_reports(
    option, value, monkeypatch, capsys, tmp_path
):
    def unexpected_acquisition(*args, **kwargs):
        raise AssertionError("invalid arguments must not reach acquisition")

    monkeypatch.setattr(cli, "iter_chunks", unexpected_acquisition)
    json_path, md_path = tmp_path / "failure.json", tmp_path / "failure.md"
    assert (
        cli.run(
            [
                "--start",
                "2010-01-01T00:00:00Z",
                "--end",
                "2010-01-02T00:00:00Z",
                option,
                value,
                "--json-report",
                str(json_path),
                "--markdown-report",
                str(md_path),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report["status"] == "failed" and report["coverage"] is None
    assert option in report["error"]
    assert report == json.loads(json_path.read_text())
    assert option in md_path.read_text()
    assert "Traceback" not in captured.err


def test_window_overflow_is_reported_without_traceback(monkeypatch, capsys):
    def overflow(*args, **kwargs):
        raise OverflowError("date value out of range")

    monkeypatch.setattr(cli, "characterize", overflow)
    assert cli.run(["--start", "2010-01-01T00:00:00Z", "--end", "2010-01-02T00:00:00Z"]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == "failed" and "out of range" in report["error"]


@pytest.mark.skipif(os.name != "posix", reason="POSIX access modes are not Windows ACLs")
@pytest.mark.parametrize("existing_mode", [None, 0o600, 0o640])
def test_atomic_report_modes_are_readable_or_preserve_existing_access(tmp_path, existing_mode):
    path = tmp_path / "report.json"
    if existing_mode is not None:
        path.write_text("old")
        path.chmod(existing_mode)
    cli._write_text(path, "new\n")
    assert path.read_text() == "new\n"
    assert stat.S_IMODE(path.stat().st_mode) == (0o644 if existing_mode is None else existing_mode)
    assert list(tmp_path.iterdir()) == [path]
