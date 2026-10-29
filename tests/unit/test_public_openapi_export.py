from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from floodmvp.api.main import app
from scripts.export_openapi import build_public_spec

PUBLIC_SPEC = Path(__file__).resolve().parents[2] / "docs/openapi/public.yaml"


def _documented_error_code(
    spec: dict[str, Any], method: str, path: str, status: str
) -> str:
    """Follow a response reference and extract its advertised error code."""
    response = spec["paths"][path][method]["responses"][status]
    if "$ref" in response:
        component = response["$ref"].rsplit("/", 1)[-1]
        response = spec["components"]["responses"][component]
    return str(response["content"]["application/json"]["example"]["error"]["code"])


def test_public_openapi_snapshot_matches_live_routes_and_responses() -> None:
    """Fail CI when the checked-in public contract is stale."""
    checked_in = yaml.safe_load(PUBLIC_SPEC.read_text(encoding="utf-8"))
    generated = build_public_spec()

    assert checked_in == generated
    live_paths = app.openapi()["paths"]
    assert checked_in["paths"].keys() == live_paths.keys()
    for path, operations in live_paths.items():
        assert operations.keys() == checked_in["paths"][path].keys()


@pytest.mark.parametrize(
    ("method", "path", "status", "expected_code"),
    [
        ("get", "/v1/cities/{city_id}", "404", "CITY_NOT_FOUND"),
        ("get", "/v1/assets/{asset_id}", "404", "ASSET_NOT_FOUND"),
        ("get", "/v1/assets/{asset_id}/upstream", "404", "ASSET_NOT_FOUND"),
        ("get", "/v1/assets/{asset_id}/downstream", "404", "ASSET_NOT_FOUND"),
        ("get", "/v1/assets/{asset_id}/metrics", "404", "SCENARIO_NOT_FOUND"),
        ("get", "/v1/assets/{asset_id}/observations", "404", "SCENARIO_NOT_FOUND"),
        (
            "get",
            "/v1/assets/{asset_id}/observations:compare",
            "404",
            "SCENARIO_NOT_FOUND",
        ),
        ("post", "/v1/telemetry/events:batch", "404", "ASSET_NOT_FOUND"),
        ("get", "/v1/analytics/jobs/{job_id}", "404", "JOB_NOT_FOUND"),
        ("get", "/v1/analytics/jobs/{job_id}/download", "400", "JOB_NOT_READY"),
        ("get", "/v1/analytics/jobs/{job_id}/download", "404", "JOB_NOT_FOUND"),
    ],
)
def test_public_openapi_keeps_specific_error_codes(
    method: str, path: str, status: str, expected_code: str
) -> None:
    spec = build_public_spec()

    assert _documented_error_code(spec, method, path, status) == expected_code


def test_export_does_not_modify_fastapi_cached_schema() -> None:
    original = copy.deepcopy(app.openapi())

    exported = build_public_spec()

    assert app.openapi() == original
    assert exported is not app.openapi()
