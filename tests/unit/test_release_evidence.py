from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from floodmvp.api.main import app
from scripts.release_manifest import ROOT, artifact_hashes


def test_release_versions_agree() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    web = json.loads((ROOT / "web/package.json").read_text(encoding="utf-8"))
    # Python spells the planned 0.9.0-rc1 release as 0.9.0rc1 (PEP 440).
    assert project["tool"]["poetry"]["version"] == web["version"].replace("-rc", "rc")
    assert app.version == web["version"]


def test_evidence_hashes_detect_changes_and_ignore_their_own_manifest(tmp_path: Path) -> None:
    (tmp_path / "nested").mkdir()
    report = tmp_path / "nested" / "result.txt"
    report.write_bytes(b"passed")
    (tmp_path / "manifest.json").write_text("old report", encoding="utf-8")
    before = artifact_hashes(tmp_path)
    assert before == [
        {
            "path": "nested/result.txt",
            "bytes": 6,
            "sha256": hashlib.sha256(b"passed").hexdigest(),
        }
    ]
    report.write_bytes(b"failed")
    assert artifact_hashes(tmp_path)[0]["sha256"] != before[0]["sha256"]
