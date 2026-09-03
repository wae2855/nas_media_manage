import json
import os
from pathlib import Path
from types import SimpleNamespace

from media_importer.core.config_view import ConfigView
from media_importer.core.db.connection import init_db
from media_importer.core.db.source_unit_repo import get_source_unit
from media_importer.core.db.task_repo import create_task, update_task
from media_importer.features.source_cleaning.cleaner import SourceCleaner
from media_importer.features.source_files.permanent_delete import (
    PermanentDeleteResult,
    permanently_delete_source_members,
    resume_permanent_source_delete,
)
from media_importer.features.source_files.source_units import (
    SourceUnitCoordinator,
    register_source_unit,
)


def test_source_disposal_defaults_to_local_recycle():
    view = ConfigView.from_dict({"source_policy": {"mode": "recycle_source_unit"}})

    assert view.source_policy.disposal_mode == "local_recycle"


# Requirement: REQ-20260901-020743 / ADR-0019
def test_permanent_delete_claims_source_and_never_touches_target_library(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "library"
    ledgers = tmp_path / "data" / "source_delete_ledgers"
    source.mkdir()
    target.mkdir()
    movie = source / "Movie"
    movie.mkdir()
    (movie / "movie.mkv").write_bytes(b"new")
    (movie / "movie.zh.srt").write_text("subtitle", encoding="utf-8")
    existing = target / "Movie.mkv"
    existing.write_bytes(b"library-must-survive")

    result = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="task-001",
        ledger_dir=str(ledgers),
        protected_roots=[str(target)],
    )

    assert result.ok is True
    assert result.state == "DELETED"
    assert not movie.exists()
    assert source.exists()
    assert existing.read_bytes() == b"library-must-survive"
    assert not list(source.glob(".nas-media-delete-*.deleting"))
    assert list(ledgers.glob("source-delete-task-001.jsonl.done-*"))


# Requirement: REQ-20260901-020743 / ADR-0019
def test_permanent_delete_rejects_symlink_at_any_depth_before_claim(tmp_path: Path):
    source = tmp_path / "source"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    video = movie / "movie.mkv"
    video.write_bytes(b"video")
    outside = tmp_path / "outside.txt"
    outside.write_text("keep", encoding="utf-8")
    (movie / "link.txt").symlink_to(outside)

    result = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="task-symlink",
        ledger_dir=str(tmp_path / "ledgers"),
    )

    assert result.ok is False
    assert "符号链接" in result.message
    assert video.exists()
    assert outside.read_text(encoding="utf-8") == "keep"
    assert not list(source.glob(".nas-media-delete-*.deleting"))


