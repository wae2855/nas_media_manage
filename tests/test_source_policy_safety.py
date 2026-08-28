from pathlib import Path
from unittest.mock import patch

import yaml

from media_importer.core.config_loader import load_config
from media_importer.core.config_view import ConfigView
from media_importer.features.source_files.cleanup_service import SourceCleanupService


def _config(*, cleanup_source_after_done=None) -> dict:
    source_policy = {"recycle_dir": "/recycle"}
    if cleanup_source_after_done is not None:
        source_policy["cleanup_source_after_done"] = cleanup_source_after_done
    return {
        "source_dir": "/source",
        "temp_dir": "/temp",
        "video_extensions": [".mkv"],
        "subtitle_extensions": [".srt"],
        "source_policy": source_policy,
    }


def test_loader_defaults_missing_cleanup_policy_to_keep_source(tmp_path: Path):
    source_dir = tmp_path / "source"
    temp_dir = tmp_path / "temp"
    log_dir = tmp_path / "logs"
    recycle_dir = tmp_path / "recycle"
    for directory in (source_dir, temp_dir, log_dir, recycle_dir):
        directory.mkdir()

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "source_dir": str(source_dir),
                "temp_dir": str(temp_dir),
                "log_dir": str(log_dir),
                "source_policy": {"recycle_dir": str(recycle_dir)},
            }
        ),
        encoding="utf-8",
    )

    loaded = load_config(str(config_path))

    assert loaded["source_policy"]["cleanup_source_after_done"] is False


def test_config_view_defaults_missing_cleanup_policy_to_keep_source():
    view = ConfigView.from_dict(_config())

    assert view.source_policy.cleanup_source_after_done is False


def test_post_import_missing_or_false_policy_keeps_source():
    for configured_value in (None, False):
        service = SourceCleanupService(
            _config(cleanup_source_after_done=configured_value)
        )

        with patch(
            "media_importer.features.source_files.cleanup_service.move_to_recycle_with_companions"
        ) as move_to_recycle:
            result = service.cleanup_source_after_import(
                {"task_id": "task-1"}, "/source/Movie.mkv", []
            )

        move_to_recycle.assert_not_called()
        assert result.moved_count == 0
        assert "源文件保留" in result.message


def test_post_import_explicit_true_allows_recycle():
    service = SourceCleanupService(_config(cleanup_source_after_done=True))

    with (
        patch(
            "media_importer.features.source_files.cleanup_service.move_to_recycle_with_companions",
            return_value=1,
        ) as move_to_recycle,
        patch(
            "media_importer.features.source_files.cleanup_service.remove_empty_parent_dir"
        ),
    ):
        result = service.cleanup_source_after_import(
            {"task_id": "task-1"}, "/source/Movie.mkv", []
        )

    move_to_recycle.assert_called_once()
    assert result.moved_count == 1


def test_skip_missing_or_false_policy_keeps_source():
    for configured_value in (None, False):
        service = SourceCleanupService(
            _config(cleanup_source_after_done=configured_value)
        )

        with patch(
            "media_importer.features.source_files.cleanup_service.move_to_recycle_with_companions"
        ) as move_to_recycle:
            result = service.recycle_source_after_skip(
                {"task_id": "task-1"}, "/source/Movie.mkv", []
            )

        move_to_recycle.assert_not_called()
        assert result.moved_count == 0
        assert "源文件保留" in result.message


def test_skip_explicit_true_allows_recycle():
    service = SourceCleanupService(_config(cleanup_source_after_done=True))

    with (
        patch(
            "media_importer.features.source_files.cleanup_service.move_to_recycle_with_companions",
            return_value=1,
        ) as move_to_recycle,
        patch(
            "media_importer.features.source_files.cleanup_service.remove_empty_parent_dir"
        ),
    ):
        result = service.recycle_source_after_skip(
            {"task_id": "task-1"}, "/source/Movie.mkv", []
        )

    move_to_recycle.assert_called_once()
    assert result.moved_count == 1
