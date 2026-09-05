"""Real SQLite/filesystem regressions for historical task coverage.

Requirement: REQ-20260905-231945
"""

import hashlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from media_importer.core.task_manager import TaskManager
from media_importer.features.source_files.source_units import (
    SourceUnitCoordinator,
    register_source_unit,
)
from media_importer.features.tasks.disposition_service import request_task_disposition
from media_importer.infrastructure.db import (
    create_subtitles,
    create_task,
    get_task,
    init_db,
    update_source_unit,
    update_task,
)


@pytest.fixture
def series(tmp_path):
    source = tmp_path / "source"
    folder = source / "北海鲸梦"
    folder.mkdir(parents=True)
    library = tmp_path / "library"
    library.mkdir()
    recycle = tmp_path / "recycle"
    recycle.mkdir()
    config = {
        "source_dir": str(source), "_data_dir": str(tmp_path / "data"),
        "library_roots": [{"id": "tv", "path": str(library), "enabled": True}],
        "source_policy": {"mode": "recycle_source_unit", "recycle_dir": str(recycle),
                          "unit_settle_seconds": 0},
    }
    videos = [folder / f"北海鲸梦.S01E{n:02d}.mp4" for n in range(1, 6)]
    for n, path in enumerate(videos):
        path.write_bytes(f"episode-{n}".encode())
    conn = init_db(str(tmp_path / "app.db"))
    unit = register_source_unit(conn, str(source), str(videos[0]))
    successes = []
    for path in videos:
        dest = library / path.name
        dest.write_bytes(path.read_bytes())
        task = create_task(conn, str(path), path.name, source_unit_id=unit.unit_id)
        update_task(conn, task["task_id"], status="SUCCESS", stage="DONE", import_success=1,
                    import_video_path=str(dest), bundle_committed=1, bundle_state="COMMITTED",
                    source_cleanup_status="WAITING", source_disposition="pending",
                    bundle_manifest=[{"kind": "video", "source_path": str(path),
                                      "dest_path": str(dest), "state": "published",
                                      "transfer_mode": "copy",
                                      "fingerprint": hashlib.sha256(path.read_bytes()).hexdigest()}])
        successes.append(task["task_id"])
    yield conn, config, unit, videos, successes
    conn.close()


def history(series, *, index=2, status="SKIPPED", stage="DONE", **fields):
    conn, _, unit, videos, _ = series
    task = create_task(conn, str(videos[index]), videos[index].name, source_unit_id=unit.unit_id)
    update_task(conn, task["task_id"], status=status, stage=stage, **fields)
    return task["task_id"]


@pytest.mark.parametrize("mode,expected", [("local_recycle", "RECYCLED"), ("permanent_delete", "DELETED")])
def test_five_successes_cover_two_proven_historical_duplicates(series, mode, expected):
    conn, config, unit, videos, successes = series
    config["source_policy"]["disposal_mode"] = mode
    first = history(series)
    second = history(series, index=4, status="FAILED")
    result = SourceUnitCoordinator(conn, config).try_recycle(unit.unit_id)
    assert result.state == expected, result.message
    assert not videos[0].parent.exists()
    assert get_task(conn, first)["status"] == "SKIPPED"
    assert get_task(conn, second)["status"] == "FAILED"
    assert all(get_task(conn, tid)["source_cleanup_status"] == expected for tid in successes)
    assert "历史" in result.message


@pytest.mark.parametrize("status,stage,fields", [
    ("PENDING", "QUEUED", {}), ("PENDING", "AWAIT_REVIEW", {}),
    ("PENDING", "RUNNING", {}), ("CANCELLED", "DONE", {}),
    ("SKIPPED", "DONE", {"outcome_code": "USER_ABANDONED", "source_disposition": "kept"}),
    ("SKIPPED", "DONE", {"outcome_code": "SOURCE_DISPOSITION_UPDATED", "source_disposition": "kept"}),
])
def test_active_or_explicitly_retained_history_must_block(series, status, stage, fields):
    conn, config, unit, videos, _ = series
    tid = history(series, status=status, stage=stage, **fields)
    result = SourceUnitCoordinator(conn, config).try_recycle(unit.unit_id)
    assert result.state == "WAITING"
    assert videos[2].exists()
    assert videos[2].name in result.message
    if fields:
        assert get_task(conn, tid)["source_disposition"] == "kept"


