"""Recorded source examples plus explicitly controlled contract/failure cases."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

import pytest

from floodmvp.adapters.noaa_ghcnh import (
    DownloadLimits,
    GHCNhError,
    GHCNhRequest,
    acquire,
    load_fixture,
    normalize_chunks,
)
from floodmvp.analytics.noaa_quality import characterize
from floodmvp.analytics.rain_intervals import describe_rain_intervals
from scripts import noaa_case_study as case

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/real_sources/noaa_ghcnh/provenance.json"


def source():
    request = GHCNhRequest(case.STATION, case.ASSET, case.START, case.END)
    chunks = [load_fixture(FIXTURE, request, DownloadLimits())]
    return request, chunks, normalize_chunks(request, chunks)


def test_quality_and_ingestion_share_the_exact_recorded_bytes():
    request, chunks, batch = source()
    assert batch == acquire(request, fixture_manifest=FIXTURE)
    quality = characterize(request, chunks)
    assert quality["counts"]["quantitative_observations"] == len(batch.records) == 2
    analysis = describe_rain_intervals(batch.records, case.START, case.END)
    assert analysis["reported_wet_intervals"] == 2 and analysis["observed_zero_intervals"] == 0
    assert [r["minutes_inside_window"] for r in analysis["intervals"]] == [0, 360]
    assert analysis["maximum_reported_depth_mm"] == 7.9
    assert analysis["event_evaluation"]["precision"] is None
    assert analysis["event_evaluation"]["confirmed_flood_incidents"] is None
    assert analysis["operational_detector"]["status"] == "not_run"
    timeline = case.timeline_rows(analysis, quality, chunks, request)
    assert len(timeline) == 3
    assert timeline[-1]["kind"] == "source_trace_report" and timeline[-1]["depth_mm"] is None
    assert not any(row["kind"] == "unknown_amount_interval" for row in timeline)


def test_observed_zero_remains_different_from_trace_and_missing():
    _, _, batch = source()
    lineage = copy.deepcopy(batch.records[1].lineage)
    lineage["observation"]["depth_mm"] = 0.0
    zero = replace(batch.records[1], value=0.0, lineage=lineage)
    result = describe_rain_intervals([zero], case.START, case.END)
    assert result["observed_zero_intervals"] == 1
    assert result["reported_wet_intervals"] == 0
    lineage["observation"]["attributes"]["Measurement_Code"] = "T"
    with pytest.raises(ValueError, match="six-hour rainfall contract"):
        describe_rain_intervals([zero], case.START, case.END)


@pytest.mark.parametrize(
    "change", ["wrong_mean", "wrong_interval", "negative", "quality_flag", "wrong_metric"]
)
def test_interval_analytics_rejects_incompatible_values(change):
    _, _, batch = source()
    row = copy.deepcopy(batch.records[1])
    if change == "wrong_mean":
        row = replace(row, value=100)
    elif change == "wrong_interval":
        row.lineage["observation"]["interval_minutes"] = 720
    elif change == "negative":
        row.lineage["observation"]["depth_mm"] = -1
    elif change == "quality_flag":
        row.lineage["observation"]["attributes"]["Quality_Code"] = "1"
    else:
        row = replace(row, metric="rain_mmph")
    with pytest.raises(ValueError, match="six-hour rainfall contract"):
        describe_rain_intervals([row], case.START, case.END)


def test_duplicate_observations_and_incomplete_source_years_fail():
    request, chunks, batch = source()
    with pytest.raises(ValueError, match="deduplicated"):
        describe_rain_intervals([batch.records[0]] * 2, case.START, case.END)
    for invalid in ([], chunks * 2):
        with pytest.raises(GHCNhError, match="requested year|annual chunk"):
            normalize_chunks(request, invalid)


def test_cached_source_is_pinned_and_curated_rows_cannot_be_promoted(tmp_path, monkeypatch):
    # Tiny controlled bytes exercise cache validation; these are not observed metrics.
    payload = b"controlled cache bytes\n"
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(case, "SOURCE_SHA256", digest)
    path = tmp_path / "manifest.json"
    request, _, _ = source()
    manifest = {
        "schema_version": 1,
        "scope": "complete_station_year",
        "license": "CC0-1.0",
        "station_id": case.STATION,
        "files": [
            {
                "file": "source.psv",
                "provenance": {
                    "year": 2010,
                    "url": case.source_url(case.STATION, 2010),
                    "sha256": digest,
                    "bytes": len(payload),
                    "mode": "http",
                    "retrieved_at": "2026-11-02T00:00:00Z",
                },
            }
        ],
    }
    (tmp_path / "source.psv").write_bytes(payload)
    case.write_json(path, manifest)
    assert case.load_cached_source(path, request)[0].payload == payload
    manifest["scope"] = "selected_rows_only"
    case.write_json(path, manifest)
    with pytest.raises(case.CaseStudyError, match="complete CC0"):
        case.load_cached_source(path, request)
    manifest["scope"] = "complete_station_year"
    manifest["files"][0]["file"] = "../outside.psv"
    case.write_json(path, manifest)
    with pytest.raises(case.CaseStudyError, match="sibling"):
        case.load_cached_source(path, request)
    manifest["files"][0]["file"] = "source.psv"
    case.write_json(path, manifest)
    (tmp_path / "source.psv").write_bytes(b"tampered")
    with pytest.raises(case.CaseStudyError, match="checksum/metadata"):
        case.load_cached_source(path, request)


def test_cleanup_refuses_a_container_without_the_expected_owner(tmp_path, monkeypatch):
    operations = []

    def command(*args, **kwargs):
        operations.append(args[:2])
        if args[:2] == ("docker", "create"):
            return "a" * 64
        if args[:2] == ("docker", "inspect"):
            return "a" * 64 + "|wrong-owner"
        pytest.fail("unowned container must not be started or removed")

    monkeypatch.setattr(case, "command", command)
    with pytest.raises(case.CaseStudyError, match="ownership"), case.disposable_server(tmp_path):
        pytest.fail("must refuse before database use")
    assert ("docker", "rm") not in operations
    assert json.loads((tmp_path / "resources.json").read_text())["cleanup"] == "failed_or_refused"


def test_existing_output_is_never_overwritten(tmp_path, monkeypatch):
    marker = tmp_path / "existing"
    marker.write_text("keep")
    monkeypatch.setattr(case, "code_provenance", lambda: pytest.fail("preflight must not run"))
    assert case.run(["--output-dir", str(tmp_path)]) == 2
    assert marker.read_text() == "keep"


def test_failure_manifest_does_not_claim_success_or_expose_driver_details(tmp_path, monkeypatch):
    def fail():
        raise RuntimeError("sensitive driver details")

    monkeypatch.setattr(case, "code_provenance", fail)
    output = tmp_path / "failure"
    assert case.run(["--output-dir", str(output)]) == 2
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["status"] == "failed" and manifest["failed_stage"] == "preflight"
    assert "sensitive driver details" not in json.dumps(manifest)


def test_artifact_structure_keeps_fixture_scope_and_missing_amounts(tmp_path):
    pytest.importorskip("matplotlib", reason="optional case-study plotting group")
    request, chunks, batch = source()
    quality = characterize(request, chunks)
    analytics = describe_rain_intervals(batch.records, case.START, case.END)
    timeline = case.timeline_rows(analytics, quality, chunks, request)
    # Controlled repository receipts exercise presentation only; the live run proves DB writes.
    ingestion = {"first_import": {"inserted": 2}, "replay": {"inserted": 0, "existing": 2}}
    case.write_outputs(tmp_path, analytics, quality, ingestion, timeline)
    assert all((tmp_path / name).is_file() for name in case.SMALL_ARTIFACTS)
    assert ET.parse(tmp_path / "rainfall.svg").getroot().tag.endswith("svg")
    assert (tmp_path / "rainfall.png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with (tmp_path / "timeline.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[-1]["depth_mm"] == "" and rows[-1]["kind"] == "source_trace_report"
    result = json.loads((tmp_path / "case-study.json").read_text())
    assert result["scope"] == "selected_rows_only"
    assert result["analytics"]["event_evaluation"]["precision"] is None
    assert "not assessed" in (tmp_path / "report.md").read_text()
