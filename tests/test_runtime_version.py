from pathlib import Path

import pytest

from media_importer.api import connectivity_handlers
from media_importer.app_version import get_app_version, read_app_version

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_version_matches_repository_fact():
    expected = (ROOT / "VERSION").read_text(encoding="utf-8").strip()

    assert get_app_version() == expected


@pytest.mark.parametrize("value", ["", "v0.3.21", "0.3", "0.3.21-dev"])
def test_runtime_version_rejects_non_release_values(tmp_path: Path, value: str):
    version_file = tmp_path / "VERSION"
    version_file.write_text(value, encoding="utf-8")

    with pytest.raises(ValueError, match="无效版本号"):
        read_app_version(version_file)


def test_public_health_payload_exposes_the_runtime_version(tmp_path: Path, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        connectivity_handlers.globals,
        "_config",
        {
            "source_dir": str(tmp_path),
            "log_dir": str(tmp_path),
            "llm": {},
        },
    )
    monkeypatch.setattr(
        connectivity_handlers,
        "json_response",
        lambda handler, status, *, data=None, message="": captured.update(
            status=status, data=data, message=message,
        ),
    )

    connectivity_handlers.ConnectivityHandlersMixin()._health(
        body={}, params={}, query={},
    )

    assert captured["status"] == 200
    assert captured["data"]["version"] == (ROOT / "VERSION").read_text(
        encoding="utf-8"
    ).strip()
