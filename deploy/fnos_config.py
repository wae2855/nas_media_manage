#!/usr/bin/env python3
"""Initialize and update fnOS runtime configuration without third-party modules."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from pathlib import Path

TOP_LEVEL_KEYS = {
    "source_dir", "log_dir", "resource_dir", "library_root", "library_roots",
    "default_library_root_id", "fallback_library_root_id",
}
SECTION_KEYS = {
    ("server", "port"),
    ("server", "api_key"),
    ("source_policy", "recycle_dir"),
}
APP_MANAGED_PATH_PATTERN = re.compile(
    r"^(?:/vol\d+/@(?:appdata|apptemp|appshare)/nas-media-importer"
    r"|/var/(?:apps|packages)/nas-media-importer/var)(?:/|$)"
)


class ConfigError(ValueError):
    """Configuration input or template is invalid."""


def _yaml_scalar(value: str | int) -> str:
    if isinstance(value, int):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _replace_values(template: str, replacements: dict[tuple[str | None, str], str | int]) -> str:
    lines = template.splitlines(keepends=True)
    found: set[tuple[str | None, str]] = set()
    section: str | None = None

    for index, line in enumerate(lines):
        match = re.match(r"^(?P<indent>\s*)(?P<key>[A-Za-z_][\w-]*):(?P<rest>.*?)(?P<newline>\r?\n)?$", line)
        if not match:
            continue
        indent = match.group("indent")
        key = match.group("key")
        if not indent:
            section = key if match.group("rest").strip() == "" else None
            target = (None, key)
        else:
            target = (section, key)
        if target not in replacements:
            continue

        rest = match.group("rest")
        comment = ""
        if "#" in rest:
            comment = "  #" + rest.split("#", 1)[1]
        newline = match.group("newline") or ""
        lines[index] = f"{indent}{key}: {_yaml_scalar(replacements[target])}{comment}{newline}"
        found.add(target)

    missing = set(replacements) - found
    if missing:
        labels = ", ".join(f"{section + '.' if section else ''}{key}" for section, key in sorted(missing))
        raise ConfigError(f"配置模板缺少字段: {labels}")
    return "".join(lines)


def _replace_top_level_block(content: str, key: str, replacement: str) -> str:
    lines = content.splitlines(keepends=True)
    start = next((index for index, line in enumerate(lines) if line.startswith(f"{key}:")), None)
    if start is None:
        raise ConfigError(f"配置模板缺少字段: {key}")
    end = start + 1
    while end < len(lines):
        line = lines[end]
        if line.strip() and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        if line.lstrip().startswith("#") and not line[0].isspace():
            break
        end += 1
    newline = "\r\n" if lines[start].endswith("\r\n") else "\n"
    lines[start:end] = [f"{key}: {replacement}{newline}"]
    return "".join(lines)


def _remove_top_level_scalar(content: str, key: str) -> str:
    """Remove an unsupported top-level scalar from an existing config."""
    return re.sub(rf"(?m)^{re.escape(key)}\s*:[^\r\n]*(?:\r?\n|$)", "", content)


def _ensure_top_level_scalar(content: str, key: str, value: str, after_key: str) -> str:
    """Add one fnOS-owned path to legacy configs without replacing user values."""
    if re.search(rf"(?m)^{re.escape(key)}\s*:", content):
        return content

    lines = content.splitlines(keepends=True)
    insert_at = next(
        (index + 1 for index, line in enumerate(lines) if re.match(rf"^{re.escape(after_key)}\s*:", line)),
        len(lines),
    )
    newline = "\r\n" if any(line.endswith("\r\n") for line in lines) else "\n"
    lines.insert(insert_at, f"{key}: {_yaml_scalar(value)}{newline}")
    return "".join(lines)


def _align_managed_path(content: str, key: str, value: str, after_key: str) -> str:
    """Move only package-owned defaults to the current fnOS private root.

    A user-selected shared directory is business configuration and must be
    preserved across reinstalls.  An old ``@appdata``/package-var default is
    fnOS-owned state and follows ``TRIM_PKGVAR`` when the package moves disks.
    """
    if not value:
        return content
    match = re.search(rf"(?m)^{re.escape(key)}\s*:(?P<value>[^\r\n]*)", content)
    if match is None:
        return _ensure_top_level_scalar(content, key, value, after_key)
    current_value = _parse_path_scalar(match.group("value"))
    if not APP_MANAGED_PATH_PATTERN.match(current_value):
        return content
    return _replace_values(content, {(None, key): value})


def _parse_path_scalar(raw_value: str) -> str:
    """Read the path value without letting comments influence migration."""
    value = raw_value.strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed, _end = json.JSONDecoder().raw_decode(value)
            return parsed if isinstance(parsed, str) else ""
        except json.JSONDecodeError:
            return ""
    if value.startswith("'"):
        match = re.match(r"^'((?:[^']|'')*)'", value)
        return match.group(1).replace("''", "'") if match else ""
    return re.split(r"\s+#", value, maxsplit=1)[0].strip()


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary_name, 0o600)
        os.replace(temporary_name, path)
        try:
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _absolute_path(value: str, label: str) -> str:
    if not value or "\x00" in value or "\n" in value or "\r" in value:
        raise ConfigError(f"{label}不能为空或包含换行")
    path = Path(value)
    if not path.is_absolute():
        raise ConfigError(f"{label}必须是绝对路径")
    return str(path)


def _optional_absolute_path(value: str | None, label: str) -> str:
    if value in {None, ""}:
        return ""
    return _absolute_path(value, label)


def _port(value: str | int) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("端口必须是数字") from exc
    if not 1024 <= port <= 65535:
        raise ConfigError("端口必须在 1024 到 65535 之间")
    return port


def initialize(args: argparse.Namespace) -> str:
    config_path = Path(args.config)
    if config_path.exists():
        return "existing"

    replacements: dict[tuple[str | None, str], str | int] = {
        (None, "source_dir"): _optional_absolute_path(getattr(args, "source_dir", ""), "来源目录"),
        (None, "log_dir"): _absolute_path(args.log_dir, "日志目录"),
        (None, "resource_dir"): _absolute_path(args.resource_dir, "海报与缓存目录"),
        (None, "library_root"): _optional_absolute_path(getattr(args, "library_root", ""), "片库根目录"),
        ("source_policy", "recycle_dir"): _optional_absolute_path(getattr(args, "recycle_dir", ""), "回收目录"),
        ("file_watcher", "enabled"): False,
        ("server", "port"): 14591,
        ("server", "api_key"): "",
    }
    template = Path(args.template).read_text(encoding="utf-8")
    rendered = _replace_values(template, replacements)
    if not getattr(args, "library_root", ""):
        rendered = _replace_top_level_block(rendered, "library_roots", "[]")
        rendered = _replace_values(rendered, {
            (None, "default_library_root_id"): "",
            (None, "fallback_library_root_id"): "",
        })
        # Fresh installations do not have a target root yet. Template rules
        # must follow the first user-selected default instead of referencing
        # the template-only "default" root.
        rendered = re.sub(r"(?m)^\s+library_root_id:\s*.*(?:\n|$)", "", rendered)
    _atomic_write(config_path, rendered)
    return "created"


def update_port(args: argparse.Namespace) -> str:
    path = Path(args.config)
    if not path.is_file():
        raise ConfigError("运行配置不存在，请先完成安装初始化")
    current = path.read_text(encoding="utf-8")
    rendered = _replace_values(current, {("server", "port"): _port(args.port)})
    _atomic_write(path, rendered)
    return "updated"


def migrate_managed_service(args: argparse.Namespace) -> str:
    """Align fnOS-owned service settings without touching user configuration."""
    path = Path(args.config)
    if not path.is_file():
        raise ConfigError("运行配置不存在，无法完成 fnOS 托管配置迁移")
    original = path.read_text(encoding="utf-8")
    current = _remove_top_level_scalar(original, "temp_dir")
    rendered = _replace_values(current, {
        ("server", "port"): 14591,
        ("server", "api_key"): "",
    })
    managed_paths = (
        ("log_dir", "日志目录", "source_dir"),
        ("resource_dir", "海报与缓存目录", "log_dir"),
    )
    for key, label, after_key in managed_paths:
        value = _optional_absolute_path(getattr(args, key, ""), label)
        rendered = _align_managed_path(rendered, key, value, after_key)
    if rendered == original:
        return "unchanged"
    _atomic_write(path, rendered)
    return "updated"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("initialize")
    for name in ("config", "template", "log-dir", "resource-dir"):
        init_parser.add_argument(f"--{name}", required=True)
    for name in ("source-dir", "library-root", "recycle-dir"):
        init_parser.add_argument(f"--{name}", default="")
    init_parser.set_defaults(handler=initialize)

    port_parser = subparsers.add_parser("update-port")
    port_parser.add_argument("--config", required=True)
    port_parser.add_argument("--port", required=True)
    port_parser.set_defaults(handler=update_port)

    managed_parser = subparsers.add_parser("migrate-managed-service")
    managed_parser.add_argument("--config", required=True)
    managed_parser.add_argument("--log-dir", default="")
    managed_parser.add_argument("--resource-dir", default="")
    managed_parser.set_defaults(handler=migrate_managed_service)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        print(args.handler(args))
        return 0
    except (ConfigError, OSError) as exc:
        print(f"配置失败: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
