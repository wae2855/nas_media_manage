import os

import pytest

from media_importer.features.import_flow.services import file_operations
from media_importer.features.import_flow.services.dedup import DedupService
from media_importer.features.import_flow.services.file_operations import move_to_import
from media_importer.features.import_flow.utils import PipelineReviewRequired
from media_importer.infrastructure.filesystem import hash_file


def _write(path, content: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(content)


def _task(import_dir, new_path, filename="Movie.2026.1080p.mkv"):
    return {
        "task_id": "conflict-task",
        "import_path": str(import_dir),
        "video_path": str(new_path),
        "final_filename": filename,
        "scrape_result": {
            "title_en": "Movie",
            "year": "2026",
            "resolution": "1080p",
            "media_type": "movie",
        },
    }


def test_exact_target_conflict_is_read_only_even_when_semantic_detection_disabled(tmp_path):
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    recycle = tmp_path / "recycle"
    library.mkdir()
    temp.mkdir()
    recycle.mkdir()
    existing = library / "Movie.2026.1080p.mkv"
    incoming = temp / "incoming.mkv"
    _write(existing, b"existing-library-bytes")
    _write(incoming, b"incoming-source-bytes")
    before_existing = existing.read_bytes()
    before_incoming = incoming.read_bytes()

    decision = DedupService({
        "duplicate_handling": {"enabled": False, "strategy": "quality"},
    }).check_task(_task(library, incoming))

    assert decision.action == "review"
    assert decision.result["conflict_type"] == "target_path"
    assert decision.result["status"] == "awaiting_user"
    assert decision.result["existing_fingerprint"] == ""
    assert decision.result["existing_stat"]["size"] == existing.stat().st_size
    assert decision.result["new_fingerprint"] == ""
    assert existing.read_bytes() == before_existing
    assert incoming.read_bytes() == before_incoming
    assert list(recycle.iterdir()) == []


def test_replace_fingerprint_is_deferred_until_user_confirms(tmp_path, monkeypatch):
    library = tmp_path / "library"
    incoming = tmp_path / "incoming.mkv"
    library.mkdir()
    existing = library / "Movie.2026.1080p.mkv"
    _write(existing, b"existing-library-bytes")
    _write(incoming, b"incoming-source-bytes")
    calls = []

    monkeypatch.setattr(
        "media_importer.features.import_flow.services.dedup.hash_file",
        lambda path: calls.append(path) or "bound-fingerprint",
    )
    service = DedupService({"duplicate_handling": {"enabled": False}})
    decision = service.check_task(_task(library, incoming))

    assert calls == []
    decision.result["resolved_action"] = "replace_existing"
    prepared = service.prepare_replace(
        {**_task(library, incoming), "dedup_result": decision.result},
        decision.result,
    )
    assert calls == [str(existing)]
    assert prepared["existing_fingerprint"] == "bound-fingerprint"


def test_replace_preparation_rejects_rule_that_now_targets_another_library(tmp_path):
    old_library = tmp_path / "old-library"
    new_library = tmp_path / "new-library"
    incoming = tmp_path / "incoming.mkv"
    old_library.mkdir()
    new_library.mkdir()
    existing = old_library / "Movie.2026.1080p.mkv"
    _write(existing, b"existing-library-bytes")
    _write(incoming, b"incoming-source-bytes")
    service = DedupService({"duplicate_handling": {"enabled": False}})
    conflict = service.check_task(_task(old_library, incoming)).result

    with pytest.raises(PipelineReviewRequired, match="目标片库已变化"):
        service.prepare_replace(
            _task(new_library, incoming),
            {**conflict, "resolved_action": "replace_existing"},
        )

    assert existing.read_bytes() == b"existing-library-bytes"
    assert incoming.read_bytes() == b"incoming-source-bytes"


def test_replace_preparation_rejects_lightweight_snapshot_change(tmp_path):
    library = tmp_path / "library"
    incoming = tmp_path / "incoming.mkv"
    library.mkdir()
    existing = library / "Movie.2026.1080p.mkv"
    _write(existing, b"existing-library-bytes")
    _write(incoming, b"incoming-source-bytes")
    service = DedupService({"duplicate_handling": {"enabled": False}})
    conflict = service.check_task(_task(library, incoming)).result
    existing.write_bytes(b"changed-library-content")

    with pytest.raises(PipelineReviewRequired, match="已发生变化"):
        service.prepare_replace(
            _task(library, incoming),
            {**conflict, "resolved_action": "replace_existing"},
        )

    assert existing.read_bytes() == b"changed-library-content"
    assert incoming.read_bytes() == b"incoming-source-bytes"


def test_existing_subtitle_is_detected_before_large_video_copy(tmp_path):
    library = tmp_path / "library"
    source = tmp_path / "source"
    library.mkdir()
    source.mkdir()
    incoming = source / "Movie.mkv"
    subtitle = source / "Movie.zh.srt"
    existing_subtitle = library / "Movie.2026.1080p.zh.srt"
    _write(incoming, b"large-video-placeholder")
    _write(subtitle, b"new-subtitle")
    _write(existing_subtitle, b"existing-subtitle")

    decision = DedupService({
        "duplicate_handling": {"enabled": False},
        "filename_templates": {"subtitle": "{video_filename}.{lang}.{ext}"},
    }).check_task({
        **_task(library, incoming),
        "subtitle_source_files": [str(subtitle)],
    })

    assert decision.action == "review"
    assert decision.result["conflict_type"] == "target_bundle"
    assert decision.result["replace_allowed"] is False
    assert decision.result["subtitle_conflicts"] == [str(existing_subtitle)]
    assert incoming.read_bytes() == b"large-video-placeholder"


def test_video_conflict_with_incoming_subtitle_blocks_partial_bundle_replace(tmp_path):
    library = tmp_path / "library"
    source = tmp_path / "source"
    library.mkdir()
    source.mkdir()
    incoming = source / "Movie.mkv"
    subtitle = source / "Movie.zh.srt"
    existing = library / "Movie.2026.1080p.mkv"
    _write(incoming, b"new-video")
    _write(subtitle, b"new-subtitle")
    _write(existing, b"existing-video")
    service = DedupService({
        "duplicate_handling": {"enabled": False},
        "filename_templates": {"subtitle": "{video_filename}.{lang}.{ext}"},
    })
    task = {
        **_task(library, incoming),
        "subtitle_source_files": [str(subtitle)],
    }

    decision = service.check_task(task)

    assert decision.action == "review"
    assert decision.result["conflict_type"] == "target_path"
    assert decision.result["replace_allowed"] is False
    assert decision.result["replace_block_reason"] == "incoming_subtitle_bundle"
    with pytest.raises(PipelineReviewRequired, match="字幕"):
        service.prepare_replace(task, decision.result)
    assert existing.read_bytes() == b"existing-video"
    assert incoming.read_bytes() == b"new-video"


def test_keep_both_uses_explicit_available_filename_and_only_adds(tmp_path):
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    library.mkdir()
    temp.mkdir()
    existing = library / "Movie.2026.1080p.mkv"
    incoming = temp / "incoming.mkv"
    _write(existing, b"existing")
    _write(incoming, b"incoming")

    result = move_to_import(
        str(incoming),
        [],
        str(library),
        {"media_type": "movie"},
        {"movie": "{title_cn}.{ext}"},
        [str(tmp_path)],
        final_filename="Movie.2026.1080p_保留1.mkv",
    )

    assert existing.read_bytes() == b"existing"
    assert (library / "Movie.2026.1080p_保留1.mkv").read_bytes() == b"incoming"
    assert result["video"].endswith("_保留1.mkv")


def test_confirmed_replace_recycles_existing_then_publishes_new_file(tmp_path):
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    recycle = tmp_path / "recycle"
    library.mkdir()
    temp.mkdir()
    recycle.mkdir()
    existing = library / "Movie.2026.1080p.mkv"
    incoming = temp / "incoming.mkv"
    _write(existing, b"existing-library-bytes")
    _write(incoming, b"new-library-bytes")
    snapshot = {
        "existing_path": str(existing),
        "existing_fingerprint": hash_file(existing),
    }

    result = move_to_import(
        str(incoming),
        [],
        str(library),
        {"media_type": "movie"},
        {"movie": "ignored.mkv"},
        [str(tmp_path)],
        overwrite=True,
        final_filename=existing.name,
        recycle_dir=str(recycle),
        task_id="conflict-task",
        expected_conflict=snapshot,
    )

    assert result["replaced"] is True
    assert existing.read_bytes() == b"new-library-bytes"
    assert incoming.read_bytes() == b"new-library-bytes"
    recycled_files = [
        path for path in recycle.rglob("*.mkv") if path.is_file()
    ]
    assert len(recycled_files) == 1
    assert recycled_files[0].read_bytes() == b"existing-library-bytes"
    assert os.path.exists(str(recycled_files[0]) + ".meta")


def test_direct_source_replace_preserves_incoming_until_source_policy_runs(tmp_path):
    library = tmp_path / "library"
    source = tmp_path / "source"
    recycle = tmp_path / "recycle"
    library.mkdir()
    source.mkdir()
    recycle.mkdir()
    existing = library / "Movie.2026.1080p.mkv"
    incoming = source / "incoming.mkv"
    _write(existing, b"existing-library-bytes")
    _write(incoming, b"new-library-bytes")
    snapshot = {
        "existing_path": str(existing),
        "existing_fingerprint": hash_file(existing),
    }

    result = move_to_import(
        str(incoming),
        [],
        str(library),
        {"media_type": "movie"},
        {"movie": "ignored.mkv"},
        [str(source), str(library)],
        overwrite=True,
        final_filename=existing.name,
        recycle_dir=str(recycle),
        task_id="direct-source-conflict-task",
        expected_conflict=snapshot,
        import_roots=[str(library)],
    )

    assert result["replaced"] is True
    assert result["source_retained"] is True
    assert existing.read_bytes() == b"new-library-bytes"
    assert incoming.read_bytes() == b"new-library-bytes"
    recycled_files = [path for path in recycle.rglob("*.mkv") if path.is_file()]
    assert len(recycled_files) == 1
    assert recycled_files[0].read_bytes() == b"existing-library-bytes"


def test_stale_replace_snapshot_fails_closed_without_changing_either_file(tmp_path):
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    recycle = tmp_path / "recycle"
    library.mkdir()
    temp.mkdir()
    recycle.mkdir()
    existing = library / "Movie.mkv"
    incoming = temp / "incoming.mkv"
    _write(existing, b"existing")
    _write(incoming, b"incoming")

    with pytest.raises(PipelineReviewRequired, match="已发生变化"):
        move_to_import(
            str(incoming),
            [],
            str(library),
            {"media_type": "movie"},
            {"movie": "ignored.mkv"},
            [str(tmp_path)],
            overwrite=True,
            final_filename=existing.name,
            recycle_dir=str(recycle),
            task_id="conflict-task",
            expected_conflict={
                "existing_path": str(existing),
                "existing_fingerprint": "stale-fingerprint",
            },
        )

    assert existing.read_bytes() == b"existing"
    assert incoming.read_bytes() == b"incoming"
    assert list(recycle.iterdir()) == []


# Requirement: REQ-20260831-004019
def test_same_size_same_mtime_content_change_invalidates_replace_snapshot(tmp_path):
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    recycle = tmp_path / "recycle"
    library.mkdir()
    temp.mkdir()
    recycle.mkdir()
    existing = library / "Movie.mkv"
    incoming = temp / "incoming.mkv"
    existing.write_bytes(b"version-one")
    incoming.write_bytes(b"version-new")
    snapshot = {
        "existing_path": str(existing),
        "existing_fingerprint": hash_file(existing),
    }
    original_stat = existing.stat()
    existing.write_bytes(b"version-two")
    os.utime(existing, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    with pytest.raises(PipelineReviewRequired, match="已发生变化"):
        move_to_import(
            str(incoming),
            [],
            str(library),
            {"media_type": "movie"},
            {"movie": "ignored.mkv"},
            [str(temp), str(library)],
            overwrite=True,
            final_filename=existing.name,
            recycle_dir=str(recycle),
            task_id="conflict-task",
            expected_conflict=snapshot,
            import_roots=[str(library)],
        )

    assert existing.read_bytes() == b"version-two"
    assert incoming.read_bytes() == b"version-new"
    assert list(recycle.iterdir()) == []


# Requirement: REQ-20260831-004019
def test_import_rejects_using_existing_library_file_as_incoming_source(tmp_path):
    library = tmp_path / "library"
    recycle = tmp_path / "recycle"
    library.mkdir()
    recycle.mkdir()
    existing = library / "Existing.mkv"
    existing.write_bytes(b"library-must-survive")

    with pytest.raises(IOError, match="不能来自目标片库"):
        move_to_import(
            str(existing),
            [],
            str(library),
            {"media_type": "movie"},
            {"movie": "ignored.mkv"},
            [str(library)],
            final_filename="Other.mkv",
            import_roots=[str(library)],
        )

    assert existing.read_bytes() == b"library-must-survive"
    assert not (library / "Other.mkv").exists()
    assert list(recycle.iterdir()) == []


# Requirement: REQ-20260831-004019
def test_import_rejects_mislabeled_library_subtitle_before_any_file_action(tmp_path):
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    target_dir = library / "Movie"
    library.mkdir()
    temp.mkdir()
    incoming = temp / "incoming.mkv"
    protected_subtitle = library / "Existing.zh.srt"
    incoming.write_bytes(b"incoming")
    protected_subtitle.write_text("library-subtitle")

    with pytest.raises(IOError, match="视频或字幕不能来自目标片库"):
        move_to_import(
            str(incoming),
            [str(protected_subtitle)],
            str(target_dir),
            {"media_type": "movie"},
            {"movie": "ignored.mkv"},
            [str(temp), str(library)],
            final_filename="Movie.mkv",
            import_roots=[str(library)],
        )

    assert incoming.read_bytes() == b"incoming"
    assert protected_subtitle.read_text() == "library-subtitle"
    assert not target_dir.exists()


# Requirement: REQ-20260831-004019
def test_replace_revalidates_target_after_long_staging_copy(tmp_path, monkeypatch):
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    recycle = tmp_path / "recycle"
    library.mkdir()
    temp.mkdir()
    recycle.mkdir()
    existing = library / "Movie.mkv"
    incoming = temp / "incoming.mkv"
    existing.write_bytes(b"CONFIRMED-VERSION")
    incoming.write_bytes(b"INCOMING")
    expected = hash_file(existing)
    real_verified_copy = file_operations.verified_copy

    def mutate_target_after_staging(*args, **kwargs):
        result = real_verified_copy(*args, **kwargs)
        if result[0]:
            existing.write_bytes(b"CHANGED-DURING-COPY")
        return result

    monkeypatch.setattr(file_operations, "verified_copy", mutate_target_after_staging)

    with pytest.raises(PipelineReviewRequired, match="准备新文件期间发生变化"):
        move_to_import(
            str(incoming),
            [],
            str(library),
            {"media_type": "movie"},
            {"movie": "ignored.mkv"},
            [str(tmp_path)],
            overwrite=True,
            final_filename=existing.name,
            recycle_dir=str(recycle),
            expected_conflict={
                "existing_path": str(existing),
                "existing_fingerprint": expected,
            },
            import_roots=[str(library)],
        )

    assert existing.read_bytes() == b"CHANGED-DURING-COPY"
    assert incoming.read_bytes() == b"INCOMING"
    assert list(recycle.rglob("*.mkv")) == []


# Requirement: REQ-20260831-004019
def test_replace_never_overwrites_target_created_during_final_publish(tmp_path, monkeypatch):
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    recycle = tmp_path / "recycle"
    library.mkdir()
    temp.mkdir()
    recycle.mkdir()
    existing = library / "Movie.mkv"
    incoming = temp / "incoming.mkv"
    existing.write_bytes(b"CONFIRMED-VERSION")
    incoming.write_bytes(b"INCOMING")
    expected = hash_file(existing)
    real_safe_move = file_operations.safe_move
    call_count = 0

    def create_target_before_publish(src, dest, allowed_base_dirs=None):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            existing.write_bytes(b"EXTERNAL-WRITER")
        return real_safe_move(src, dest, allowed_base_dirs)

    monkeypatch.setattr(file_operations, "safe_move", create_target_before_publish)

    with pytest.raises(IOError, match="未覆盖当前目标"):
        move_to_import(
            str(incoming),
            [],
            str(library),
            {"media_type": "movie"},
            {"movie": "ignored.mkv"},
            [str(tmp_path)],
            overwrite=True,
            final_filename=existing.name,
            recycle_dir=str(recycle),
            expected_conflict={
                "existing_path": str(existing),
                "existing_fingerprint": expected,
            },
            import_roots=[str(library)],
        )

    assert existing.read_bytes() == b"EXTERNAL-WRITER"
    assert incoming.read_bytes() == b"INCOMING"
    recycled_files = list(recycle.rglob("*.mkv"))
    assert len(recycled_files) == 1
    assert recycled_files[0].read_bytes() == b"CONFIRMED-VERSION"
