"""Application version sourced from the repository/package VERSION file."""

from __future__ import annotations

import re
from pathlib import Path

_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")


def read_app_version(path: Path) -> str:
    version = path.read_text(encoding="utf-8").strip()
    if not _VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"无效版本号: {version or '<empty>'}")
    return version


def get_app_version() -> str:
    version_file = Path(__file__).resolve().parents[1] / "VERSION"
    try:
        return read_app_version(version_file)
    except (OSError, ValueError):
        return "unknown"