# Requirement: REQ-20260901-020743 / ADR-0019
def test_claim_failure_restores_all_members_before_any_delete(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    source.mkdir()
    first = source / "a.mkv"
    second = source / "b.mkv"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    original_rename = os.rename
    failed_once = False

    def fail_second_claim(src, dst, *args, **kwargs):
        nonlocal failed_once
        if src == str(second) and not failed_once:
            failed_once = True
            raise OSError("simulated claim failure")
        return original_rename(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "rename", fail_second_claim)
    result = permanently_delete_source_members(
        [str(first), str(second)],
        source_root=str(source),
        operation_id="task-claim-failure",
        ledger_dir=str(tmp_path / "ledgers"),
    )

    assert result.ok is False
    assert result.state == "BLOCKED"
    assert first.read_bytes() == b"a"
    assert second.read_bytes() == b"b"
    assert not list(source.glob(".nas-media-delete-*.deleting"))

    resumed = resume_permanent_source_delete(
        result.ledger_path,
        source_root=str(source),
    )

    assert resumed.state == "BLOCKED"
    assert "安全回退" in resumed.message
    assert first.read_bytes() == b"a"
    assert second.read_bytes() == b"b"
    assert not Path(result.ledger_path).exists()
    assert list((tmp_path / "ledgers").glob("*.rolled_back-*"))


# Requirement: REQ-20260901-020743 / ADR-0019
def test_permanent_delete_rejects_nested_mount_device_before_claim(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    movie = source / "Movie"
    nested_mount = movie / "mounted-cloud"
    nested_mount.mkdir(parents=True)
    video = nested_mount / "remote.mkv"
    video.write_bytes(b"remote-must-survive")
    from media_importer.features.source_files import permanent_delete as module
    real_lstat = module.os.lstat

    def different_device_for_nested_mount(path, *args, **kwargs):
        result = real_lstat(path, *args, **kwargs)
        if os.fspath(path).startswith(str(nested_mount)):
            return SimpleNamespace(
                st_mode=result.st_mode,
                st_dev=result.st_dev + 1,
                st_ino=result.st_ino,
                st_size=result.st_size,
                st_mtime_ns=result.st_mtime_ns,
            )
        return result

    monkeypatch.setattr(module.os, "lstat", different_device_for_nested_mount)
    result = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="task-nested-mount",
        ledger_dir=str(tmp_path / "ledgers"),
    )

    assert result.state == "BLOCKED"
    assert "嵌套挂载点" in result.message
    assert video.read_bytes() == b"remote-must-survive"
    assert not list(source.glob(".nas-media-delete-*.deleting"))


# Requirement: REQ-20260901-020743 / ADR-0019
def test_resume_rejects_claim_path_outside_task_tombstone(tmp_path: Path):
    source = tmp_path / "source"
    ledgers = tmp_path / "ledgers"
    tombstone = source / ".nas-media-delete-task-ledger.deleting"
    source.mkdir()
    ledgers.mkdir()
    tombstone.mkdir()
    original = source / "movie.mkv"
    original.write_bytes(b"source")
    from media_importer.features.source_files import permanent_delete as module
    snapshot = module._snapshot_entry(str(original))
    original.unlink()
    outside = tmp_path / "outside-sentinel.mkv"
    outside.write_bytes(b"outside-must-survive")
    tombstone_stat = tombstone.stat()
    ledger = ledgers / "source-delete-task-ledger.jsonl"
    events = [
        {
            "state": "PREPARED",
            "source_root": str(source),
            "tombstone": str(tombstone),
            "tombstone_device": tombstone_stat.st_dev,
            "tombstone_inode": tombstone_stat.st_ino,
            "members": [{"original_path": str(original), "snapshot": snapshot}],
        },
        {
            "state": "MEMBER_CLAIMED",
            "original_path": str(original),
            "claimed_path": str(outside),
        },
    ]
    ledger.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    ledger.chmod(0o600)

    resumed = resume_permanent_source_delete(
        str(ledger),
        source_root=str(source),
    )

    assert resumed.state == "BLOCKED"
    assert "越界的隔离区路径" in resumed.message
    assert outside.read_bytes() == b"outside-must-survive"
    assert not original.exists()


# Requirement: REQ-20260901-020743 / ADR-0019
def test_delete_failure_resumes_only_the_claimed_tombstone(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "library"
    ledgers = tmp_path / "ledgers"
    source.mkdir()
    target.mkdir()
    movie = source / "Movie"
    movie.mkdir()
    (movie / "movie.mkv").write_bytes(b"source")
    sentinel = target / "sentinel.mkv"
    sentinel.write_bytes(b"target-safe")
    from media_importer.features.source_files import permanent_delete as module
    real_finish = module._finish_tombstone

    monkeypatch.setattr(
        module,
        "_finish_tombstone",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("simulated interruption")),
    )
    first = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="task-resume",
        ledger_dir=str(ledgers),
        protected_roots=[str(target)],
    )

    assert first.state == "PARTIAL"
    assert not movie.exists()
    tombstones = list(source.glob(".nas-media-delete-*.deleting"))
    assert len(tombstones) == 1
    assert sentinel.read_bytes() == b"target-safe"

    monkeypatch.setattr(module, "_finish_tombstone", real_finish)
    resumed = resume_permanent_source_delete(
        first.ledger_path,
        source_root=str(source),
        protected_roots=[str(target)],
    )

    assert resumed.state == "DELETED"
    assert not tombstones[0].exists()
    assert sentinel.read_bytes() == b"target-safe"


