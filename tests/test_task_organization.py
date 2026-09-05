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


def _completed_organized_task(manager, config, *, with_subtitle=True):
    directory = os.path.join(config["library_roots"][0]["path"], "电影", "小姐")
    os.makedirs(directory, exist_ok=True)
    video = os.path.join(directory, "小姐.2016.mkv")
    with open(video, "wb") as handle:
        handle.write(b"organized-video-bytes")
    subtitles = []
    if with_subtitle:
        subtitle = os.path.join(directory, "小姐.2016.zh.srt")
        with open(subtitle, "wb") as handle:
            handle.write(b"organized-subtitle-bytes")
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
        import_path=directory,
        final_filename=os.path.basename(video),
        organization_status=ORGANIZATION_ORGANIZED,
        scrape_result={
            "title_cn": "小姐",
            "title_en": "The Handmaiden",
            "year": 2016,
            "media_type": "movie",
            "dimensions": {"media_type": "movie"},
        },
        scrape_dimensions={"media_type": "movie"},
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


def test_completed_organized_task_can_create_custom_manual_relocation(tmp_path):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, video, subtitles = _completed_organized_task(manager, config)

    first = create_reorganization_task_for_api(
        manager,
        config,
        parent["task_id"],
        mode="custom",
        library_root_id="main",
        relative_dir="收藏/韩国电影",
    )
    second = create_reorganization_task_for_api(
        manager,
        config,
        parent["task_id"],
        mode="custom",
        library_root_id="main",
        relative_dir="其他位置",
    )

    assert first.code == 201
    assert second.code == 200
    child = first.data["task"]
    assert child["task_kind"] == "REORGANIZE"
    assert child["parent_task_id"] == parent["task_id"]
    assert child["status"] == "PENDING"
    assert child["stage"] == "AWAIT_REVIEW"
    assert child["video_path"] == video
    assert child["final_filename"] == os.path.basename(video)
    assert child["import_path"] == os.path.join(
        config["library_roots"][0]["path"], "收藏", "韩国电影"
    )
    assert child["reorganization_intent"]["reason"] == "user_requested"
    assert child["reorganization_intent"]["mode"] == "custom"
    assert [row["source_path"] for row in get_subtitles_by_task(
        manager.conn, child["task_id"]
    )] == subtitles
    assert manager.get_task(parent["task_id"])["status"] == "SUCCESS"


@pytest.mark.parametrize(
    ("root_id", "relative_dir", "message"),
    [
        ("missing", "电影/收藏", "片库不存在"),
        ("main", "../越界", "不能超出片库根目录"),
        ("main", "/绝对路径", "必须是相对路径"),
        ("main", "", "具体子目录"),
    ],
)
def test_custom_manual_relocation_rejects_unsafe_target(
    tmp_path, root_id, relative_dir, message
):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, _video, _subtitles = _completed_organized_task(manager, config)

    result = create_reorganization_task_for_api(
        manager,
        config,
        parent["task_id"],
        mode="custom",
        library_root_id=root_id,
        relative_dir=relative_dir,
    )

    assert result.code == 400
    assert message in result.message
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
    assert again.code == 200
    assert again.data["task"]["task_id"] == child["task_id"]


def test_manual_relocation_moves_bundle_and_updates_parent_current_paths(tmp_path):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, video, subtitles = _completed_organized_task(manager, config)
    child = create_reorganization_task_for_api(
        manager,
        config,
        parent["task_id"],
        mode="custom",
        library_root_id="main",
        relative_dir="收藏/韩国电影",
    ).data["task"]

    result = ReorganizationService(config, manager.conn).reorganize_task(child)

    expected_dir = os.path.join(config["library_roots"][0]["path"], "收藏", "韩国电影")
    assert result.video_path == os.path.join(expected_dir, "小姐.2016.mkv")
    assert result.subtitle_files == [os.path.join(expected_dir, "小姐.2016.zh.srt")]
    assert not os.path.exists(video)
    assert not os.path.exists(subtitles[0])
    updated_parent = manager.get_task(parent["task_id"])
    assert updated_parent["status"] == "SUCCESS"
    assert updated_parent["import_video_path"] == result.video_path
    assert updated_parent["import_path"] == expected_dir
    parent_subtitles = get_subtitles_by_task(manager.conn, parent["task_id"])
    assert parent_subtitles[0]["import_path"] == result.subtitle_files[0]
    completed_child = manager.get_task(child["task_id"])
    assert completed_child["reorganization_intent"]["completed_target_path"] == result.video_path


