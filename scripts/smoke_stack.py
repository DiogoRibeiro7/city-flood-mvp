"""Run the complete demo stack in a disposable Docker Compose project.

Usage: python -m scripts.smoke_stack (Python 3.12+ and Docker Compose required).
Host-side orchestration uses only the standard library, never application .env.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import re
import shlex
import signal
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.smoke_fixture import (
    CITY_ID,
    END,
    FIXTURE_VERSION,
    RAIN_ID,
    RAIN_VALUES,
    START,
    fixture_digest,
)

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.smoke.yml"


class SmokeError(RuntimeError):
    """An actionable smoke assertion or orchestration failure."""


def wait_for[T](
    description: str,
    probe: Callable[[], T],
    ready: Callable[[T], bool],
    timeout: float,
    *,
    interval: float = 1.0,
) -> T:
    """Poll to a deadline, preserving the last response or transport error."""
    deadline = time.monotonic() + timeout
    last: object = "no response"
    while True:
        try:
            result = probe()
            last = result
            if ready(result):
                return result
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = str(exc)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise SmokeError(
                f"Timed out waiting for {description}; last response: {str(last)[:800]}"
            )
        time.sleep(min(interval, remaining))


def request(url: str, body: dict[str, Any] | None = None) -> str:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    # Ignore host proxy settings for the runner's loopback-only services.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=5) as response:
        return str(response.read().decode("utf-8"))


def json_request(url: str, body: dict[str, Any] | None = None) -> Any:
    return json.loads(request(url, body))


def job_completed(job: dict[str, Any]) -> bool:
    if job.get("status") in {"failed", "cancelled"}:
        raise SmokeError(f"Queued job reached unsuccessful terminal state: {job}")
    return job.get("status") == "completed"


def verify_csv(content: str) -> None:
    rows = list(csv.DictReader(io.StringIO(content)))
    expected = [
        (RAIN_ID, "rain_mmph", START + dt.timedelta(minutes=5 * index), value)
        for index, value in enumerate(RAIN_VALUES)
    ]
    try:
        actual = [
            (
                row["asset_id"],
                row["metric"],
                dt.datetime.fromisoformat(row["ts"].replace("Z", "+00:00")),
                float(row["value"]),
            )
            for row in rows
        ]
    except (KeyError, ValueError) as exc:
        raise SmokeError("Export CSV has invalid columns or measurements") from exc
    if actual != expected:
        raise SmokeError(
            f"Export CSV differs from the fixture: expected 12 exact rows, got {actual}"
        )


class Stack:
    def __init__(self, artifacts: Path) -> None:
        self.project = f"city-flood-smoke-{uuid.uuid4().hex[:12]}"
        self.artifacts = artifacts.resolve() / self.project
        self.artifacts.mkdir(parents=True, exist_ok=False)
        self.env_file = self.artifacts / "compose.env"
        self.env = {
            key: value for key, value in os.environ.items() if not key.startswith("COMPOSE_")
        }
        self.env["SMOKE_PROJECT"] = self.project
        self.configure_api("http://127.0.0.1:1")
        self.compose = [
            "docker",
            "compose",
            "--project-directory",
            str(ROOT),
            "--env-file",
            str(self.env_file),
            "-p",
            self.project,
            "-f",
            str(COMPOSE),
        ]

    def configure_api(self, base: str) -> None:
        self.env["SMOKE_API_BASE"] = base
        self.env_file.write_text(
            f"SMOKE_PROJECT={self.project}\nSMOKE_API_BASE={base}\n", encoding="utf-8"
        )

    def command(
        self, *args: str, timeout: float = 120, check: bool = True, docker: bool = False
    ) -> subprocess.CompletedProcess[str]:
        argv = (["docker"] if docker else self.compose) + list(args)
        with (self.artifacts / "commands.log").open("a", encoding="utf-8") as log:
            log.write(f"\n$ {shlex.join(argv)}\n")
            log.flush()
            try:
                result = subprocess.run(
                    argv,
                    cwd=ROOT,
                    env=self.env,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                for output in (exc.stdout, exc.stderr):
                    if output:
                        log.write(
                            output.decode(errors="replace") if isinstance(output, bytes) else output
                        )
                raise SmokeError(f"Command exceeded {timeout:g}s: {shlex.join(argv)}") from exc
            log.write(result.stdout + result.stderr)
            log.write(f"\nexit_code={result.returncode}\n")
        if check and result.returncode:
            raise SmokeError(
                f"Command exited {result.returncode}: {shlex.join(argv)}\n"
                f"{(result.stdout + result.stderr)[-3000:]}"
            )
        return result

    def require_unused_project(self) -> None:
        for resource in ("container", "volume", "network"):
            options = ["--all"] if resource == "container" else []
            existing = self.command(
                resource,
                "ls",
                "-q",
                *options,
                "--filter",
                f"label=com.docker.compose.project={self.project}",
                docker=True,
            )
            if existing.stdout.strip():
                raise SmokeError(f"Refusing to reuse an existing Compose project: {self.project}")

    def base_url(self, service: str, port: int) -> str:
        address = self.command("port", service, str(port)).stdout.strip()
        if re.fullmatch(r"127\.0\.0\.1:\d+", address) is None:
            raise SmokeError(f"Expected one loopback-only binding for {service}, got {address!r}")
        return f"http://{address}"

    def diagnostics(self) -> None:
        for args, filename in (
            (("ps", "--all", "--format", "json"), "services.json"),
            (("logs", "--no-color", "--tail", "200"), "services.log"),
            (("images", "--format", "json"), "images.json"),
        ):
            try:
                result = self.command(*args, timeout=30, check=False)
                (self.artifacts / filename).write_text(
                    result.stdout + result.stderr, encoding="utf-8"
                )
            except Exception as exc:
                print(f"Could not collect {filename}: {exc}", flush=True)

    def cleanup(self) -> None:
        self.command("down", "--volumes", "--remove-orphans", timeout=120)
        # Remove only this run's two image tags, retaining shared base-image caches.
        for service in ("backend", "web"):
            self.command("image", "rm", f"{self.project}-{service}", docker=True, check=False)


def exercise(stack: Stack, args: argparse.Namespace, report: dict[str, Any]) -> None:
    def phase(name: str) -> None:
        report["phase"] = name
        print(f"[{name}] {stack.project}", flush=True)

    phase("build")
    stack.command("build", "backend", "web", timeout=args.build_timeout)
    phase("database")
    stack.command("up", "-d", "--no-build", "db")
    wait_for(
        "database readiness",
        lambda: (
            stack.command(
                "exec",
                "-T",
                "db",
                "pg_isready",
                "-U",
                "postgres",
                "-d",
                "floodmvp_smoke_test",
                timeout=10,
                check=False,
            ).returncode
        ),
        lambda code: code == 0,
        args.timeout,
    )
    phase("migrations")
    stack.command("run", "--rm", "--no-deps", "backend", "alembic", "upgrade", "head")
    phase("seed")
    for options in ([], ["--analytics"]):
        result = stack.command(
            "run", "--rm", "--no-deps", "backend", "python", "-m", "scripts.seed_smoke", *options
        )
        seeded = json.loads(result.stdout.strip().splitlines()[-1])
        expected = {"cities": 1, "assets": 3, "observations": 36, "sha256": fixture_digest()}
        if any(seeded.get(key) != value for key, value in expected.items()):
            raise SmokeError(f"Seed/reseed verification failed: {seeded}")
        report["seed"] = seeded
    phase("readiness")
    stack.command("up", "-d", "--no-build", "backend", "worker")
    api = stack.base_url("backend", 8000)
    stack.configure_api(api)
    stack.command("up", "-d", "--no-build", "web", "prometheus", "grafana")
    web = stack.base_url("web", 5173)
    report["endpoints"] = {"api": api, "web": web}
    wait_for(
        "API health",
        lambda: json_request(f"{api}/v1/health"),
        lambda v: v == {"status": "ok"},
        args.timeout,
    )
    wait_for("web HTML", lambda: request(web), lambda v: "/src/main.tsx" in v, args.timeout)
    wait_for(
        "web API configuration",
        lambda: request(f"{web}/src/api.ts"),
        lambda v: api in v,
        args.timeout,
    )
    prom = stack.base_url("prometheus", 9090)
    grafana = stack.base_url("grafana", 3000)
    wait_for("Prometheus readiness", lambda: request(f"{prom}/-/ready"), bool, args.timeout)
    wait_for(
        "Grafana database",
        lambda: json_request(f"{grafana}/api/health"),
        lambda v: v.get("database") == "ok",
        args.timeout,
    )
    phase("api")
    cities = json_request(f"{api}/v1/cities")
    assets = json_request(f"{api}/v1/cities/{CITY_ID}/assets")
    if [city["city_id"] for city in cities] != [CITY_ID] or len(assets) != 3:
        raise SmokeError("API did not return the one seeded city and three assets")
    query = {"from": START.isoformat(), "to": END.isoformat()}
    observations = json_request(
        f"{api}/v1/assets/{RAIN_ID}/observations?"
        + urllib.parse.urlencode({**query, "metric": "rain_mmph", "granularity": "1m"})
    )
    series = observations["series"]
    expected_series = [
        (START + dt.timedelta(minutes=5 * i), value) for i, value in enumerate(RAIN_VALUES)
    ]
    actual_series = [
        (dt.datetime.fromisoformat(row["ts"].replace("Z", "+00:00")), row["value"])
        for row in series
    ]
    if actual_series != expected_series:
        raise SmokeError("Observation API differs from the fixed synthetic rainfall series")
    events = json_request(
        f"{api}/v1/events?" + urllib.parse.urlencode({**query, "city_id": CITY_ID})
    )
    if {event["event_type"] for event in events} != {"rain", "overflow"}:
        raise SmokeError(f"Expected seeded rain and overflow events, got {events}")
    json_request(f"{api}/v1/cities/{CITY_ID}/status")
    json_request(f"{api}/v1/cities/{CITY_ID}/summary")
    report["checks"] = [
        "seed replay",
        "service readiness",
        "web API configuration",
        "API fixture",
        "analytics events",
    ]
    phase("export")
    if args.inject_failure == "worker":
        stack.command("stop", "worker")
    job = json_request(
        f"{api}/v1/analytics/jobs",
        {
            "type": "export_csv",
            "query": {
                **query,
                "asset_ids": [RAIN_ID],
                "metric": "rain_mmph",
                "granularity": "1m",
                "agg": "avg",
            },
        },
    )
    report["export_job_id"] = job["job_id"]
    job_url = f"{api}/v1/analytics/jobs/{job['job_id']}"
    completed = wait_for(
        "export job completion", lambda: json_request(job_url), job_completed, args.job_timeout
    )
    if completed.get("row_count") != 12:
        raise SmokeError(f"Export reported an unexpected row count: {completed}")
    content = request(f"{job_url}/download")
    verify_csv(content)
    (stack.artifacts / "export.csv").write_text(content, encoding="utf-8")
    report["checks"].append("worker CSV completion and exact download")
    phase("scheduler")
    # Start only after assertions over the fixed historical analytics run.
    stack.command("up", "-d", "--no-build", "scheduler")

    def scheduled() -> bool:
        jobs = json_request(f"{api}/v1/jobs/queue?job_type=analytics_run")
        return bool(jobs) and all(job_completed(item) for item in jobs)

    wait_for("scheduler analytics completion", scheduled, bool, args.job_timeout)
    report["checks"].append("scheduler enqueued analytics completed by worker")


def run(args: argparse.Namespace) -> int:
    stack = Stack(args.artifacts)
    report: dict[str, Any] = {
        "project": stack.project,
        "status": "failed",
        "phase": "preflight",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "fixture": {
            "version": FIXTURE_VERSION,
            "sha256": fixture_digest(),
            "start": START.isoformat(),
            "end": END.isoformat(),
        },
        "injected_failure": args.inject_failure,
        "cleanup": "not started",
    }
    print(f"Artifacts: {stack.artifacts}", flush=True)
    owned = False
    started = time.monotonic()
    try:
        stack.command("version", docker=True)
        stack.command("version")
        stack.require_unused_project()
        owned = True
        exercise(stack, args, report)
        report["status"] = "passed"
    except (Exception, KeyboardInterrupt) as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        print(f"FAILED at {report['phase']}: {report['error']}", flush=True)
    finally:
        if owned:
            stack.diagnostics()
            if args.keep:
                report["cleanup"] = "retained by --keep"
                print(
                    f"Cleanup: {shlex.join(stack.compose + ['down', '--volumes', '--remove-orphans'])}",
                    flush=True,
                )
            else:
                try:
                    stack.cleanup()
                    report["cleanup"] = "completed"
                except Exception as exc:
                    report["cleanup"] = f"failed: {exc}"
                    report["status"] = "failed"
                    print(f"Cleanup failed: {exc}", flush=True)
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        (stack.artifacts / "result.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
    print(f"{report['status'].upper()}: {stack.artifacts / 'result.json'}", flush=True)
    return 0 if report["status"] == "passed" else 1


def positive_seconds(value: str) -> float:
    result = float(value)
    if not 0 < result < float("inf"):
        raise argparse.ArgumentTypeError("timeout must be a positive finite number")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=ROOT / "test-results" / "smoke")
    parser.add_argument(
        "--timeout", type=positive_seconds, default=120, help="Readiness deadline per service"
    )
    parser.add_argument("--job-timeout", type=positive_seconds, default=60)
    parser.add_argument("--build-timeout", type=positive_seconds, default=1200)
    parser.add_argument(
        "--keep", action="store_true", help="Retain this run's resources for inspection"
    )
    parser.add_argument(
        "--inject-failure",
        choices=["worker"],
        help="Stop the worker before enqueueing; expect exit 1",
    )

    def interrupted(signum: int, frame: object) -> None:
        raise KeyboardInterrupt(f"Received signal {signum}")

    signal.signal(signal.SIGTERM, interrupted)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
