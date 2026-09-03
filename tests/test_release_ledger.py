# Requirement: REQ-20260902-172713

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "release_ledger",
    ROOT / "scripts/release_ledger.py",
)
release_ledger = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(release_ledger)


def _release_root(tmp_path: Path, version: str = "1.2.4") -> tuple[Path, Path]:
    root = tmp_path / "repo"
    for relative in release_ledger.SOURCE_INPUTS:
        path = root / relative
        if Path(relative).suffix or relative == "VERSION":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                version if relative == "VERSION" else f"content:{relative}",
                encoding="utf-8",
            )
        else:
            path.mkdir(parents=True, exist_ok=True)
            (path / "asset.txt").write_text(relative, encoding="utf-8")
    ledger = root / "deploy/release-ledger.json"
    ledger.write_text(json.dumps({
        "schema_version": 1,
        "releases": [{
            "version": "1.2.3",
            "source_sha256": None,
            "status": "candidate",
            "builds": [{
                "artifact_sha256": "a" * 64,
                "built_at": "2026-09-01T00:00:00+08:00",
            }],
        }],
    }), encoding="utf-8")
    return root, ledger


def test_newer_version_passes_and_same_version_changed_source_fails(tmp_path: Path):
    root, ledger = _release_root(tmp_path)

    check = release_ledger.preflight(root, ledger)
    assert check["mode"] == "new"
    assert check["version"] == "1.2.4"

    payload = release_ledger.load_ledger(ledger)
    payload["releases"].append({
        "version": "1.2.4",
        "source_sha256": "b" * 64,
        "status": "candidate",
        "builds": [{
            "artifact_sha256": "c" * 64,
            "built_at": "2026-09-02T00:00:00+08:00",
        }],
    })
    ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(release_ledger.ReleaseLedgerError, match="已用于其他源码"):
        release_ledger.preflight(root, ledger)


def test_same_version_same_source_allows_rebuild(tmp_path: Path):
    root, ledger = _release_root(tmp_path)
    fingerprint = release_ledger.source_fingerprint(root)
    payload = release_ledger.load_ledger(ledger)
    payload["releases"].append({
        "version": "1.2.4",
        "source_sha256": fingerprint,
        "status": "candidate",
        "builds": [{
            "artifact_sha256": "c" * 64,
            "built_at": "2026-09-02T00:00:00+08:00",
        }],
    })
    ledger.write_text(json.dumps(payload), encoding="utf-8")

    assert release_ledger.preflight(root, ledger)["mode"] == "rebuild"


def test_build_record_and_explicit_fnos_verification_are_separate(tmp_path: Path):
    root, ledger = _release_root(tmp_path)
    artifact = tmp_path / "nas-media-importer.fpk"
    artifact.write_bytes(b"candidate-package")

    recorded = release_ledger.record_build(root, ledger, artifact)
    before_verification = release_ledger.status(root, ledger)

    assert recorded["version"] == "1.2.4"
    assert before_verification == {
        "current_version": "1.2.4",
        "latest_candidate": "1.2.4",
        "latest_verified": None,
    }

    release_ledger.mark_verified(ledger, "1.2.4", "fnOS 安装与任务验证通过")
    assert release_ledger.status(root, ledger)["latest_verified"] == "1.2.4"


def test_ledger_rejects_non_monotonic_or_duplicate_versions(tmp_path: Path):
    _root, ledger = _release_root(tmp_path)
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["releases"].append(dict(payload["releases"][0]))
    ledger.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(release_ledger.ReleaseLedgerError, match="严格递增"):
        release_ledger.load_ledger(ledger)