def test_manual_relocation_maps_nonstandard_subtitle_without_touching_missing_history(tmp_path):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    directory = os.path.join(config["library_roots"][0]["path"], "电影", "测试片")
    os.makedirs(directory, exist_ok=True)
    video = os.path.join(directory, "测试片.2024.mkv")
    existing_subtitle = os.path.join(directory, "commentary.final.zh-Hans.srt")
    missing_subtitle = os.path.join(directory, "missing.zh.srt")
    with open(video, "wb") as handle:
        handle.write(b"video")
    with open(existing_subtitle, "wb") as handle:
        handle.write(b"subtitle")
    parent = manager.create_task(
        video,
        os.path.basename(video),
        [missing_subtitle, existing_subtitle],
    )
    update_task(
        manager.conn,
        parent["task_id"],
        status="SUCCESS",
        stage="DONE",
        import_success=1,
        file_location="import",
        video_path=video,
        import_video_path=video,
        import_path=directory,
        final_filename=os.path.basename(video),
        organization_status=ORGANIZATION_ORGANIZED,
        scrape_result={"title_cn": "测试片", "year": 2024, "media_type": "movie"},
        scrape_dimensions={"media_type": "movie"},
    )
    parent_rows = get_subtitles_by_task(manager.conn, parent["task_id"])
    for row in parent_rows:
        update_subtitle(
            manager.conn,
            row["id"],
            status="SUCCESS" if os.path.isfile(row["source_path"]) else "FAILED",
            import_path=row["source_path"],
            target_path=row["source_path"],
            planned_filename=os.path.basename(row["source_path"]),
        )

    child = create_reorganization_task_for_api(
        manager,
        config,
        parent["task_id"],
        mode="custom",
        library_root_id="main",
        relative_dir="人工收藏/测试",
    ).data["task"]
    child_row = get_subtitles_by_task(manager.conn, child["task_id"])[0]
    result = ReorganizationService(config, manager.conn).reorganize_task(child)

    assert os.path.basename(result.subtitle_files[0]) == child_row["planned_filename"]
    updated_rows = get_subtitles_by_task(manager.conn, parent["task_id"])
    assert updated_rows[0]["import_path"] == missing_subtitle
    assert updated_rows[0]["status"] == "FAILED"
    assert updated_rows[1]["import_path"] == result.subtitle_files[0]
    assert updated_rows[1]["status"] == "SUCCESS"


def test_failed_manual_relocation_retry_returns_to_same_review_target(tmp_path):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, _video, _subtitles = _completed_organized_task(manager, config)
    child = create_reorganization_task_for_api(
        manager,
        config,
        parent["task_id"],
        mode="custom",
        library_root_id="main",
        relative_dir="人工收藏/重试",
    ).data["task"]
    expected_path = child["import_path"]
    expected_intent = child["reorganization_intent"]
    update_task(
        manager.conn,
        child["task_id"],
        status="FAILED",
        stage="DONE",
        file_location="import",
        error_message="模拟移动失败",
    )

    retried = manager.retry_task(child["task_id"])

    assert retried["status"] == "PENDING"
    assert retried["stage"] == "AWAIT_REVIEW"
    assert retried["file_location"] == "import"
    assert retried["import_path"] == expected_path
    assert retried["reorganization_intent"] == expected_intent


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


def test_confirm_custom_manual_relocation_keeps_selected_directory(tmp_path):
    config = _config(tmp_path)
    manager = TaskManager(str(tmp_path / "data"), config={})
    parent, video, subtitles = _completed_organized_task(manager, config)
    child = create_reorganization_task_for_api(
        manager,
        config,
        parent["task_id"],
        mode="custom",
        library_root_id="main",
        relative_dir="人工收藏/获奖电影",
    ).data["task"]

    from media_importer.notify.hooks import HookRunner

    runner = PipelineRunner.__new__(PipelineRunner)
    runner.config = config
    runner.task_manager = manager
    runner.metrics = None
    runner.logger = None
    runner.notifier = None
    runner.hooks = HookRunner(config)

    preview = runner.preview_task(child["task_id"], {"dimensions": {}})
    assert preview["import_path"].endswith(os.path.join("人工收藏", "获奖电影"))
    assert preview["used_fallback"] == 0
    assert runner.confirm_task(child["task_id"])

    expected_dir = os.path.join(
        config["library_roots"][0]["path"], "人工收藏", "获奖电影"
    )
    completed = manager.get_task(child["task_id"])
    assert completed["status"] == "SUCCESS"
    assert completed["import_video_path"] == os.path.join(expected_dir, "小姐.2016.mkv")
    assert completed["reorganization_intent"]["reason"] == "user_requested"
    assert completed["reorganization_intent"]["completed_target_path"] == completed["import_video_path"]
    assert not os.path.exists(video)
    assert not os.path.exists(subtitles[0])
    original = manager.get_task(parent["task_id"])
    assert original["status"] == "SUCCESS"
    assert original["import_video_path"] == completed["import_video_path"]