@pytest.mark.parametrize("change", ["uncommitted", "no_manifest", "missing_target", "wrong_target", "wrong_source", "outside_target"])
def test_duplicate_coverage_requires_verified_current_bundle(series, change):
    conn, config, unit, videos, successes = series
    history(series)
    task = get_task(conn, successes[2])
    target = Path(task["import_video_path"])
    if change == "uncommitted":
        update_task(conn, successes[2], bundle_committed=0)
    elif change == "no_manifest":
        update_task(conn, successes[2], bundle_manifest=[])
    elif change == "missing_target":
        target.unlink()
    elif change == "outside_target":
        manifest = task["bundle_manifest"]
        manifest[0]["dest_path"] = str(videos[2])
        update_task(conn, successes[2], bundle_manifest=manifest)
    else:
        path = target if change == "wrong_target" else videos[2]
        before = path.stat()
        path.write_bytes(b"x" * before.st_size)
        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    result = SourceUnitCoordinator(conn, config).try_recycle(unit.unit_id)
    assert result.state in {"WAITING", "BLOCKED"}
    assert videos[2].exists()


def test_cleanup_result_is_immediately_shared_and_repeat_is_idempotent(series):
    conn, config, unit, _, successes = series
    coordinator = SourceUnitCoordinator(conn, config)
    assert coordinator.try_recycle(unit.unit_id).state == "RECYCLED"
    assert all(get_task(conn, tid)["source_cleanup_status"] == "RECYCLED" for tid in successes)
    assert coordinator.try_recycle(unit.unit_id).state == "RECYCLED"


def test_recovered_committed_task_keeps_source_even_after_background_retry(series):
    conn, config, unit, videos, successes = series
    update_task(conn, successes[0], bundle_state="COMMITTED_RECOVERED",
                source_disposition="kept", source_disposition_message="重启保护保留来源")
    coordinator = SourceUnitCoordinator(conn, config)
    result = coordinator.try_recycle(unit.unit_id)
    assert result.state == "WAITING"
    assert "保留" in result.message
    coordinator.retry_pending()
    assert videos[0].exists()
    assert get_task(conn, successes[0])["source_disposition"] == "kept"
    assert get_task(conn, successes[0])["source_disposition_message"] == "重启保护保留来源"


@pytest.mark.parametrize("change", ["none", "missing", "changed", "omitted"])
def test_history_subtitle_requires_complete_bundle_proof(series, change):
    conn, config, _, videos, successes = series
    subtitle = videos[2].with_suffix(".srt")
    subtitle.write_bytes(b"subtitle")
    # Freeze the new physical generation before registering any of its tasks.
    unit = register_source_unit(conn, config["source_dir"], str(videos[0]))
    for tid in successes:
        update_task(conn, tid, source_unit_id=unit.unit_id)
    amended = (conn, config, unit, videos, successes)
    duplicate = history(amended)
    create_subtitles(conn, duplicate, [str(subtitle)])
    create_subtitles(conn, successes[2], [str(subtitle)])
    target = Path(config["library_roots"][0]["path"]) / subtitle.name
    target.write_bytes(subtitle.read_bytes())
    manifest = get_task(conn, successes[2])["bundle_manifest"]
    if change != "omitted":
        manifest.append({"kind": "subtitle", "source_path": str(subtitle), "dest_path": str(target),
                         "transfer_mode": "copy", "state": "published",
                         "fingerprint": hashlib.sha256(subtitle.read_bytes()).hexdigest()})
        update_task(conn, successes[2], bundle_manifest=manifest)
    if change == "missing":
        target.unlink()
    elif change == "changed":
        target.write_bytes(b"corrupted")
    result = SourceUnitCoordinator(conn, config).try_recycle(unit.unit_id)
    assert result.state == ("RECYCLED" if change == "none" else "WAITING")
    assert subtitle.exists() == (change != "none")


