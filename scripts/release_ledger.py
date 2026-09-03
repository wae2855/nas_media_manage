#!/usr/bin/env python3
"""查询并维护 fnOS 候选包与真机验收版本台账。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
SOURCE_INPUTS = (
    "VERSION",
    "media_importer",
    "config.yaml.example",
    "requirements.txt",
    "deploy/requirements-fnos.lock",
    "deploy/fnos_config.py",
    "deploy/build_fpk.sh",
    "deploy/icons",
    "scripts/release_ledger.py",
    "scripts/validate_fpk.py",
)
IGNORED_NAMES = frozenset({".DS_Store", "__pycache__"})


class ReleaseLedgerError(ValueError):
    """发布台账或版本门禁不满足。"""


def parse_version(value: str) -> tuple[int, int, int]:
    version = str(value or "").strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise ReleaseLedgerError(f"无效语义版本号: {version or '<empty>'}")
    return tuple(int(part) for part in version.split("."))


def read_current_version(root: Path) -> str:
    value = (root / "VERSION").read_text(encoding="utf-8").strip()
    parse_version(value)
    return value


def _iter_source_files(root: Path):
    for relative_input in SOURCE_INPUTS:
        input_path = root / relative_input
        if not input_path.exists():
            raise ReleaseLedgerError(f"发布输入不存在: {relative_input}")
        candidates = [input_path] if input_path.is_file() else sorted(input_path.rglob("*"))
        for candidate in candidates:
            if candidate.is_dir() or any(part in IGNORED_NAMES for part in candidate.parts):
                continue
            if candidate.suffix == ".pyc":
                continue
            if candidate.is_symlink() or not candidate.is_file():
                raise ReleaseLedgerError(
                    f"发布输入包含符号链接或特殊文件: {candidate.relative_to(root)}"
                )
            yield candidate


def source_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _iter_source_files(root):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
    return digest.hexdigest()


def load_ledger(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ReleaseLedgerError(f"无法读取发布台账 {path}: {error}") from error
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ReleaseLedgerError("发布台账 schema_version 不受支持")
    releases = payload.get("releases")
    if not isinstance(releases, list):
        raise ReleaseLedgerError("发布台账 releases 必须是数组")
    previous = None
    for item in releases:
        if not isinstance(item, dict):
            raise ReleaseLedgerError("发布台账包含无效记录")
        current = parse_version(item.get("version", ""))
        if previous is not None and current <= previous:
            raise ReleaseLedgerError("发布台账版本必须严格递增且不能重复")
        previous = current
        if item.get("status") not in {"candidate", "verified"}:
            raise ReleaseLedgerError(f"版本 {item.get('version')} 的状态无效")
        source_sha = item.get("source_sha256")
        if source_sha is not None and not HASH_PATTERN.fullmatch(str(source_sha)):
            raise ReleaseLedgerError(f"版本 {item.get('version')} 的源码指纹无效")
        builds = item.get("builds")
        if not isinstance(builds, list) or not builds:
            raise ReleaseLedgerError(f"版本 {item.get('version')} 缺少候选包记录")
        for build in builds:
            if not HASH_PATTERN.fullmatch(str(build.get("artifact_sha256", ""))):
                raise ReleaseLedgerError(f"版本 {item.get('version')} 的候选包哈希无效")
        if item.get("status") == "verified" and not item.get("verified_at"):
            raise ReleaseLedgerError(f"版本 {item.get('version')} 缺少 fnOS 验收时间")
    return payload


def _write_ledger(path: Path, payload: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o644,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def preflight(root: Path, ledger_path: Path, version: str | None = None) -> dict:
    current = version or read_current_version(root)
    current_key = parse_version(current)
    ledger = load_ledger(ledger_path)
    fingerprint = source_fingerprint(root)
    releases = ledger["releases"]
    if not releases:
        return {"mode": "new", "version": current, "source_sha256": fingerprint}
    latest = releases[-1]
    latest_key = parse_version(latest["version"])
    if current_key < latest_key:
        raise ReleaseLedgerError(
            f"当前版本 {current} 低于最近候选 {latest['version']}，拒绝构建"
        )
    if current_key == latest_key:
        if latest.get("source_sha256") == fingerprint:
            return {"mode": "rebuild", "version": current, "source_sha256": fingerprint}
        raise ReleaseLedgerError(
            f"版本 {current} 已用于其他源码；请先提升根 VERSION 再构建"
        )
    return {"mode": "new", "version": current, "source_sha256": fingerprint}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def record_build(root: Path, ledger_path: Path, artifact: Path) -> dict:
    check = preflight(root, ledger_path)
    artifact_sha = _sha256_file(artifact)
    payload = load_ledger(ledger_path)
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    build = {"artifact_sha256": artifact_sha, "built_at": now}
    if check["mode"] == "new":
        payload["releases"].append({
            "version": check["version"],
            "source_sha256": check["source_sha256"],
            "status": "candidate",
            "builds": [build],
        })
    else:
        release = payload["releases"][-1]
        if not any(
            item.get("artifact_sha256") == artifact_sha
            for item in release["builds"]
        ):
            release["builds"].append(build)
    _write_ledger(ledger_path, payload)
    return {**check, "artifact_sha256": artifact_sha}


def mark_verified(ledger_path: Path, version: str, note: str) -> dict:
    parse_version(version)
    payload = load_ledger(ledger_path)
    release = next(
        (item for item in payload["releases"] if item["version"] == version),
        None,
    )
    if release is None:
        raise ReleaseLedgerError(f"版本 {version} 还没有成功候选包，不能登记验收")
    release["status"] = "verified"
    release["verified_at"] = datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )
    release["verification_note"] = str(note or "").strip() or "fnOS 真机验收通过"
    _write_ledger(ledger_path, payload)
    return release


def status(root: Path, ledger_path: Path) -> dict:
    payload = load_ledger(ledger_path)
    releases = payload["releases"]
    verified = next(
        (item for item in reversed(releases) if item["status"] == "verified"),
        None,
    )
    return {
        "current_version": read_current_version(root),
        "latest_candidate": releases[-1]["version"] if releases else None,
        "latest_verified": verified["version"] if verified else None,
    }


def _default_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=_default_root())
    parser.add_argument("--ledger", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    preflight_parser = subparsers.add_parser("preflight")
    preflight_parser.add_argument("--version")
    record_parser = subparsers.add_parser("record-build")
    record_parser.add_argument("--artifact", type=Path, required=True)
    verify_parser = subparsers.add_parser("mark-verified")
    verify_parser.add_argument("--version", required=True)
    verify_parser.add_argument("--note", required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    ledger_path = (args.ledger or root / "deploy/release-ledger.json").resolve()
    try:
        if args.command == "status":
            result = status(root, ledger_path)
        elif args.command == "preflight":
            result = preflight(root, ledger_path, args.version)
        elif args.command == "record-build":
            result = record_build(root, ledger_path, args.artifact.resolve())
        else:
            result = mark_verified(ledger_path, args.version, args.note)
    except (OSError, ReleaseLedgerError) as error:
        print(f"发布门禁失败: {error}", file=sys.stderr)
        return 1
    if args.command == "status":
        print(f"当前开发版本: {result['current_version']}")
        print(f"最近候选包: {result['latest_candidate'] or '暂无'}")
        print(f"最近 fnOS 验收正常版本: {result['latest_verified'] or '暂无'}")
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
