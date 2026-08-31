import os
from datetime import datetime, timedelta

from media_importer.core.task_manager import TaskManager
from media_importer.features.scraping.thumbnail_cache import (
    prune_thumbnail_cache,
    recent_movie_items,
)
from media_importer.features.tasks import get_dashboard_summary_for_api
from media_importer.infrastructure.db import update_task


def _task(manager, name, **fields):
    task = manager.create_task(f"/source/{name}", name)
    update_task(manager.conn, task["task_id"], **fields)
    return manager.get_task(task["task_id"])


def test_dashboard_summary_uses_business_states_and_local_today(tmp_path):
    manager = TaskManager(str(tmp_path / "data"))
    thumb_dir = tmp_path / "resources" / "thumbnail"
    thumb_dir.mkdir(parents=True)
    now = datetime.now()

    movie_path = thumb_dir / "movie.jpg"
    movie_path.write_bytes(b"poster")
    _task(
        manager,
        "movie.mkv",
        status="SUCCESS",
        stage="DONE",
        import_success=1,
        completed_at=now.isoformat(),
        thumbnail_path=str(movie_path),
        provider_type="tmdb",
        provider_id="10",
        scrape_title_cn="今天的电影",
    )
    _task(
        manager,
        "old.mkv",
        status="SUCCESS",
        stage="DONE",
        import_success=1,
        completed_at=(now - timedelta(days=2)).isoformat(),
    )
    _task(manager, "run-a.mkv", status="PENDING", stage="RUNNING", percentage=20)
    _task(manager, "run-b.mkv", status="PENDING", stage="RUNNING", percentage=60)
    _task(manager, "review.mkv", status="PENDING", stage="AWAIT_REVIEW")
    _task(manager, "failed.mkv", status="FAILED", stage="DONE", error_message="网络不可用")

    result = get_dashboard_summary_for_api(
        manager,
        paused=False,
        thumbnail_dir=str(thumb_dir),
    )

    assert result.code == 200
    assert result.data["counts"] == {
        "queued": 0,
        "running": 2,
        "await_review": 1,
        "failed": 1,
    }
    assert result.data["running_progress"] == 40
    assert result.data["today_success"] == 1
    assert len(result.data["activities"]) == 5
    assert {item["title"] for item in result.data["activities"]} >= {
        "正在整理",
        "等待确认",
        "处理失败",
    }
    assert result.data["recent_movies"][0]["title"] == "今天的电影"
    assert result.data["recent_movies"][0]["url"].endswith("movie.jpg")
    assert "_path" not in result.data["recent_movies"][0]


def test_recent_movies_deduplicate_and_reject_outside_thumbnail_root(tmp_path):
    thumb_dir = tmp_path / "thumbnail"
    thumb_dir.mkdir()
    inside = thumb_dir / "inside.jpg"
    inside.write_bytes(b"ok")
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"no")
    rows = [
        {
            "task_id": "new",
            "provider_type": "tmdb",
            "provider_id": "42",
            "thumbnail_path": str(inside),
            "scrape_title_cn": "新版",
        },
        {
            "task_id": "duplicate",
            "provider_type": "tmdb",
            "provider_id": "42",
            "thumbnail_path": str(inside),
            "scrape_title_cn": "重复",
        },
        {
            "task_id": "outside",
            "provider_type": "tmdb",
            "provider_id": "99",
            "thumbnail_path": str(outside),
        },
    ]

    items = recent_movie_items(rows, str(thumb_dir))

    assert [item["task_id"] for item in items] == ["new"]


def test_thumbnail_cache_prunes_by_count_and_bytes_without_touching_protected(tmp_path):
    thumb_dir = tmp_path / "thumbnail"
    thumb_dir.mkdir()
    files = []
    for index in range(5):
        path = thumb_dir / f"{index}.jpg"
        path.write_bytes(bytes([index]) * 10)
        os.utime(path, (index + 1, index + 1))
        files.append(path)
    protected = files[0]

    result = prune_thumbnail_cache(
        str(thumb_dir),
        {str(protected)},
        max_files=2,
        max_bytes=25,
    )

    assert protected.exists()
    assert result["files"] <= 2
    assert result["bytes"] <= 25
    assert result["removed"] == 3


def test_thumbnail_cache_skips_symlink_and_non_image(tmp_path):
    thumb_dir = tmp_path / "thumbnail"
    thumb_dir.mkdir()
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"outside")
    symlink = thumb_dir / "linked.jpg"
    symlink.symlink_to(outside)
    note = thumb_dir / "note.txt"
    note.write_text("keep", encoding="utf-8")

    result = prune_thumbnail_cache(str(thumb_dir), set(), max_files=0, max_bytes=0)

    assert result["removed"] == 0
    assert symlink.is_symlink()
    assert note.exists()


# Requirement: REQ-20260831-004019
def test_thumbnail_cache_rejects_symlinked_root_into_library(tmp_path):
    library = tmp_path / "library"
    posters = library / "posters"
    resource = tmp_path / "resource"
    library.mkdir()
    posters.mkdir()
    resource.mkdir()
    victim = posters / "Movie.jpg"
    victim.write_bytes(b"LIBRARY-MUST-SURVIVE")
    (resource / "thumbnail").symlink_to(posters, target_is_directory=True)

    result = prune_thumbnail_cache(
        str(resource / "thumbnail"),
        set(),
        max_files=0,
        max_bytes=0,
        protected_roots=[str(library)],
    )

    assert result["removed"] == 0
    assert victim.read_bytes() == b"LIBRARY-MUST-SURVIVE"
