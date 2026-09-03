import os

import pytest

from media_importer.core.task_manager import TaskManager
from media_importer.features.import_flow.runner import PipelineRunner
from media_importer.features.import_flow.services.reorganization import (
    ReorganizationService,
)
from media_importer.features.import_flow.utils import PipelineReviewRequired
from media_importer.features.tasks.organization_service import (
    ORGANIZATION_FALLBACK_PENDING,
    ORGANIZATION_ORGANIZED,
    backfill_fallback_outcomes,
    create_reorganization_task_for_api,
)
from media_importer.infrastructure.db import (
    get_subtitles_by_task,
    update_subtitle,
    update_task,
)


def _config(tmp_path):
    library = tmp_path / "library"
    source = tmp_path / "source"
    recycle = tmp_path / "recycle"
    for path in (library, source, recycle):
        path.mkdir()
    return {
        "source_dir": str(source),
        "library_roots": [
            {"id": "main", "name": "主片库", "path": str(library), "enabled": True},
        ],
        "default_library_root_id": "main",
        "fallback_library_root_id": "main",
        "fallback_dir": "待整理",
        "path_rules": [
            {
                "name": "电影",
                "conditions": {"media_type": "movie"},
                "library_root_id": "main",
                "template": "电影/{title_cn}",
            },
        ],
        "filename_templates": {
            "movie": "{title_cn}.{year}.{ext}",
            "subtitle": "{video_filename}.{lang}.{ext}",
        },
        "source_policy": {"recycle_dir": str(recycle)},
    }


def _completed_fallback_task(manager, config, *, with_subtitle=True):
    fallback = os.path.join(config["library_roots"][0]["path"], "待整理")
    os.makedirs(fallback, exist_ok=True)
    video = os.path.join(fallback, "小姐.2016.mkv")
    with open(video, "wb") as handle:
        handle.write(b"video-bytes")
    subtitles = []
    if with_subtitle:
        subtitle = os.path.join(fallback, "小姐.2016.zh.srt")
        with open(subtitle, "wb") as handle:
            handle.write(b"subtitle-bytes")
        subtitles.append(subtitle)
    task = manager.create_task(video, os.path.basename(video), subtitles)
    update_task(
        manager.conn,
        task["task_id"],
        status="SUCCESS",
        stage="DONE",
        import_success=1,
        file_location="import",
        video_path=video,
        import_video_path=video,
        import_path=fallback,
        scrape_result={
            "title_cn": "小姐",
            "title_en": "The Handmaiden",
            "year": 2016,
            "media_type": "movie",
            "dimensions": {},
        },
        scrape_dimensions={},
    )
    for row in get_subtitles_by_task(manager.conn, task["task_id"]):
        update_subtitle(
            manager.conn,
            row["id"],
            status="SUCCESS",
            import_path=row["source_path"],
            target_path=row["source_path"],
            planned_filename=os.path.basename(row["source_path"]),
        )
    return manager.get_task(task["task_id"]), video, subtitles


def test_backfill_marks_completed_fallback_without_reopening_task(tmp_path):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, _video, _subtitles = _completed_fallback_task(manager, config)

    assert backfill_fallback_outcomes(manager.conn, config) == 1

    current = manager.get_task(parent["task_id"])
    assert current["status"] == "SUCCESS"
    assert current["stage"] == "DONE"
    assert current["organization_status"] == ORGANIZATION_FALLBACK_PENDING
    assert current["used_fallback"] == 1


def test_create_reorganization_keeps_parent_completed_and_is_idempotent(tmp_path):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, video, subtitles = _completed_fallback_task(manager, config)
    backfill_fallback_outcomes(manager.conn, config)

    first = create_reorganization_task_for_api(manager, config, parent["task_id"])
    second = create_reorganization_task_for_api(manager, config, parent["task_id"])

    assert first.code == 201
    assert second.code == 200
    assert second.data["task"]["task_id"] == first.data["task"]["task_id"]
    child = first.data["task"]
    assert child["task_kind"] == "REORGANIZE"
    assert child["parent_task_id"] == parent["task_id"]
    assert child["status"] == "PENDING"
    assert child["stage"] == "AWAIT_REVIEW"
    assert child["video_path"] == video
    assert [row["source_path"] for row in get_subtitles_by_task(manager.conn, child["task_id"])] == subtitles
    assert manager.get_task(parent["task_id"])["status"] == "SUCCESS"


