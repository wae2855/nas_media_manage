#!/usr/bin/env python3
import json
import os
import tempfile
from datetime import datetime, timedelta

from media_importer.features.recycle import (
    list_recycle_dir,
    move_dir_to_recycle,
    move_to_recycle,
    move_to_recycle_with_companions,
    recycle_cleanup,
)
from media_importer.infrastructure.filesystem import (
    make_fingerprint,
    safe_delete,
    validate_path_safety,
)


def test_fingerprint_is_stable_for_same_file():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".mkv") as f:
        f.write(b"x" * 1024)
        path = f.name

    try:
        assert make_fingerprint(path) == make_fingerprint(path)
        assert len(make_fingerprint(path)) == 16
    finally:
        os.unlink(path)


def test_move_to_recycle_records_metadata_and_source_zone():
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = os.path.join(tmpdir, "source")
        recycle_dir = os.path.join(tmpdir, "recycle")
        os.makedirs(source_dir)
        os.makedirs(recycle_dir)
        src = os.path.join(source_dir, "movie.mkv")
        with open(src, "w") as f:
            f.write("video")

        ok, dest, _ = move_to_recycle(
            src,
            recycle_dir,
            reason="unit_test",
            task_id="task-1",
            source_dir=source_dir,
        )

        assert ok is True
        assert not os.path.exists(src)
        assert os.path.exists(dest)
        with open(dest + ".meta", encoding="utf-8") as f:
            meta = json.load(f)
        assert meta["reason"] == "unit_test"
        assert meta["task_id"] == "task-1"
        assert meta["source_zone"] == "source"
        assert list_recycle_dir(recycle_dir)["total"] == 1


def test_move_to_recycle_with_companions_moves_subtitle():
    with tempfile.TemporaryDirectory() as tmpdir:
        source_dir = os.path.join(tmpdir, "source")
        recycle_dir = os.path.join(tmpdir, "recycle")
        os.makedirs(source_dir)
        os.makedirs(recycle_dir)
        video = os.path.join(source_dir, "movie.mkv")
        subtitle = os.path.join(source_dir, "movie.zh.srt")
        with open(video, "w") as f:
            f.write("video")
        with open(subtitle, "w") as f:
            f.write("subtitle")

        moved = move_to_recycle_with_companions(
            video,
            [],
            [".mkv"],
            [".srt"],
            recycle_dir,
            source_dir=source_dir,
        )

        assert moved >= 2
        assert not os.path.exists(video)
        assert not os.path.exists(subtitle)


def test_safe_delete_rejects_paths_outside_allowed_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        allowed_dir = os.path.join(tmpdir, "allowed")
        blocked_dir = os.path.join(tmpdir, "blocked")
        os.makedirs(allowed_dir)
        os.makedirs(blocked_dir)
        blocked = os.path.join(blocked_dir, "movie.mkv")
        with open(blocked, "w") as f:
            f.write("video")

        ok, msg = safe_delete(blocked, allowed_base_dirs=[allowed_dir])

        assert ok is False
        assert "allowed" in msg or "Path not in allowed directories" in msg
        assert os.path.exists(blocked)


def test_safe_delete_rejects_symlink_without_touching_target(tmp_path):
    library = tmp_path / "library"
    temp = tmp_path / "temp"
    library.mkdir()
    temp.mkdir()
    video = library / "Movie.mkv"
    video.write_bytes(b"library-must-survive")
    linked = temp / "Movie.mkv"
    linked.symlink_to(video)

    ok, message = safe_delete(str(linked), allowed_base_dirs=[str(temp)])

    assert ok is False
    assert "符号链接" in message
    assert linked.is_symlink()
    assert video.read_bytes() == b"library-must-survive"


# Requirement: REQ-20260831-004019
def test_move_to_recycle_rejects_library_file_without_confirmed_replace(tmp_path):
    library = tmp_path / "library"
    recycle = tmp_path / "recycle"
    library.mkdir()
    recycle.mkdir()
    video = library / "Movie.mkv"
    video.write_bytes(b"library-must-survive")

    ok, destination, message = move_to_recycle(
        str(video),
        str(recycle),
        reason="task_delete",
        import_roots=[str(library)],
    )

    assert ok is False
    assert destination == ""
    assert "逐项确认替换" in message
    assert video.read_bytes() == b"library-must-survive"
    assert list(recycle.iterdir()) == []


# Requirement: REQ-20260831-004019
def test_move_directory_to_recycle_rejects_library_tree(tmp_path):
    library = tmp_path / "library"
    recycle = tmp_path / "recycle"
    movie = library / "Movie"
    movie.mkdir(parents=True)
    recycle.mkdir()
    video = movie / "Movie.mkv"
    video.write_bytes(b"library-must-survive")

    ok, destination, message = move_dir_to_recycle(
        str(movie),
        str(recycle),
        reason="source_unit_cleanup",
        import_roots=[str(library)],
    )

    assert ok is False
    assert destination == ""
    assert "逐项确认替换" in message
    assert video.read_bytes() == b"library-must-survive"
    assert list(recycle.iterdir()) == []


def test_validate_path_safety_rejects_traversal():
    ok, msg = validate_path_safety("../movie.mkv")

    assert ok is False
    assert "穿越" in msg


# Requirement: REQ-20260831-004019
def test_recycle_cleanup_never_deletes_when_recycle_overlaps_library(tmp_path):
    library = tmp_path / "library"
    recycle = library / "recycle"
    recycle.mkdir(parents=True)
    video = recycle / "Movie.mkv"
    video.write_bytes(b"library-must-survive")
    meta = {
        "moved_at": (datetime.now() - timedelta(days=60)).isoformat(),
        "original_path": str(tmp_path / "source" / "Movie.mkv"),
    }
    (recycle / "Movie.mkv.meta").write_text(json.dumps(meta), encoding="utf-8")

    deleted = recycle_cleanup(str(recycle), 1, protected_roots=[str(library)])

    assert deleted == []
    assert video.read_bytes() == b"library-must-survive"
    assert (recycle / "Movie.mkv.meta").exists()