def test_different_generation_success_does_not_cover_history(series):
    conn, config, _, videos, successes = series
    videos[0].write_bytes(b"upstream changed")
    newer = register_source_unit(conn, config["source_dir"], str(videos[0]))
    task = create_task(conn, str(videos[2]), videos[2].name, source_unit_id=newer.unit_id)
    update_task(conn, task["task_id"], status="SKIPPED", stage="DONE")
    assert SourceUnitCoordinator(conn, config).try_recycle(newer.unit_id).state == "WAITING"
    assert all(path.exists() for path in videos)
    assert get_task(conn, successes[2])["status"] == "SUCCESS"


def test_unimported_distinct_episode_is_not_covered_by_other_successes(series):
    conn, config, unit, videos, successes = series
    update_task(conn, successes[1], status="FAILED", stage="DONE", import_success=0)
    history(series)
    assert SourceUnitCoordinator(conn, config).try_recycle(unit.unit_id).state == "WAITING"
    assert all(path.exists() for path in videos)


def test_normal_cleanup_does_not_read_library_contents(series, monkeypatch):
    from media_importer.features.source_files import coverage

    conn, config, unit, _, _ = series

    def forbidden(*args, **kwargs):
        raise AssertionError("No duplicate proof is needed: do not hash the library")

    monkeypatch.setattr(coverage, "hash_file", forbidden)
    coordinator = SourceUnitCoordinator(conn, config)
    assert coordinator.try_recycle(unit.unit_id).state == "RECYCLED"
    assert coordinator.retry_pending() == []


def test_task_state_changed_during_proof_blocks_disposal(series, monkeypatch):
    from media_importer.features.source_files import coverage

    conn, config, unit, videos, _ = series
    duplicate = history(series)
    original = coverage.hash_file

    def race(*args, **kwargs):
        update_task(conn, duplicate, status="PENDING", stage="QUEUED")
        return original(*args, **kwargs)

    monkeypatch.setattr(coverage, "hash_file", race)
    result = SourceUnitCoordinator(conn, config).try_recycle(unit.unit_id)
    assert result.state == "WAITING"
    assert "状态发生变化" in result.message
    assert all(path.exists() for path in videos)


def test_one_unreadable_unit_does_not_abort_later_cleanup(series, monkeypatch):
    from media_importer.features.source_files import source_units

    conn, config, unit, videos, _ = series
    other_folder = Path(config["source_dir"]) / "Other"
    other_folder.mkdir()
    other = other_folder / "other.mp4"
    other.write_bytes(b"other")
    unit2 = register_source_unit(conn, config["source_dir"], str(other))
    task = create_task(conn, str(other), other.name, source_unit_id=unit2.unit_id)
    update_task(conn, task["task_id"], status="SUCCESS", stage="DONE", import_success=1)
    for uid in [unit.unit_id, unit2.unit_id]:
        update_source_unit(conn, uid, state="WAITING")
    original = source_units._snapshot

    def failing_snapshot(path, kind):
        if path == str(videos[0].parent):
            raise PermissionError("test inaccessible source")
        return original(path, kind)

    monkeypatch.setattr(source_units, "_snapshot", failing_snapshot)
    results = SourceUnitCoordinator(conn, config).retry_pending()
    assert {result.state for result in results} == {"BLOCKED", "RECYCLED"}
    assert videos[0].exists()
    assert not other.exists()


