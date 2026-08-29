from unittest.mock import patch

from media_importer.core.config_view import ConfigView
from media_importer.features.source_files.cleanup_service import SourceCleanupService


def _config(mode: str) -> dict:
    return {
        "source_dir": "/source",
        "temp_dir": "/temp",
        "video_extensions": [".mkv"],
        "subtitle_extensions": [".srt"],
        "source_policy": {
            "mode": mode,
            "recycle_dir": "/recycle",
        },
        "source_cleaner": {"enabled": True, "ai_enabled": True},
    }


def test_source_policy_modes_are_explicit_and_legacy_true_migrates_to_unit_recycle():
    assert ConfigView.from_dict(_config("preserve_all")).source_policy.mode == "preserve_all"
    assert ConfigView.from_dict(_config("preserve_media")).source_policy.mode == "preserve_media"
    assert ConfigView.from_dict(_config("recycle_source_unit")).source_policy.mode == "recycle_source_unit"

    legacy = _config("preserve_all")
    legacy["source_policy"].pop("mode")
    legacy["source_policy"]["cleanup_source_after_done"] = True
    assert ConfigView.from_dict(legacy).source_policy.mode == "recycle_source_unit"


def test_only_preserve_media_can_enable_junk_cleaner_and_llm():
    for mode, expected in (
        ("preserve_all", False),
        ("preserve_media", True),
        ("recycle_source_unit", False),
    ):
        view = ConfigView.from_dict(_config(mode))
        assert view.source_cleaner.enabled is expected
        assert view.source_cleaner.ai_enabled is expected


def test_post_import_never_recycles_an_individual_file_in_unit_mode():
    service = SourceCleanupService(_config("recycle_source_unit"))

    with patch(
        "media_importer.features.source_files.cleanup_service.move_to_recycle_with_companions",
        create=True,
    ) as move_to_recycle:
        result = service.cleanup_source_after_import(
            {"task_id": "task-1"}, "/source/Forrest Gump/movie.mkv", []
        )

    move_to_recycle.assert_not_called()
    assert result.moved_count == 0
    assert "源单元" in result.message


def test_skip_never_recycles_source_in_unit_mode():
    service = SourceCleanupService(_config("recycle_source_unit"))

    with patch(
        "media_importer.features.source_files.cleanup_service.move_to_recycle_with_companions",
        create=True,
    ) as move_to_recycle:
        result = service.recycle_source_after_skip(
            {"task_id": "task-1"}, "/source/Forrest Gump/movie.mkv", []
        )

    move_to_recycle.assert_not_called()
    assert result.moved_count == 0
    assert "未全部成功" in result.message
