from __future__ import annotations

import argparse
import copy
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
import yaml

from scripts.recovery_drill import (
    RecoveryStack,
    archive_digest,
    compare_snapshots,
    compare_target,
    run,
    verify_archive,
)
from scripts.recovery_probe import main, require_recovery_database
from scripts.smoke_stack import ROOT, SmokeError

PROJECT = "city-flood-recovery-012345abcdef"
SOURCE = "postgresql+asyncpg://postgres:recovery-test-only@db:5432/test_recovery_source"
RESTORED = SOURCE.replace("@db:", "@restored-db:").replace("_source", "_restored")


@pytest.mark.parametrize(("target", "url"), [("source", SOURCE), ("restored", RESTORED)])
def test_exact_owned_database_targets_are_accepted(target: str, url: str) -> None:
    require_recovery_database(url, "test", PROJECT, target)


@pytest.mark.parametrize(
    ("url", "app_env", "project", "target"),
    [
        (SOURCE.replace("test_recovery_source", "floodmvp"), "test", PROJECT, "source"),
        (SOURCE.replace("@db:", "@production:"), "test", PROJECT, "source"),
        (SOURCE.replace(":5432", ":6432"), "test", PROJECT, "source"),
        (SOURCE.replace("postgres:", "app:"), "test", PROJECT, "source"),
        (SOURCE.replace("+asyncpg", ""), "test", PROJECT, "source"),
        (SOURCE + "?dbname=production", "test", PROJECT, "source"),
        (SOURCE, "prod", PROJECT, "source"),
        (SOURCE, "test", "city-flood-smoke-012345abcdef", "source"),
        (SOURCE, "test", "", "source"),
        (SOURCE, "test", PROJECT, "restored"),
        (SOURCE, "test", PROJECT, "unknown"),
    ],
)
def test_database_guards_reject_target_overrides(
    url: str, app_env: str, project: str, target: str
) -> None:
    with pytest.raises(ValueError):
        require_recovery_database(url, app_env, project, target)


@pytest.mark.parametrize(
    ("url", "target", "action"),
    [
        (SOURCE, "source", "stale-running"),
        (RESTORED, "restored", "seed"),
        (SOURCE.replace("@db:", "@production:"), "source", "seed"),
    ],
)
async def test_refusal_happens_before_connecting(
    url: str, target: str, action: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in {"DATABASE_URL": url, "APP_ENV": "test", "SMOKE_PROJECT": PROJECT}.items():
        monkeypatch.setenv(key, value)
    engine = Mock()
    monkeypatch.setattr("scripts.recovery_probe.create_async_engine", engine)
    with pytest.raises(ValueError):
        await main(target, action)
    engine.assert_not_called()


def test_compose_isolates_databases_and_ignores_host_application_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://real@production/application")
    monkeypatch.setenv("COMPOSE_FILE", "production.yml")
    monkeypatch.setenv("COMPOSE_PROJECT_NAME", "production")
    stack = RecoveryStack(tmp_path)
    assert stack.compose[-1] == str(ROOT / "docker-compose.recovery.yml")
    assert stack.project.startswith("city-flood-recovery-")
    assert not any(key.startswith("COMPOSE_") for key in stack.env)
    config = yaml.safe_load((ROOT / "docker-compose.recovery.yml").read_text())
    services = config["services"]
    assert services["backend"]["environment"]["DATABASE_URL"] == SOURCE
    for name in ("recovered-api", "interrupted-worker", "retry-worker"):
        assert services[name]["environment"]["DATABASE_URL"] == RESTORED
    for name in ("db", "restored-db"):
        assert "ports" not in services[name]
    assert services["db"]["volumes"][0] != services["restored-db"]["volumes"][0]
    assert services["recovered-api"]["ports"] == ["127.0.0.1::8000"]
    assert not any(volume.get("external") for volume in config["volumes"].values() if volume)


def test_database_command_refuses_container_with_foreign_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = RecoveryStack(tmp_path)
    container = "a" * 64
    command = Mock(
        side_effect=[
            subprocess.CompletedProcess([], 0, container, ""),
            subprocess.CompletedProcess([], 0, f"{container}|production|db", ""),
        ]
    )
    monkeypatch.setattr(stack, "command", command)
    with pytest.raises(SmokeError, match="ownership mismatch"):
        stack.database("db", "psql", "-c", "SELECT 1")
    assert command.call_count == 2
    assert all(call.args[0] != "exec" for call in command.call_args_list)


def test_corrupted_backup_is_rejected_before_restore(tmp_path: Path) -> None:
    archive = tmp_path / "backup.dump"
    archive.write_bytes(b"PGDMP synthetic archive")
    expected = archive_digest(archive)
    verify_archive(archive, expected)
    archive.write_bytes(b"corrupted archive")
    with pytest.raises(SmokeError, match="checksum mismatch; restore refused"):
        verify_archive(archive, expected)


@pytest.mark.parametrize("changed", ["rows", "schema", "migration_head"])
def test_restore_rejects_data_or_schema_drift(changed: str) -> None:
    source = {"rows": {"city": "hash"}, "schema": {"constraints": []}, "migration_head": "0018"}
    restored = copy.deepcopy(source)
    compare_snapshots(source, restored)
    restored[changed] = "different"
    with pytest.raises(SmokeError, match="differ"):
        compare_snapshots(source, restored)


def test_target_comparison_does_not_round_a_miss_into_a_pass() -> None:
    assert compare_target(900, 900)["within_candidate_in_this_drill"]
    assert not compare_target(900.0000001, 900)["within_candidate_in_this_drill"]


@pytest.mark.parametrize("fault", ["preflight", "image_collision", "exercise", "cleanup", None])
def test_failures_record_evidence_and_cleanup_only_owned_resources(
    fault: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stack = RecoveryStack(tmp_path)
    monkeypatch.setattr("scripts.recovery_drill.RecoveryStack", lambda artifacts: stack)

    def command(*args: str, **kwargs: object) -> subprocess.CompletedProcess[str]:
        code = 1 if args[:2] == ("image", "inspect") and fault != "image_collision" else 0
        return subprocess.CompletedProcess([], code, "", "")

    monkeypatch.setattr(stack, "command", command)
    monkeypatch.setattr(
        stack,
        "require_unused_project",
        Mock(side_effect=SmokeError("project collision") if fault == "preflight" else None),
    )
    monkeypatch.setattr(stack, "diagnostics", Mock())
    cleanup = Mock(side_effect=SmokeError("cleanup failed") if fault == "cleanup" else None)
    monkeypatch.setattr(stack, "cleanup", cleanup)
    monkeypatch.setattr(
        "scripts.recovery_drill.exercise",
        Mock(side_effect=SmokeError("restore failed") if fault == "exercise" else None),
    )
    result = run(argparse.Namespace(artifacts=tmp_path, inject_failure=None))
    report = json.loads((stack.artifacts / "result.json").read_text())
    assert result == (0 if fault is None else 1)
    assert report["status"] == ("passed" if fault is None else "failed")
    assert cleanup.call_count == (0 if fault in {"preflight", "image_collision"} else 1)
    if fault == "exercise":
        assert "restore failed" in report["error"]
        assert report["cleanup"] == "completed"
    if fault == "cleanup":
        assert "cleanup failed" in report["cleanup"]