# Requirement: REQ-20260901-020743 / ADR-0019
def test_foreign_file_in_tombstone_blocks_delete_and_is_not_removed(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    ledgers = tmp_path / "ledgers"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    (movie / "movie.mkv").write_bytes(b"source")
    from media_importer.features.source_files import permanent_delete as module
    real_append = module._append_ledger

    def inject_after_claim(path, event, **kwargs):
        real_append(path, event, **kwargs)
        if event.get("state") == "CLAIMED":
            tombstone = next(source.glob(".nas-media-delete-*.deleting"))
            (tombstone / "foreign.txt").write_text("do-not-delete", encoding="utf-8")

    monkeypatch.setattr(module, "_append_ledger", inject_after_claim)
    result = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="task-foreign",
        ledger_dir=str(ledgers),
    )

    assert result.state == "PARTIAL"
    foreign = next(source.glob(".nas-media-delete-*.deleting")) / "foreign.txt"
    assert foreign.read_text(encoding="utf-8") == "do-not-delete"


def _simulate_remote_mount(monkeypatch, module, source: Path, *, mount_source="remote:vault"):
    monkeypatch.setattr(
        module,
        "_mount_evidence",
        lambda _path: {
            "realpath": str(source.resolve()),
            "filesystem_type": "fuse.rclone",
            "mount_point": str(source.resolve()),
            "mount_source": mount_source,
            "locality": "remote",
        },
    )


# Requirement: REQ-20260902-222141 / ADR-0019
def test_remote_delete_accepts_virtual_inode_change_after_claim(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "library"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    target.mkdir()
    (movie / "movie.mkv").write_bytes(b"source")
    sentinel = target / "sentinel.mkv"
    sentinel.write_bytes(b"target-safe")
    from media_importer.features.source_files import permanent_delete as module

    _simulate_remote_mount(monkeypatch, module, source)
    real_snapshot = module._snapshot_entry

    def unstable_remote_inode(path, **kwargs):
        snapshot = real_snapshot(path, **kwargs)
        if ".nas-media-delete-" in os.fspath(path):
            snapshot["inode"] = int(snapshot["inode"]) + 999_999
            for child in snapshot.get("children", []):
                child["inode"] = int(child["inode"]) + 999_999
        return snapshot

    monkeypatch.setattr(module, "_snapshot_entry", unstable_remote_inode)
    result = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="remote-inode-change",
        ledger_dir=str(tmp_path / "ledgers"),
        protected_roots=[str(target)],
    )

    assert result.state == "DELETED"
    assert not movie.exists()
    assert sentinel.read_bytes() == b"target-safe"


# Requirement: REQ-20260902-222141 / ADR-0019
def test_local_delete_still_blocks_inode_change_after_claim(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    (movie / "movie.mkv").write_bytes(b"source")
    from media_importer.features.source_files import permanent_delete as module

    real_snapshot = module._snapshot_entry

    def changed_inode(path, **kwargs):
        snapshot = real_snapshot(path, **kwargs)
        if ".nas-media-delete-" in os.fspath(path):
            snapshot["inode"] = int(snapshot["inode"]) + 1
        return snapshot

    monkeypatch.setattr(module, "_snapshot_entry", changed_inode)
    result = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="local-inode-change",
        ledger_dir=str(tmp_path / "ledgers"),
    )

    assert result.state == "PARTIAL"
    assert "成员变化" in result.message
    assert next(source.glob(".nas-media-delete-*.deleting")).exists()


