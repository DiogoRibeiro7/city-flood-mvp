"""Run a synthetic backup/restore and worker recovery drill in owned disposable Compose resources."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import signal
import subprocess
import time
import urllib.parse
from pathlib import Path
from typing import Any

from scripts.smoke_fixture import CITY_ID, END, RAIN_ID, START, fixture_digest
from scripts.smoke_stack import (
    ROOT,
    SmokeError,
    Stack,
    json_request,
    positive_seconds,
    request,
    verify_csv,
    wait_for,
)

DATABASES = {"db": "test_recovery_source", "restored-db": "test_recovery_restored"}
SERVICES = {*DATABASES, "backend", "recovered-api", "interrupted-worker", "retry-worker"}
TARGETS = {"database_rto_seconds": 14400, "rpo_exposure_seconds": 900, "worker_rto_seconds": 300}


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n"
    )


def archive_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_archive(path: Path, expected: str) -> None:
    if archive_digest(path) != expected:
        raise SmokeError("Backup archive checksum mismatch; restore refused")


def compare_snapshots(source: dict[str, Any], restored: dict[str, Any]) -> None:
    if source != restored:
        raise SmokeError(
            "Restored application rows, schema, migration or extension versions differ"
        )


def compare_target(seconds: float, target: int) -> dict[str, Any]:
    return {
        "measured_seconds": round(seconds, 6),
        "proposed_target_seconds": target,
        "within_candidate_in_this_drill": seconds <= target,
    }


class RecoveryStack(Stack):
    def __init__(self, artifacts: Path) -> None:
        super().__init__(
            artifacts, compose_file=ROOT / "docker-compose.recovery.yml", purpose="recovery"
        )

    def owned_container(self, service: str) -> str:
        """Resolve one full ID and verify both project and service before a fault or DB command."""
        if service not in SERVICES:
            raise SmokeError("Unknown recovery service")
        container = self.command("ps", "--all", "-q", service).stdout.strip()
        if re.fullmatch(r"[a-f0-9]{64}", container) is None:
            raise SmokeError("Expected exactly one full recovery container ID")
        identity = self.command(
            "inspect",
            "--format",
            '{{.Id}}|{{index .Config.Labels "com.docker.compose.project"}}|{{index .Config.Labels "com.docker.compose.service"}}',
            container,
            docker=True,
        ).stdout.strip()
        if identity != f"{container}|{self.project}|{service}":
            raise SmokeError("Recovery container ownership mismatch; action refused")
        return container

    def database(self, service: str, program: str, *args: str, timeout: float = 120) -> str:
        if service not in DATABASES or program not in {"psql", "pg_dump", "pg_restore"}:
            raise SmokeError("Unknown recovery database command")
        container = self.owned_container(service)
        options = ["-X", "-v", "ON_ERROR_STOP=1", "-At"] if program == "psql" else []
        return self.command(
            "exec",
            container,
            program,
            "-U",
            "postgres",
            "-d",
            DATABASES[service],
            *options,
            *args,
            docker=True,
            timeout=timeout,
        ).stdout.strip()

    def probe(self, target: str, action: str) -> dict[str, Any]:
        service = "backend" if target == "source" else "recovered-api"
        result = self.command(
            "run",
            "--rm",
            "--no-deps",
            service,
            "python",
            "-m",
            "scripts.recovery_probe",
            "--target",
            target,
            action,
            timeout=120,
        )
        return dict(json.loads(result.stdout.strip().splitlines()[-1]))

    def cleanup(self) -> None:
        # Refuse removal if any named container no longer belongs to this run.
        for service in SERVICES:
            if self.command("ps", "--all", "-q", service).stdout.strip():
                self.owned_container(service)
        self.command("down", "--volumes", "--remove-orphans", timeout=120)
        self.require_unused_project()
        if (
            self.command(
                "image", "inspect", f"{self.project}-backend", docker=True, check=False
            ).returncode
            == 0
        ):
            self.command("image", "rm", f"{self.project}-backend", docker=True)


def exercise(stack: RecoveryStack, args: argparse.Namespace, report: dict[str, Any]) -> None:
    def phase(name: str) -> None:
        report["phase"] = name
        print(f"[{name}] {stack.project}", flush=True)

    def save(name: str, value: Any) -> None:
        write_json(stack.artifacts / name, value)

    phase("build")
    stack.command("build", "backend", timeout=args.build_timeout)
    phase("databases")
    stack.command("up", "-d", "--no-build", "db", "restored-db")
    for service, database in DATABASES.items():

        def database_ready(service: str = service, database: str = database) -> int:
            return stack.command(
                "exec",
                "-T",
                service,
                "pg_isready",
                "-h",
                "127.0.0.1",
                "-U",
                "postgres",
                "-d",
                database,
                check=False,
                timeout=10,
            ).returncode

        wait_for(
            f"{service} TCP readiness",
            database_ready,
            lambda code: code == 0,
            args.timeout,
        )
        stack.owned_container(service)
    report["database_images"] = {
        service: stack.command(
            "inspect", "--format", "{{.Image}}", stack.owned_container(service), docker=True
        ).stdout.strip()
        for service in DATABASES
    }
    if len(set(report["database_images"].values())) != 1:
        raise SmokeError("Source and restore database images differ")
    phase("seed")
    stack.command("run", "--rm", "--no-deps", "backend", "alembic", "upgrade", "head")
    report["fixture"] = stack.probe("source", "seed")
    checkpoint_started = time.monotonic()
    report["checkpoint_action_started_at"] = dt.datetime.now(dt.UTC).isoformat()
    report["checkpoint"] = stack.probe("source", "checkpoint")
    source = stack.probe("source", "snapshot")
    save("source-snapshot.json", source)
    report["source_snapshot_sha256"] = source["sha256"]
    report["migration_head"] = source["migration_head"]
    report["postgres_version"] = source["postgres_version"]
    report["extensions"] = source["schema"]["extensions"]
    phase("backup")
    started = time.monotonic()
    stack.database(
        "db", "pg_dump", "--format=custom", "--no-owner", "--no-acl", "--file=/tmp/recovery.dump"
    )
    report["backup_seconds"] = round(time.monotonic() - started, 6)
    archive = stack.artifacts / "backup.dump"
    source_id = stack.owned_container("db")
    expected = stack.command(
        "exec", source_id, "sha256sum", "/tmp/recovery.dump", docker=True
    ).stdout.split()[0]
    stack.command("cp", f"{source_id}:/tmp/recovery.dump", str(archive), docker=True)
    report["archive"] = {
        "sha256": expected,
        "bytes": archive.stat().st_size,
        "format": "pg_dump custom",
    }
    phase("archive_integrity")
    if args.inject_failure == "corrupt-backup":
        # Only the new run's local artifact is modified; no database archive is overwritten.
        if archive.resolve().parent != stack.artifacts:
            raise SmokeError("Corruption fixture escaped its artifact directory")
        with archive.open("r+b") as stream:
            first = stream.read(1)
            stream.seek(0)
            stream.write(bytes([first[0] ^ 1]))
    verify_archive(archive, expected)
    report["post_backup_write"] = stack.probe("source", "post-backup")
    phase("source_outage")
    outage_started = time.monotonic()
    report["fault_declared_at"] = dt.datetime.now(dt.UTC).isoformat()
    report["rpo_exposure_upper_bound"] = compare_target(
        outage_started - checkpoint_started, TARGETS["rpo_exposure_seconds"]
    )
    source_id = stack.owned_container("db")
    stack.command("stop", "--time", "2", source_id, docker=True)
    if (
        stack.command(
            "inspect", "--format", "{{.State.Running}}", source_id, docker=True
        ).stdout.strip()
        != "false"
    ):
        raise SmokeError("Source database did not stop")
    phase("restore")
    stack.probe("restored", "require-empty")
    target_id = stack.owned_container("restored-db")
    stack.command("cp", str(archive), f"{target_id}:/tmp/recovery.dump", docker=True)
    transferred = stack.command(
        "exec", target_id, "sha256sum", "/tmp/recovery.dump", docker=True
    ).stdout.split()[0]
    if transferred != expected:
        raise SmokeError("Transferred archive checksum mismatch")
    stack.database("restored-db", "psql", "-c", "SELECT timescaledb_pre_restore()")
    started = time.monotonic()
    stack.database(
        "restored-db",
        "pg_restore",
        "--exit-on-error",
        "--no-owner",
        "--no-acl",
        "/tmp/recovery.dump",
    )
    stack.database("restored-db", "psql", "-c", "SELECT timescaledb_post_restore()")
    report["restore_command_seconds"] = round(time.monotonic() - started, 6)
    restored = stack.probe("restored", "snapshot")
    save("restored-snapshot.json", restored)
    compare_snapshots(source, restored)
    report["restored_snapshot_sha256"] = restored["sha256"]
    report["snapshot_match"] = True
    report["observed_data_loss"] = {
        "post_backup_observations_missing": 1,
        "pre_backup_observations_restored": restored["tables"]["telemetry_observation"]["rows"],
        "interpretation": "One deliberately committed post-backup observation is absent; no WAL replay was performed.",
    }
    phase("restored_api")
    stack.command("up", "-d", "--no-build", "recovered-api")
    api = stack.base_url("recovered-api", 8000)
    wait_for(
        "restored API health",
        lambda: json_request(f"{api}/v1/health"),
        lambda value: value == {"status": "ok"},
        args.timeout,
    )
    cities = json_request(f"{api}/v1/cities")
    if [city["city_id"] for city in cities] != [CITY_ID]:
        raise SmokeError("Restored API did not return the fixture city")
    observations = json_request(
        f"{api}/v1/assets/{RAIN_ID}/observations?"
        + urllib.parse.urlencode(
            {
                "metric": "rain_mmph",
                "from": START.isoformat(),
                "to": END.isoformat(),
                "granularity": "1m",
            }
        )
    )
    if len(observations["series"]) != 12:
        raise SmokeError("Restored API did not expose all fixture rainfall observations")
    report["database_recovery"] = compare_target(
        time.monotonic() - outage_started, TARGETS["database_rto_seconds"]
    )
    report["database_recovery"]["scope"] = (
        "Source-stop request through restore, equality checks and restored API data read; destination server pre-provisioned."
    )
    phase("worker_interruption")
    stack.command("up", "-d", "--no-build", "interrupted-worker")
    worker_id = stack.owned_container("interrupted-worker")
    marker = wait_for(
        "worker claimed the recovered export",
        lambda: stack.command(
            "exec", worker_id, "cat", "/tmp/recovery-worker-entered.json", docker=True, check=False
        ),
        lambda result: result.returncode == 0,
        args.timeout,
    )
    if json.loads(marker.stdout)["export_id"] != report["fixture"]["export_id"]:
        raise SmokeError("Paused worker claimed an unexpected job")
    active = stack.probe("restored", "job-state")
    if (
        active["lock_available"]
        or active["status"] != "queued"
        or active["backlog"]["oldest_export_age_seconds"] <= 300
    ):
        raise SmokeError("Failed to detect aged unfinished work and the active transaction lock")
    report["active_worker_probe"] = active
    fault_started = time.monotonic()
    worker_id = stack.owned_container("interrupted-worker")
    stack.command("kill", "--signal", "KILL", worker_id, docker=True)
    exit_code = stack.command(
        "inspect", "--format", "{{.State.ExitCode}}", worker_id, docker=True
    ).stdout.strip()
    if exit_code != "137":
        raise SmokeError("Interrupted worker did not exit from SIGKILL")
    rolled_back = wait_for(
        "worker transaction rollback",
        lambda: stack.probe("restored", "job-state"),
        lambda state: state["lock_available"] and state["status"] == "queued",
        args.timeout,
    )
    if rolled_back["attempts"] != 0 or not rolled_back["lock_metadata_cleared"]:
        raise SmokeError("Killed worker claim did not roll back cleanly")
    report["killed_worker"] = {"exit_code": 137, "rollback_state": rolled_back}
    # Restart the SAME container. Its private marker skips the pause on its second process.
    stack.command("start", stack.owned_container("interrupted-worker"), docker=True)
    restored_job = wait_for(
        "restarted worker completion",
        lambda: stack.probe("restored", "job-state"),
        lambda state: state["status"] == "completed",
        args.timeout,
    )
    if restored_job["attempts"] != 1 or not restored_job["lock_metadata_cleared"]:
        raise SmokeError("Recovered job did not have exactly one committed attempt")
    csv = request(f"{api}/v1/analytics/jobs/{report['fixture']['export_id']}/download")
    verify_csv(csv)
    (stack.artifacts / "recovered-export.csv").write_text(csv, encoding="utf-8", newline="\n")
    report["worker_recovery"] = compare_target(
        time.monotonic() - fault_started, TARGETS["worker_rto_seconds"]
    )
    report["worker_recovery"]["scope"] = (
        "SIGKILL request through rollback, same-container restart and exact CSV download verification."
    )
    report["worker_recovery"]["completed_job"] = restored_job
    phase("retry")
    retry_started = time.monotonic()
    report["retry_first_attempt"] = stack.probe("restored", "retry-first")
    wait_for(
        "retry backoff eligibility",
        lambda: stack.probe("restored", "retry-state"),
        lambda state: state["due"],
        args.timeout,
    )
    stack.command("run", "--rm", "--no-deps", "retry-worker")
    retried = stack.probe("restored", "retry-state")
    if (
        retried["status"] != "completed"
        or retried["attempts"] != 2
        or retried["has_error"]
        or not retried["lock_metadata_cleared"]
    ):
        raise SmokeError("Automatic retry did not complete on its second committed attempt")
    verify_csv(request(f"{api}/v1/analytics/jobs/{retried['export_id']}/download"))
    report["retry_recovery"] = compare_target(
        time.monotonic() - retry_started, TARGETS["worker_rto_seconds"]
    )
    report["retry_recovery"]["completed_job"] = retried
    phase("stale_running_detection")
    stale = stack.probe("restored", "stale-running")
    if stale["oldest_export_age_seconds"] <= 300 or stale["automatically_requeued"]:
        raise SmokeError("Stale running fixture was not detected without mutation")
    report["stale_running_probe"] = stale
    report["limitations"] = [
        "Synthetic tiny workload; local measurements do not establish production RTO/RPO.",
        "Logical backup only: no PITR, WAL shipping, off-site storage, role/ACL recovery or external export-store restoration.",
        "Stale timestamps are controlled fixtures; alert hold duration and operator notification were not exercised.",
        "No automatic stale-job requeue; worker claim rollback does not guarantee exactly-once external side effects.",
    ]


def run(args: argparse.Namespace) -> int:
    stack = RecoveryStack(args.artifacts)
    report: dict[str, Any] = {
        "schema_version": 1,
        "project": stack.project,
        "status": "failed",
        "phase": "preflight",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "proposed_targets": TARGETS,
        "fixture_sha256": fixture_digest(),
        "injected_failure": args.inject_failure,
        "cleanup": "not started",
    }
    print(f"Artifacts: {stack.artifacts}", flush=True)
    owned = False
    started = time.monotonic()
    try:
        report["code_revision"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
        report["code_dirty"] = bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        )
        stack.command("version", docker=True)
        stack.require_unused_project()
        if (
            stack.command(
                "image", "inspect", f"{stack.project}-backend", docker=True, check=False
            ).returncode
            == 0
        ):
            raise SmokeError("Refusing to replace an existing recovery image tag")
        owned = True
        exercise(stack, args, report)
        report["status"] = "passed"
    except (Exception, KeyboardInterrupt) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED at {report['phase']}: {report['error']}", flush=True)
    finally:
        if owned:
            stack.diagnostics()
            try:
                stack.cleanup()
                report["cleanup"] = "completed"
            except Exception as exc:
                report.update(status="failed", cleanup=f"failed: {exc}")
        report["elapsed_seconds"] = round(time.monotonic() - started, 6)
        report["completed_at"] = dt.datetime.now(dt.UTC).isoformat()
        write_json(stack.artifacts / "result.json", report)
    print(f"{report['status'].upper()}: {stack.artifacts / 'result.json'}", flush=True)
    return 0 if report["status"] == "passed" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=ROOT / "test-results/recovery")
    parser.add_argument("--timeout", type=positive_seconds, default=120)
    parser.add_argument("--build-timeout", type=positive_seconds, default=1200)
    parser.add_argument("--inject-failure", choices=("corrupt-backup",))

    def interrupted(signum: int, frame: object) -> None:
        raise KeyboardInterrupt(f"Received signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