@pytest.mark.parametrize("mode", ["local_recycle", "permanent_delete"])
@pytest.mark.parametrize("action", ["keep", "retry"])
def test_cleanup_claim_serializes_user_source_intent(series, monkeypatch, mode, action):
    from media_importer.features.source_files import source_units

    conn, config, unit, videos, _ = series
    config["source_policy"]["disposal_mode"] = mode
    duplicate = history(series)
    original = source_units.list_tasks_for_source_unit
    reached_final_check = threading.Event()
    release_cleanup = threading.Event()
    calls = 0

    def pause_before_claim(*args, **kwargs):
        nonlocal calls
        calls += 1
        rows = original(*args, **kwargs)
        if calls == 2:
            reached_final_check.set()
            assert release_cleanup.wait(2)
        return rows

    monkeypatch.setattr(source_units, "list_tasks_for_source_unit", pause_before_claim)
    manager = TaskManager.__new__(TaskManager)
    manager.conn = conn
    manager.config = config
    manager._lock = threading.RLock()

    with ThreadPoolExecutor(max_workers=2) as pool:
        cleanup_future = pool.submit(SourceUnitCoordinator(conn, config).try_recycle, unit.unit_id)
        assert reached_final_check.wait(2)
        if action == "keep":
            action_future = pool.submit(
                request_task_disposition, manager, config, duplicate, source_disposition="keep"
            )
        else:
            action_future = pool.submit(manager.retry_task, duplicate)
        assert not action_future.done()
        release_cleanup.set()
        cleanup = cleanup_future.result(timeout=5)
        user_result = action_future.result(timeout=5)

    assert cleanup.state == ("RECYCLED" if mode == "local_recycle" else "DELETED")
    if action == "keep":
        assert user_result.code == 409
    else:
        assert user_result is None
    assert not videos[0].parent.exists()
    assert get_task(conn, duplicate)["source_disposition"] != "kept"


def test_terminal_unit_repairs_stale_task_cleanup_result_without_overwriting_retain(series):
    conn, _, unit, _, successes = series
    retained = history(series)
    update_task(conn, retained, outcome_code="USER_ABANDONED", source_disposition="kept",
                source_disposition_message="用户要求保留")
    update_source_unit(conn, unit.unit_id, state="RECYCLED", cleanup_status="DONE")
    result = SourceUnitCoordinator(conn, {}).try_recycle(unit.unit_id)
    assert result.state == "RECYCLED"
    assert all(get_task(conn, tid)["source_cleanup_status"] == "RECYCLED" for tid in successes)
    assert get_task(conn, retained)["source_disposition"] == "kept"
    assert get_task(conn, retained)["source_disposition_message"] == "用户要求保留"


def test_other_source_retry_is_not_blocked_by_long_cleanup_proof(series, monkeypatch):
    from media_importer.features.source_files import source_units

    conn, config, unit, _, _ = series
    history(series)
    other = create_task(conn, "/different/movie.mkv", "movie.mkv")
    update_task(conn, other["task_id"], status="FAILED", stage="DONE")
    entered = threading.Event()
    release = threading.Event()
    original = source_units.list_tasks_for_source_unit
    calls = 0

    def pause(*args, **kwargs):
        nonlocal calls
        calls += 1
        rows = original(*args, **kwargs)
        if calls == 2:
            entered.set()
            assert release.wait(2)
        return rows

    monkeypatch.setattr(source_units, "list_tasks_for_source_unit", pause)
    manager = TaskManager.__new__(TaskManager)
    manager.conn = conn
    manager.config = config
    manager._lock = threading.RLock()
    with ThreadPoolExecutor(max_workers=2) as pool:
        cleanup = pool.submit(SourceUnitCoordinator(conn, config).try_recycle, unit.unit_id)
        assert entered.wait(2)
        retry = pool.submit(manager.retry_task, other["task_id"])
        assert retry.result(timeout=1)["stage"] == "QUEUED"
        release.set()
        assert cleanup.result(timeout=5).state == "RECYCLED"


def test_source_change_after_readiness_is_rechecked_before_disposal(series, monkeypatch):
    from media_importer.features.source_files import source_units

    conn, config, unit, videos, _ = series
    original = source_units.inspect_storage_readiness

    def mutate_after_readiness(*args, **kwargs):
        readiness = original(*args, **kwargs)
        videos[0].write_bytes(b"changed after readiness")
        return readiness

    monkeypatch.setattr(source_units, "inspect_storage_readiness", mutate_after_readiness)
    result = SourceUnitCoordinator(conn, config).try_recycle(unit.unit_id)
    assert result.state == "BLOCKED"
    assert "再次发生变化" in result.message
    assert all(path.exists() for path in videos)