def test_reorganization_moves_video_and_subtitle_as_bundle_and_resolves_parent(tmp_path):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, video, subtitles = _completed_fallback_task(manager, config)
    backfill_fallback_outcomes(manager.conn, config)
    child = create_reorganization_task_for_api(manager, config, parent["task_id"]).data["task"]
    target = os.path.join(config["library_roots"][0]["path"], "电影", "小姐")
    update_task(
        manager.conn,
        child["task_id"],
        import_path=target,
        final_filename="小姐.2016.mkv",
        used_fallback=0,
    )
    subtitle_row = get_subtitles_by_task(manager.conn, child["task_id"])[0]
    update_subtitle(
        manager.conn,
        subtitle_row["id"],
        planned_filename="小姐.2016.zh.srt",
    )
    child = manager.get_task(child["task_id"])

    result = ReorganizationService(config, manager.conn).reorganize_task(child)

    assert result.video_path == os.path.join(target, "小姐.2016.mkv")
    assert result.subtitle_files == [os.path.join(target, "小姐.2016.zh.srt")]
    assert not os.path.exists(video)
    assert not os.path.exists(subtitles[0])
    assert open(result.video_path, "rb").read() == b"video-bytes"
    assert open(result.subtitle_files[0], "rb").read() == b"subtitle-bytes"
    resolved_parent = manager.get_task(parent["task_id"])
    assert resolved_parent["organization_status"] == ORGANIZATION_ORGANIZED
    assert resolved_parent["reorganized_by_task_id"] == child["task_id"]
    again = create_reorganization_task_for_api(manager, config, parent["task_id"])
    assert again.code == 400
    assert "已经按正式规则整理完成" in again.message


def test_reorganization_never_overwrites_existing_target(tmp_path):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, video, subtitles = _completed_fallback_task(manager, config)
    backfill_fallback_outcomes(manager.conn, config)
    child = create_reorganization_task_for_api(manager, config, parent["task_id"]).data["task"]
    target = os.path.join(config["library_roots"][0]["path"], "电影", "小姐")
    os.makedirs(target, exist_ok=True)
    existing = os.path.join(target, "小姐.2016.mkv")
    with open(existing, "wb") as handle:
        handle.write(b"existing-library-file")
    update_task(
        manager.conn,
        child["task_id"],
        import_path=target,
        final_filename="小姐.2016.mkv",
        used_fallback=0,
    )
    child = manager.get_task(child["task_id"])

    with pytest.raises(PipelineReviewRequired):
        ReorganizationService(config, manager.conn).reorganize_task(child)

    assert open(existing, "rb").read() == b"existing-library-file"
    assert open(video, "rb").read() == b"video-bytes"
    assert open(subtitles[0], "rb").read() == b"subtitle-bytes"
    assert manager.get_task(parent["task_id"])["organization_status"] == ORGANIZATION_FALLBACK_PENDING


def test_confirm_reorganization_finishes_child_without_reopening_parent(tmp_path):
    config = _config(tmp_path)
    config["path_rules"] = [{
        "name": "默认电影",
        "conditions": {},
        "library_root_id": "main",
        "template": "电影/{title_cn}",
    }]
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, video, subtitles = _completed_fallback_task(manager, config)
    backfill_fallback_outcomes(manager.conn, config)
    child = create_reorganization_task_for_api(manager, config, parent["task_id"]).data["task"]

    from media_importer.notify.hooks import HookRunner

    runner = PipelineRunner.__new__(PipelineRunner)
    runner.config = config
    runner.task_manager = manager
    runner.metrics = None
    runner.logger = None
    runner.notifier = None
    runner.hooks = HookRunner(config)

    assert runner.confirm_task(child["task_id"])

    completed = manager.get_task(child["task_id"])
    assert completed["status"] == "SUCCESS"
    assert completed["stage"] == "DONE"
    assert completed["task_kind"] == "REORGANIZE"
    assert completed["source_cleanup_status"] == "SKIPPED"
    assert completed["used_fallback"] == 0
    assert os.path.isfile(completed["import_video_path"])
    assert not os.path.exists(video)
    assert not os.path.exists(subtitles[0])
    original = manager.get_task(parent["task_id"])
    assert original["status"] == "SUCCESS"
    assert original["organization_status"] == ORGANIZATION_ORGANIZED
    assert original["reorganized_by_task_id"] == child["task_id"]
