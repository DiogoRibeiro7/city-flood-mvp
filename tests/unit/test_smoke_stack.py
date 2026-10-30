from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import subprocess
import urllib.error
from pathlib import Path
from unittest.mock import Mock

import pytest

from scripts.seed_smoke import require_smoke_database
from scripts.smoke_fixture import RAIN_ID, RAIN_VALUES, START
from scripts.smoke_stack import SmokeError, Stack, job_completed, run, verify_csv, wait_for


@pytest.fixture()
def fake_clock(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    clock = [0.0]
    monkeypatch.setattr("scripts.smoke_stack.time.monotonic", lambda: clock[0])

    def advance(seconds: float) -> None:
        clock[0] += seconds

    monkeypatch.setattr("scripts.smoke_stack.time.sleep", advance)
    return clock


def test_readiness_retries_transport_error_and_unready_state(fake_clock: list[float]) -> None:
    probe = Mock(
        side_effect=[urllib.error.URLError("refused"), {"status": "starting"}, {"status": "ok"}]
    )
    assert wait_for("API", probe, lambda value: value["status"] == "ok", 5) == {"status": "ok"}
    assert fake_clock == [2.0]


def test_queue_deadline_reports_last_state_without_oversleeping(fake_clock: list[float]) -> None:
    with pytest.raises(SmokeError, match="export.*queued"):
        wait_for("export", lambda: {"status": "queued"}, job_completed, 2.5)
    assert fake_clock == [2.5]


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_terminal_job_failure_is_immediate(status: str, fake_clock: list[float]) -> None:
    with pytest.raises(SmokeError, match="unsuccessful terminal state"):
        wait_for(
            "export", lambda: {"status": status, "error_message": "bad query"}, job_completed, 30
        )
    assert fake_clock == [0.0]


def fixture_csv() -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["asset_id", "metric", "ts", "value"])
    for index, value in enumerate(RAIN_VALUES):
        writer.writerow(
            [RAIN_ID, "rain_mmph", (START + dt.timedelta(minutes=5 * index)).isoformat(), value]
        )
    return output.getvalue()


def test_export_requires_exact_measurements() -> None:
    verify_csv(fixture_csv())
    for corrupt in (
        fixture_csv().replace("8.0", "9.0", 1),
        fixture_csv().replace("rain_mmph", "wrong_metric", 1),
        fixture_csv().replace("00:05:00", "00:06:00", 1),
        fixture_csv().splitlines()[0],
        "wrong,columns\n1,2\n",
    ):
        with pytest.raises(SmokeError, match="CSV"):
            verify_csv(corrupt)


@pytest.mark.parametrize(
    ("url", "app_env", "project"),
    [
        ("postgresql://postgres@db/floodmvp", "test", "city-flood-smoke-012345abcdef"),
        ("postgresql://postgres@db/floodmvp_smoke_test", "prod", "city-flood-smoke-012345abcdef"),
        (
            "postgresql://postgres@production/floodmvp_smoke_test",
            "test",
            "city-flood-smoke-012345abcdef",
        ),
        ("postgresql://postgres@db/floodmvp_smoke_test", "test", "application"),
        ("postgresql://postgres@db/floodmvp_smoke_test", "test", ""),
        ("sqlite:///floodmvp_smoke_test", "test", "city-flood-smoke-012345abcdef"),
    ],
)
def test_smoke_seeder_rejects_application_targets(url: str, app_env: str, project: str) -> None:
    with pytest.raises(ValueError, match="isolated Compose"):
        require_smoke_database(url, app_env, project)


def test_smoke_seeder_accepts_only_explicit_isolated_configuration() -> None:
    require_smoke_database(
        "postgresql+asyncpg://postgres:smoke-test-only@db/floodmvp_smoke_test",
        "test",
        "city-flood-smoke-012345abcdef",
    )


def test_stack_ignores_ambient_compose_project_and_env_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COMPOSE_FILE", "production.yml")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "production")
    monkeypatch.setenv("COMPOSE_ENV_FILES", "production.env")
    monkeypatch.setenv("SMOKE_PROJECT", "production")
    stack = Stack(tmp_path)
    assert not any(key.startswith("COMPOSE_") for key in stack.env)
    assert stack.env["SMOKE_PROJECT"] == stack.project
    assert stack.compose[stack.compose.index("--env-file") + 1] == str(stack.env_file)
    assert stack.compose[stack.compose.index("-p") + 1] == stack.project
    assert "production" not in stack.env_file.read_text()


def test_existing_stopped_container_is_not_adopted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = Stack(tmp_path)
    command = Mock(return_value=subprocess.CompletedProcess([], 0, "existing-container", ""))
    monkeypatch.setattr(stack, "command", command)
    with pytest.raises(SmokeError, match="Refusing to reuse"):
        stack.require_unused_project()
    assert "--all" in command.call_args.args


@pytest.mark.parametrize("fault", ["preflight", "exercise", "cleanup", None])
def test_run_records_failures_and_cleans_only_owned_resources(
    fault: str | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stack = Stack(tmp_path)
    monkeypatch.setattr("scripts.smoke_stack.Stack", lambda artifacts: stack)
    monkeypatch.setattr(
        stack, "command", Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    )
    monkeypatch.setattr(
        stack,
        "require_unused_project",
        Mock(side_effect=SmokeError("collision") if fault == "preflight" else None),
    )
    monkeypatch.setattr(stack, "diagnostics", Mock())
    cleanup = Mock(side_effect=SmokeError("cannot remove volume") if fault == "cleanup" else None)
    monkeypatch.setattr(stack, "cleanup", cleanup)

    def exercise(*args: object) -> None:
        if fault == "exercise":
            raise SmokeError("unready API")

    monkeypatch.setattr("scripts.smoke_stack.exercise", exercise)
    result = run(argparse.Namespace(artifacts=tmp_path, keep=False, inject_failure=None))
    report = json.loads((stack.artifacts / "result.json").read_text())
    assert result == (0 if fault is None else 1)
    assert report["status"] == ("passed" if fault is None else "failed")
    assert cleanup.call_count == (0 if fault == "preflight" else 1)
    if fault == "exercise":
        assert "unready API" in report["error"]
        assert report["cleanup"] == "completed"
    if fault == "cleanup":
        assert "cannot remove volume" in report["cleanup"]


def test_command_timeout_preserves_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    stack = Stack(tmp_path)
    monkeypatch.setattr(
        "scripts.smoke_stack.subprocess.run",
        Mock(side_effect=subprocess.TimeoutExpired("docker", 1, output=b"partial build output")),
    )
    with pytest.raises(SmokeError, match="exceeded 1s"):
        stack.command("build", timeout=1)
    assert "partial build output" in (stack.artifacts / "commands.log").read_text()