# Requirement: REQ-20260902-222141 / ADR-0019
def test_old_remote_ledger_resumes_partial_delete_without_recopy(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    (movie / "movie.mkv").write_bytes(b"source")
    (movie / "poster.jpg").write_bytes(b"poster")
    ledgers = tmp_path / "ledgers"
    from media_importer.features.source_files import permanent_delete as module

    _simulate_remote_mount(monkeypatch, module, source)
    real_finish = module._finish_tombstone
    monkeypatch.setattr(
        module,
        "_finish_tombstone",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("simulated power loss")),
    )
    first = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="old-remote-ledger",
        ledger_dir=str(ledgers),
    )
    assert first.state == "PARTIAL"
    events = [json.loads(line) for line in Path(first.ledger_path).read_text().splitlines()]
    events[0].pop("identity_mode", None)
    events[0].pop("source_mount", None)
    Path(first.ledger_path).write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    Path(first.ledger_path).chmod(0o600)

    monkeypatch.setattr(module, "_finish_tombstone", real_finish)
    resumed = resume_permanent_source_delete(
        first.ledger_path,
        source_root=str(source),
    )

    assert resumed.state == "DELETED"
    assert not movie.exists()
    assert not list(source.glob(".nas-media-delete-*.deleting"))


# Requirement: REQ-20260902-222141 / ADR-0019
def test_remote_partial_unlink_resumes_remaining_members(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    target = tmp_path / "library"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    target.mkdir()
    (movie / "a.mkv").write_bytes(b"first")
    (movie / "b.srt").write_bytes(b"second")
    sentinel = target / "sentinel.mkv"
    sentinel.write_bytes(b"target-safe")
    from media_importer.features.source_files import permanent_delete as module

    _simulate_remote_mount(monkeypatch, module, source)
    real_unlink = module.os.unlink
    unlink_calls = 0

    def interrupt_second_unlink(path, *args, **kwargs):
        nonlocal unlink_calls
        unlink_calls += 1
        if unlink_calls == 2:
            raise OSError("simulated process interruption")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(module.os, "unlink", interrupt_second_unlink)
    first = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="remote-partial-unlink",
        ledger_dir=str(tmp_path / "ledgers"),
        protected_roots=[str(target)],
    )
    assert first.state == "PARTIAL"
    assert "simulated process interruption" in first.message
    assert sentinel.read_bytes() == b"target-safe"

    monkeypatch.setattr(module.os, "unlink", real_unlink)
    resumed = resume_permanent_source_delete(
        first.ledger_path,
        source_root=str(source),
        protected_roots=[str(target)],
    )

    assert resumed.state == "DELETED"
    assert not movie.exists()
    assert not list(source.glob(".nas-media-delete-*.deleting"))
    assert sentinel.read_bytes() == b"target-safe"


# Requirement: REQ-20260902-222141 / ADR-0019
def test_remote_resume_blocks_when_mount_identity_changes(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    (movie / "movie.mkv").write_bytes(b"source")
    from media_importer.features.source_files import permanent_delete as module

    _simulate_remote_mount(monkeypatch, module, source, mount_source="remote:before")
    real_finish = module._finish_tombstone
    monkeypatch.setattr(
        module,
        "_finish_tombstone",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("simulated interruption")),
    )
    first = permanently_delete_source_members(
        [str(movie)],
        source_root=str(source),
        operation_id="remote-mount-change",
        ledger_dir=str(tmp_path / "ledgers"),
    )
    tombstone = next(source.glob(".nas-media-delete-*.deleting"))

    monkeypatch.setattr(module, "_finish_tombstone", real_finish)
    _simulate_remote_mount(monkeypatch, module, source, mount_source="remote:after")
    resumed = resume_permanent_source_delete(first.ledger_path, source_root=str(source))

    assert resumed.state == "BLOCKED"
    assert "挂载身份发生变化" in resumed.message
    assert tombstone.exists()


