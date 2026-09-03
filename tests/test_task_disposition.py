from types import SimpleNamespace

from media_importer.core.db import (
    create_subtitles,
    create_task,
    get_task,
    init_db,
    update_task,
)
from media_importer.features.tasks import (
    complete_requested_stop,
    request_task_disposition,
)


class Manager(SimpleNamespace):
    def get_task(self, task_id):
        return get_task(self.conn, task_id)


def _setup(tmp_path, *, status="PENDING", stage="QUEUED"):
    source = tmp_path / "source"
    recycle = tmp_path / "recycle"
    library = tmp_path / "library"
    data = tmp_path / "data"
    for path in (source, recycle, library, data):
        path.mkdir()
    video = source / "Movie.mkv"
    subtitle = source / "Movie.zh.srt"
    other = source / "download-note.txt"
    video.write_bytes(b"video")
    subtitle.write_bytes(b"subtitle")
    other.write_bytes(b"must-stay")
    conn = init_db(str(tmp_path / "tasks.db"))
    task = create_task(conn, str(video), video.name, task_id="movie-task")
    create_subtitles(conn, task["task_id"], [str(subtitle)])
    update_task(conn, task["task_id"], status=status, stage=stage)
    config = {
        "source_dir": str(source),
        "_data_dir": str(data),
        "source_policy": {
            "mode": "recycle_source_unit",
            "disposal_mode": "local_recycle",
            "recycle_dir": str(recycle),
        },
        "library_roots": [{
            "id": "movies",
            "name": "电影",
            "path": str(library),
            "enabled": True,
        }],
    }
    return Manager(conn=conn), config, video, subtitle, other, library, recycle


def test_queued_task_can_end_while_keeping_new_resource(tmp_path):
    manager, config, video, subtitle, other, library, _recycle = _setup(tmp_path)

    result = request_task_disposition(
        manager, config, "movie-task", source_disposition="keep"
    )

    assert result.code == 200
    task = manager.get_task("movie-task")
    assert task["status"] == "CANCELLED"
    assert task["outcome_code"] == "USER_CANCELLED"
    assert task["source_disposition"] == "kept"
    assert video.read_bytes() == b"video"
    assert subtitle.read_bytes() == b"subtitle"
    assert other.read_bytes() == b"must-stay"
    assert list(library.iterdir()) == []
    manager.conn.close()


def test_review_task_recycles_only_registered_video_package(tmp_path):
    manager, config, video, subtitle, other, library, recycle = _setup(
        tmp_path, stage="AWAIT_REVIEW"
    )

    result = request_task_disposition(
        manager, config, "movie-task", source_disposition="local_recycle"
    )

    assert result.code == 200
    task = manager.get_task("movie-task")
    assert task["status"] == "SKIPPED"
    assert task["source_disposition"] == "recycled"
    assert not video.exists()
    assert not subtitle.exists()
    assert other.read_bytes() == b"must-stay"
    assert list(library.iterdir()) == []
    recycled_files = [path.name for path in recycle.rglob("*") if path.is_file()]
    assert any(name.startswith("Movie.mkv") for name in recycled_files)
    assert any(name.startswith("Movie.zh.srt") for name in recycled_files)
    manager.conn.close()


def test_running_task_stops_cooperatively_at_safe_checkpoint(tmp_path):
    manager, config, video, subtitle, other, library, _recycle = _setup(
        tmp_path, stage="RUNNING"
    )

    requested = request_task_disposition(
        manager, config, "movie-task", source_disposition="keep"
    )
    completed = complete_requested_stop(manager, config, "movie-task")

    assert requested.code == 202
    assert completed.code == 200
    task = manager.get_task("movie-task")
    assert task["status"] == "CANCELLED"
    assert task["outcome_code"] == "USER_STOPPED"
    assert task["cancel_requested"] == 0
    assert video.exists() and subtitle.exists() and other.exists()
    assert list(library.iterdir()) == []
    manager.conn.close()


def test_committed_bundle_cannot_be_stopped_or_touched(tmp_path):
    manager, config, video, subtitle, other, library, _recycle = _setup(
        tmp_path, stage="RUNNING"
    )
    imported = library / "Movie.mkv"
    imported.write_bytes(b"library")
    update_task(manager.conn, "movie-task", bundle_committed=1, import_video_path=str(imported))

    result = request_task_disposition(
        manager, config, "movie-task", source_disposition="local_recycle"
    )

    assert result.code == 409
    assert imported.read_bytes() == b"library"
    assert video.exists() and subtitle.exists() and other.exists()
    manager.conn.close()


def test_permanent_delete_requires_explicit_global_mode(tmp_path):
    manager, config, video, subtitle, other, library, _recycle = _setup(
        tmp_path, status="FAILED", stage="DONE"
    )

    blocked = request_task_disposition(
        manager, config, "movie-task", source_disposition="permanent_delete"
    )

    assert blocked.code == 409
    assert video.exists() and subtitle.exists() and other.exists()
    assert list(library.iterdir()) == []
    manager.conn.close()


def test_success_task_only_allows_record_deletion_not_source_disposal(tmp_path):
    manager, config, video, subtitle, other, library, _recycle = _setup(
        tmp_path, status="SUCCESS", stage="DONE"
    )
    imported = library / "Movie.mkv"
    imported.write_bytes(b"library")
    update_task(manager.conn, "movie-task", import_video_path=str(imported), file_location="import")

    result = request_task_disposition(
        manager, config, "movie-task", source_disposition="local_recycle"
    )

    assert result.code == 400
    assert imported.read_bytes() == b"library"
    assert video.exists() and subtitle.exists() and other.exists()
    manager.conn.close()
