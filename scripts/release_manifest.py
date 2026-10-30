"""Record source identity and checksums for a local candidate evidence directory."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def artifact_hashes(directory: Path) -> list[dict[str, Any]]:
    """Hash regular artifacts, excluding this manifest and external symlink targets."""
    files = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.is_symlink() or path.name == "manifest.json":
            continue
        if not path.resolve().is_relative_to(directory.resolve()):
            raise ValueError(f"Artifact escapes evidence directory: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        files.append(
            {
                "path": path.relative_to(directory).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": digest.hexdigest(),
            }
        )
    return files


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, default=ROOT / "test-results" / "rc")
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)

    def git(*arguments: str) -> str:
        return subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT.as_posix()}", *arguments],
            cwd=ROOT,
            text=True,
            timeout=30,
        ).strip()

    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    web = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))
    result = {
        "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
        "revision": git("rev-parse", "HEAD"),
        "working_tree_clean": not bool(git("status", "--porcelain")),
        "python": sys.version,
        "platform": platform.platform(),
        "package_versions": {"python": project["tool"]["poetry"]["version"], "web": web["version"]},
        "lockfiles": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("poetry.lock", "web/yarn.lock")
        },
        "artifacts": artifact_hashes(args.artifacts),
    }
    output = args.artifacts / "manifest.json"
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output}; clean source: {result['working_tree_clean']}")


if __name__ == "__main__":
    main()