# Requirement: REQ-20260902-222141 / ADR-0019
def test_source_unit_preserves_specific_resume_block_reason(tmp_path: Path, monkeypatch):
    source = tmp_path / "source"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    video = movie / "movie.mkv"
    video.write_bytes(b"source")
    data = tmp_path / "data"
    conn = init_db(str(tmp_path / "app.db"))
    unit = register_source_unit(conn, str(source), str(video))
    ledger_dir = data / "source_delete_ledgers"
    ledger_dir.mkdir(parents=True)
    (ledger_dir / f"source-delete-{unit.unit_id}.jsonl").write_text("active", encoding="utf-8")
    from media_importer.features.source_files import source_units as module

    exact_reason = "来源删除恢复检查失败: 来源挂载身份发生变化: mount_source"
    monkeypatch.setattr(
        module,
        "resume_permanent_source_delete",
        lambda *_args, **_kwargs: PermanentDeleteResult(False, "BLOCKED", exact_reason),
    )
    result = SourceUnitCoordinator(conn, {
        "_data_dir": str(data),
        "source_dir": str(source),
        "source_policy": {
            "mode": "recycle_source_unit",
            "disposal_mode": "permanent_delete",
        },
    }).try_recycle(unit.unit_id)

    stored = get_source_unit(conn, unit.unit_id)
    assert result.state == "BLOCKED"
    assert result.message == exact_reason
    assert stored["last_error"] == exact_reason
    assert "不存在" not in stored["last_error"]


# Requirement: REQ-20260901-020743 / ADR-0019
def test_source_unit_permanent_mode_deletes_completed_folder_without_recycle_copy(tmp_path: Path):
    source = tmp_path / "source"
    recycle = tmp_path / "recycle"
    data = tmp_path / "data"
    movie = source / "Movie"
    movie.mkdir(parents=True)
    recycle.mkdir()
    video = movie / "movie.mkv"
    video.write_bytes(b"video")
    conn = init_db(str(tmp_path / "app.db"))
    unit = register_source_unit(conn, str(source), str(video))
    task = create_task(conn, str(video), video.name, source_unit_id=unit.unit_id)
    update_task(conn, task["task_id"], status="SUCCESS", stage="DONE", import_success=1)

    result = SourceUnitCoordinator(conn, {
        "_data_dir": str(data),
        "source_dir": str(source),
        "video_extensions": [".mkv"],
        "source_policy": {
            "mode": "recycle_source_unit",
            "disposal_mode": "permanent_delete",
            "recycle_dir": str(recycle),
            "unit_settle_seconds": 0,
        },
    }).try_recycle(unit.unit_id)

    assert result.state == "DELETED"
    assert "永久删除" in result.message
    assert not movie.exists()
    assert list(recycle.iterdir()) == []


# Requirement: REQ-20260901-020743 / ADR-0019
def test_source_cleaner_permanent_mode_deletes_only_classified_junk(tmp_path: Path):
    source = tmp_path / "source"
    target = tmp_path / "library"
    data = tmp_path / "data"
    source.mkdir()
    target.mkdir()
    video = source / "movie.mkv"
    junk = source / "ad.txt"
    video.write_bytes(b"video")
    junk.write_text("ad", encoding="utf-8")
    existing = target / "existing.mkv"
    existing.write_bytes(b"keep")
    cleaner = SourceCleaner({
        "_data_dir": str(data),
        "source_dir": str(source),
        "library_roots": [{"id": "movies", "path": str(target), "enabled": True}],
        "video_extensions": [".mkv"],
        "subtitle_extensions": [".srt"],
        "source_policy": {
            "mode": "preserve_media",
            "disposal_mode": "permanent_delete",
            "recycle_dir": str(tmp_path / "unused-recycle"),
        },
        "source_cleaner": {
            "enabled": True,
            "cleanup_mode": "media_and_related",
            "delete_extensions": [".txt"],
            "protect_extensions": [],
            "blacklist_patterns": [],
            "junk_video_max_size_mb": 0,
            "cleanup_empty_dirs": False,
        },
    })

    record = cleaner.execute()

    assert record["disposal_mode"] == "permanent_delete"
    assert record["total_files"] == 1
    assert video.read_bytes() == b"video"
    assert not junk.exists()
    assert existing.read_bytes() == b"keep"
