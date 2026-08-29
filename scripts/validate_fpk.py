#!/usr/bin/env python3
"""Validate an fnOS FPK's structure and release-critical contents."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tarfile
from pathlib import Path, PurePosixPath

OUTER_REQUIRED = {
    "manifest",
    "app.tgz",
    "cmd/main",
    "cmd/install_callback",
    "cmd/upgrade_callback",
    "cmd/uninstall_callback",
    "cmd/config_callback",
    "wizard/install",
    "wizard/config",
    "wizard/uninstall",
    "config/resource",
    "config/privilege",
}
INNER_REQUIRED = {
    "ui/config",
    "ui/index.cgi",
    "server/fnos_config.py",
    "server/config.yaml.example",
    "server/requirements.txt",
    "server/media_importer/features/configuration/startup_readiness.py",
    "server/media_importer/features/configuration/library_paths.py",
    "server/media_importer/features/source_files/source_units.py",
    "server/media_importer/core/db/source_unit_repo.py",
}
JSON_FILES = {
    "wizard/install",
    "wizard/config",
    "wizard/uninstall",
    "config/resource",
    "config/privilege",
}
EXECUTABLE_FILES = {
    "cmd/main",
    "cmd/install_callback",
    "cmd/upgrade_callback",
    "cmd/uninstall_callback",
    "cmd/config_callback",
}
INNER_EXECUTABLE_FILES = {"ui/index.cgi"}


class ValidationError(ValueError):
    pass


def _normalize(name: str) -> str:
    return name.removeprefix("./")


def _forbidden(name: str) -> bool:
    path = PurePosixPath(_normalize(name))
    return (
        "__pycache__" in path.parts
        or path.name == ".DS_Store"
        or path.name == ".env"
        or path.suffix in {".pyc", ".db", ".sqlite", ".log"}
    )


def _manifest(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        if "=" not in raw_line or raw_line.lstrip().startswith("#"):
            continue
        key, value = raw_line.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def validate(path: Path, expected_version: str | None = None) -> dict[str, object]:
    errors: list[str] = []
    try:
        outer = tarfile.open(path, "r:*")
    except (OSError, tarfile.TarError) as exc:
        raise ValidationError(f"无法读取 FPK: {exc}") from exc

    with outer:
        members = {_normalize(member.name): member for member in outer.getmembers()}
        missing = OUTER_REQUIRED - set(members)
        if missing:
            errors.append("外层缺少: " + ", ".join(sorted(missing)))
        forbidden = [name for name in members if _forbidden(name)]
        if forbidden:
            errors.append("外层包含禁止文件: " + ", ".join(sorted(forbidden)[:10]))

        for name in JSON_FILES & set(members):
            extracted = outer.extractfile(members[name])
            try:
                json.loads(extracted.read().decode("utf-8") if extracted else "")
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"JSON 无效 {name}: {exc}")

        for name in EXECUTABLE_FILES & set(members):
            if members[name].mode & 0o111 == 0:
                errors.append(f"脚本不可执行: {name}")

        manifest_data: dict[str, str] = {}
        if "manifest" in members:
            extracted = outer.extractfile(members["manifest"])
            manifest_data = _manifest(extracted.read().decode("utf-8") if extracted else "")
            if expected_version and manifest_data.get("version") != expected_version:
                errors.append(f"版本不匹配: {manifest_data.get('version')} != {expected_version}")
            dependencies = {item.strip() for item in manifest_data.get("install_dep_apps", "").split(",")}
            if "python312" not in dependencies:
                errors.append("manifest 未声明 python312")

        inner_names: set[str] = set()
        inner_members: dict[str, tarfile.TarInfo] = {}
        if "app.tgz" in members:
            extracted = outer.extractfile(members["app.tgz"])
            try:
                with tarfile.open(fileobj=io.BytesIO(extracted.read() if extracted else b""), mode="r:gz") as inner:
                    inner_members = {_normalize(member.name): member for member in inner.getmembers()}
                    inner_names = set(inner_members)
            except tarfile.TarError as exc:
                errors.append(f"app.tgz 无效: {exc}")
            inner_missing = INNER_REQUIRED - inner_names
            if inner_missing:
                errors.append("应用层缺少: " + ", ".join(sorted(inner_missing)))
            inner_forbidden = [name for name in inner_names if _forbidden(name)]
            if inner_forbidden:
                errors.append("应用层包含禁止文件: " + ", ".join(sorted(inner_forbidden)[:10]))
            for name in INNER_EXECUTABLE_FILES & inner_names:
                if inner_members[name].mode & 0o111 == 0:
                    errors.append(f"应用脚本不可执行: {name}")

    if errors:
        raise ValidationError("; ".join(errors))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "path": str(path),
        "version": manifest_data.get("version"),
        "sha256": digest,
        "outer_entries": len(members),
        "app_entries": len(inner_names),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fpk", type=Path)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(validate(args.fpk, args.version), ensure_ascii=False, indent=2))
        return 0
    except ValidationError as exc:
        print(f"FPK 验证失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
