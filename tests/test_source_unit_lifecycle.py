from pathlib import Path

import pytest

from media_importer.core.db.connection import init_db
from media_importer.core.db.task_repo import create_task, update_task
from media_importer.features.source_files.source_units import (
    SourceUnitCoordinator,
    register_source_unit,
    resolve_source_unit,
)


def test_nested_media_uses_top_level_download_folder_as_unit(tmp_path: Path):
    source = tmp_path / "source"
    movie = source / "Forrest Gump"
    movie.mkdir(parents=True)
    video = movie / "movie.mkv"
    video.write_bytes(b"video")

    unit = resolve_source_unit(str(source), str(video))

    assert unit.kind == "folder"
    assert unit.unit_path == str(movie)
    assert [item["relative_path"] for item in unit.snapshot] == ["movie.mkv"]


def test_direct_files_share_one_loose_root_unit_without_moving_source_root(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.mkv").write_bytes(b"a")
    (source / "readme.txt").write_text("junk", encoding="utf-8")

    first = resolve_source_unit(str(source), str(source / "a.mkv"))
    second = resolve_source_unit(str(source), str(source / "readme.txt"))

    assert first.unit_id == second.unit_id
    assert first.kind == "loose_root"
    assert first.unit_path == str(source)
    assert {item["relative_path"] for item in first.snapshot} == {"a.mkv", "readme.txt"}


def test_same_folder_name_with_new_content_gets_a_new_unit_generation(tmp_path: Path):
    source = tmp_path / "source"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    video = movie / "movie.mkv"
    video.write_bytes(b"v1")
    first = resolve_source_unit(str(source), str(video))

    video.write_bytes(b"version-two")
    second = resolve_source_unit(str(source), str(video))

    assert first.unit_id != second.unit_id


def test_folder_waits_until_every_task_succeeds_then_moves_whole_folder(tmp_path: Path):
    source = tmp_path / "source"
    recycle = tmp_path / "recycle"
    movie = source / "Forrest Gump"
    movie.mkdir(parents=True)
    recycle.mkdir()
    first_file = movie / "disc1.mkv"
    second_file = movie / "disc2.mkv"
    first_file.write_bytes(b"1")
    second_file.write_bytes(b"2")
    conn = init_db(str(tmp_path / "app.db"))

    unit = register_source_unit(conn, str(source), str(first_file))
    task1 = create_task(conn, str(first_file), first_file.name, source_unit_id=unit.unit_id)
    task2 = create_task(conn, str(second_file), second_file.name, source_unit_id=unit.unit_id)
    update_task(conn, task1["task_id"], status="SUCCESS", stage="DONE", import_success=1)

    coordinator = SourceUnitCoordinator(conn, {
        "source_dir": str(source),
        "source_policy": {"mode": "recycle_source_unit", "recycle_dir": str(recycle), "unit_settle_seconds": 0},
    })
    waiting = coordinator.try_recycle(unit.unit_id)
    assert waiting.state == "WAITING"
    assert movie.exists()

    update_task(conn, task2["task_id"], status="SUCCESS", stage="DONE", import_success=1)
    recycled = coordinator.try_recycle(unit.unit_id)
    assert recycled.state == "RECYCLED"
    assert not movie.exists()
    assert any(path.name == "Forrest Gump" for path in recycle.rglob("Forrest Gump"))


def test_changed_snapshot_blocks_recycle(tmp_path: Path):
    source = tmp_path / "source"
    recycle = tmp_path / "recycle"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    recycle.mkdir()
    video = movie / "movie.mkv"
    video.write_bytes(b"video")
    conn = init_db(str(tmp_path / "app.db"))
    unit = register_source_unit(conn, str(source), str(video))
    task = create_task(conn, str(video), video.name, source_unit_id=unit.unit_id)
    update_task(conn, task["task_id"], status="SUCCESS", stage="DONE", import_success=1)
    (movie / "late-file.txt").write_text("still downloading", encoding="utf-8")

    result = SourceUnitCoordinator(conn, {
        "source_dir": str(source),
        "source_policy": {"mode": "recycle_source_unit", "recycle_dir": str(recycle), "unit_settle_seconds": 0},
    }).try_recycle(unit.unit_id)

    assert result.state == "BLOCKED"
    assert "发生变化" in result.message
    assert movie.exists()


def test_source_unit_with_symlink_is_rejected(tmp_path: Path):
    source = tmp_path / "source"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    video = movie / "movie.mkv"
    video.write_bytes(b"video")
    (movie / "outside-link.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="符号链接"):
        resolve_source_unit(str(source), str(video))


def test_loose_root_partial_failure_can_resume_without_touching_source_root(
    tmp_path: Path, monkeypatch,
):
    source = tmp_path / "source"
    recycle = tmp_path / "recycle"
    source.mkdir()
    recycle.mkdir()
    first = source / "a.mkv"
    second = source / "b.mkv"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    conn = init_db(str(tmp_path / "app.db"))
    unit = register_source_unit(conn, str(source), str(first))
    for path in (first, second):
        task = create_task(conn, str(path), path.name, source_unit_id=unit.unit_id)
        update_task(conn, task["task_id"], status="SUCCESS", stage="DONE", import_success=1)
    config = {
        "source_dir": str(source),
        "temp_dir": str(tmp_path),
        "library_root": str(tmp_path),
        "video_extensions": [".mkv"],
        "source_policy": {"mode": "recycle_source_unit", "recycle_dir": str(recycle), "unit_settle_seconds": 0},
    }
    calls = []

    def fail_second(path, *_args, **_kwargs):
        calls.append(path)
        if len(calls) == 2:
            return False, "", "模拟第二个文件回收失败"
        Path(path).unlink()
        return True, str(recycle / Path(path).name), "ok"

    monkeypatch.setattr(
        "media_importer.features.source_files.source_units.move_to_recycle", fail_second
    )
    first_try = SourceUnitCoordinator(conn, config).try_recycle(unit.unit_id)
    assert first_try.state == "BLOCKED"
    assert source.exists() and not first.exists() and second.exists()

    def succeed(path, *_args, **_kwargs):
        Path(path).unlink()
        return True, str(recycle / Path(path).name), "ok"

    monkeypatch.setattr(
        "media_importer.features.source_files.source_units.move_to_recycle", succeed
    )
    second_try = SourceUnitCoordinator(conn, config).try_recycle(unit.unit_id)
    assert second_try.state == "RECYCLED"
    assert source.exists() and not second.exists()


def test_incomplete_download_marker_keeps_entire_folder(tmp_path: Path):
    source = tmp_path / "source"
    recycle = tmp_path / "recycle"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    recycle.mkdir()
    video = movie / "movie.mkv"
    video.write_bytes(b"video")
    (movie / "movie.mkv.aria2").write_bytes(b"state")
    conn = init_db(str(tmp_path / "app.db"))
    unit = register_source_unit(conn, str(source), str(video))
    task = create_task(conn, str(video), video.name, source_unit_id=unit.unit_id)
    update_task(conn, task["task_id"], status="SUCCESS", stage="DONE", import_success=1)

    result = SourceUnitCoordinator(conn, {
        "source_dir": str(source),
        "source_policy": {
            "mode": "recycle_source_unit",
            "recycle_dir": str(recycle),
            "unit_settle_seconds": 0,
        },
    }).try_recycle(unit.unit_id)

    assert result.state == "WAITING"
    assert "未完成下载" in result.message
    assert movie.exists()
