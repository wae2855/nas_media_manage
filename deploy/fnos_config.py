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

TOP_LEVEL_KEYS = {"source_dir", "temp_dir", "log_dir", "library_root"}
SECTION_KEYS = {
    ("server", "port"),
    ("server", "api_key"),
    ("source_policy", "recycle_dir"),
}


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
    api_key_value = sys.stdin.read() if getattr(args, "api_key_stdin", False) else args.api_key
    api_key = (api_key_value or "").strip()
    if not api_key or any(character in api_key for character in "\r\n\x00"):
        raise ConfigError("初始 API Key 不能为空或包含换行")

    replacements: dict[tuple[str | None, str], str | int] = {
        (None, "source_dir"): _absolute_path(args.source_dir, "来源目录"),
        (None, "temp_dir"): _absolute_path(args.temp_dir, "中转目录"),
        (None, "log_dir"): _absolute_path(args.log_dir, "日志目录"),
        (None, "library_root"): _absolute_path(args.library_root, "片库根目录"),
        ("source_policy", "recycle_dir"): _absolute_path(args.recycle_dir, "回收目录"),
        ("server", "port"): _port(args.port),
        ("server", "api_key"): api_key,
    }
    template = Path(args.template).read_text(encoding="utf-8")
    rendered = _replace_values(template, replacements)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("initialize")
    for name in ("config", "template", "source-dir", "library-root", "recycle-dir", "temp-dir", "log-dir", "port"):
        init_parser.add_argument(f"--{name}", required=True)
    key_group = init_parser.add_mutually_exclusive_group(required=True)
    key_group.add_argument("--api-key")
    key_group.add_argument("--api-key-stdin", action="store_true")
    init_parser.set_defaults(handler=initialize)

    port_parser = subparsers.add_parser("update-port")
    port_parser.add_argument("--config", required=True)
    port_parser.add_argument("--port", required=True)
    port_parser.set_defaults(handler=update_port)
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
