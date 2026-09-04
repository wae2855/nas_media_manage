import hashlib
from pathlib import Path

import pytest

from media_importer.features.import_flow.services import file_operations
from media_importer.infrastructure.filesystem.safety import (
    TARGET_CHECKSUM_MISMATCH,
    safe_delete_bundle_temporary,
    safe_move,
    verified_copy,
)


def test_verified_copy_publishes_identical_bytes(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    payload = b"verified-transfer" * 100_000
    source.write_bytes(payload)

    ok, _message = verified_copy(str(source), str(target), remove_source=True)

    assert ok is True
    assert target.read_bytes() == payload
    assert not source.exists()
    assert not (target_dir / "movie.bin.copying").exists()


def test_verified_copy_resumes_only_matching_prefix(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    payload = b"abc123" * 400_000
    source.write_bytes(payload)
    partial = target_dir / "movie.bin.copying"
    partial.write_bytes(payload[:1_100_000])

    ok, _message = verified_copy(str(source), str(target))

    assert ok is True
    assert target.read_bytes() == payload


def test_verified_copy_rebuilds_mismatched_partial(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    payload = b"right" * 300_000
    source.write_bytes(payload)
    (target_dir / "movie.bin.copying").write_bytes(b"wrong" * 50_000)

    ok, _message = verified_copy(str(source), str(target))

    assert ok is True
    assert target.read_bytes() == payload


def test_safe_move_does_not_recreate_missing_mount_path(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"data")
    missing_mount = tmp_path / "gone-mount"
    target = missing_mount / "movie.bin"

    ok, message = safe_move(
        str(source),
        str(target),
        allowed_base_dirs=[str(tmp_path), str(missing_mount)],
    )

    assert ok is False
    assert "拒绝自动创建" in message
    assert source.exists()
    assert not missing_mount.exists()


def test_path_boundary_does_not_accept_similar_prefix(tmp_path):
    allowed = tmp_path / "media"
    sibling = tmp_path / "media-other"
    allowed.mkdir()
    sibling.mkdir()
    source = allowed / "source.bin"
    source.write_bytes(b"data")

    ok, message = safe_move(
        str(source),
        str(sibling / "target.bin"),
        allowed_base_dirs=[str(allowed)],
    )

    assert ok is False
    assert "目标路径安全检查失败" in message
    assert source.exists()


def test_source_change_during_copy_keeps_source_and_does_not_publish(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    source.write_bytes(b"a" * (2 * 1024 * 1024))
    changed = False

    def mutate_after_copy(copied, total):
        nonlocal changed
        if copied == total and not changed:
            with source.open("ab") as handle:
                handle.write(b"changed")
            changed = True

    ok, message = verified_copy(
        str(source),
        str(target),
        remove_source=True,
        progress_callback=mutate_after_copy,
    )

    assert ok is False
    assert "源文件发生变化" in message
    assert source.exists()
    assert not target.exists()


def test_source_change_during_hash_is_reported_before_target_checksum(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    source.write_bytes(b"a" * (2 * 1024 * 1024))
    changed = False

    def mutate_during_source_hash(phase, completed, _total):
        nonlocal changed
        if phase == "verify_source" and completed >= 1024 * 1024 and not changed:
            with source.open("ab") as handle:
                handle.write(b"changed-during-hash")
            changed = True

    ok, message = verified_copy(
        str(source),
        str(target),
        phase_callback=mutate_during_source_hash,
    )

    assert ok is False
    assert message == "完整性校验期间源文件发生变化，保留源文件并等待重试"
    assert "目标临时文件 SHA-256" not in message
    assert source.exists()
    assert not target.exists()


def _movie_import_kwargs(source: Path, library: Path) -> dict:
    return {
        "video_path": str(source),
        "subtitle_paths": [],
        "import_dir": str(library),
        "scraped_info": {"title_cn": "测试电影", "year": "2026", "media_type": "movie"},
        "filename_templates": {"movie": "{title_cn}.{year}.{ext}"},
        "allowed_base_dirs": [str(source.parent), str(library)],
        "final_filename": "测试电影.2026.mkv",
        "task_id": "checksum-retry",
    }


def test_bundle_copy_retries_one_target_checksum_mismatch_from_empty_partial(
    tmp_path, monkeypatch
):
    source_dir = tmp_path / "source"
    library = tmp_path / "library"
    source_dir.mkdir()
    library.mkdir()
    source = source_dir / "movie.mkv"
    payload = b"stable-source"
    source.write_bytes(payload)
    calls = []

    def flaky_copy(source_path, destination, **kwargs):
        calls.append(destination)
        if len(calls) == 1:
            Path(destination + ".copying").write_bytes(b"bad-target-read")
            return False, TARGET_CHECKSUM_MISMATCH
        Path(destination).write_bytes(Path(source_path).read_bytes())
        callback = kwargs.get("digest_callback")
        if callback:
            callback(hashlib.sha256(payload).hexdigest())
        return True, "ok"

    monkeypatch.setattr(file_operations, "verified_copy", flaky_copy)

    result = file_operations.move_to_import(**_movie_import_kwargs(source, library))

    assert len(calls) == 2
    assert Path(result["video"]).read_bytes() == payload
    assert source.read_bytes() == payload
    assert not list(library.glob("*.copying"))


def test_bundle_copy_stops_after_two_target_checksum_mismatches(
    tmp_path, monkeypatch
):
    source_dir = tmp_path / "source"
    library = tmp_path / "library"
    source_dir.mkdir()
    library.mkdir()
    source = source_dir / "movie.mkv"
    source.write_bytes(b"stable-source")
    calls = []

    def always_bad(_source_path, destination, **_kwargs):
        calls.append(destination)
        Path(destination + ".copying").write_bytes(b"bad-target-read")
        return False, TARGET_CHECKSUM_MISMATCH

    monkeypatch.setattr(file_operations, "verified_copy", always_bad)

    with pytest.raises(IOError, match="安全重试一次仍不一致"):
        file_operations.move_to_import(**_movie_import_kwargs(source, library))

    assert len(calls) == 2
    assert source.exists()
    assert not (library / "测试电影.2026.mkv").exists()
    assert not list(library.glob("*.copying"))


def test_bundle_copy_does_not_retry_when_source_changes(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    library = tmp_path / "library"
    source_dir.mkdir()
    library.mkdir()
    source = source_dir / "movie.mkv"
    source.write_bytes(b"changing-source")
    calls = []

    def source_changed(_source_path, destination, **_kwargs):
        calls.append(destination)
        Path(destination + ".copying").write_bytes(b"partial")
        return False, "完整性校验期间源文件发生变化，保留源文件并等待重试"

    monkeypatch.setattr(file_operations, "verified_copy", source_changed)

    with pytest.raises(IOError, match="完整性校验期间源文件发生变化"):
        file_operations.move_to_import(**_movie_import_kwargs(source, library))

    assert len(calls) == 1
    assert source.exists()
    assert not (library / "测试电影.2026.mkv").exists()
    assert not list(library.glob("*.copying"))


def test_bundle_temporary_cleanup_allows_large_owned_sparse_file(tmp_path):
    stage = tmp_path / "Movie.mkv.task-1.1.bundle.tmp"
    partial = Path(str(stage) + ".copying")
    with partial.open("wb") as handle:
        handle.truncate(51 * 1024 * 1024 * 1024)

    removed, message = safe_delete_bundle_temporary(
        str(partial), [str(tmp_path)]
    )

    assert removed is True, message
    assert not partial.exists()


def test_bundle_temporary_cleanup_rejects_non_bundle_file(tmp_path):
    unrelated = tmp_path / "Movie.mkv.copying"
    unrelated.write_bytes(b"do-not-delete")

    removed, message = safe_delete_bundle_temporary(
        str(unrelated), [str(tmp_path)]
    )

    assert removed is False
    assert "不是允许清理" in message
    assert unrelated.exists()


def test_bundle_temporary_cleanup_rejects_symlink(tmp_path):
    victim = tmp_path / "victim.bin"
    victim.write_bytes(b"keep")
    partial = tmp_path / "Movie.mkv.task-1.1.bundle.tmp.copying"
    partial.symlink_to(victim)

    removed, message = safe_delete_bundle_temporary(
        str(partial), [str(tmp_path)]
    )

    assert removed is False
    assert "独立普通文件" in message
    assert partial.is_symlink()
    assert victim.read_bytes() == b"keep"


# Requirement: REQ-20260901-010051
def test_verified_copy_reports_truthful_transfer_and_verification_phases(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    payload = b"progress" * 300_000
    source.write_bytes(payload)
    (target_dir / "movie.bin.copying").write_bytes(payload[:1_100_000])
    events = []

    ok, _message = verified_copy(
        str(source),
        str(target),
        phase_callback=lambda phase, completed, total: events.append(
            (phase, completed, total)
        ),
    )

    assert ok is True
    phases = [event[0] for event in events]
    assert phases.index("resume_check") < phases.index("transfer")
    assert phases.index("transfer") < phases.index("verify_source")
    assert phases.index("verify_source") < phases.index("verify_target")
    assert phases.index("verify_target") < phases.index("publish")
    for phase in ("transfer", "verify_source", "verify_target", "publish"):
        phase_events = [event for event in events if event[0] == phase]
        assert phase_events[-1][1] == phase_events[-1][2]
