"""配置简化方案的真实文件场景验收。

所有文件均创建在 pytest 的隔离临时目录中；测试只执行可恢复的回收操作。
"""

import json
from pathlib import Path

import pytest

from media_importer.core.db.connection import init_db
from media_importer.core.db.task_repo import create_task, update_task
from media_importer.features.configuration.library_paths import resolve_library_template
from media_importer.features.configuration.startup_readiness import inspect_startup_readiness
from media_importer.features.recycle import list_recycle_dir
from media_importer.features.source_cleaning.cleaner import SourceCleaner
from media_importer.features.source_files.cleanup_service import SourceCleanupService
from media_importer.features.source_files.source_units import (
    SourceUnitCoordinator,
    register_source_unit,
)


def _write(path: Path, content: bytes = b"test-data") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def _sparse(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.seek(size - 1)
        handle.write(b"\0")
    return path


def _paths(tmp_path: Path) -> dict[str, Path]:
    paths = {name: tmp_path / name for name in ("source", "temp", "recycle", "logs", "library")}
    for path in paths.values():
        path.mkdir()
    return paths


def _config(paths: dict[str, Path], mode: str = "preserve_all") -> dict:
    return {
        "source_dir": str(paths["source"]),
        "temp_dir": str(paths["temp"]),
        "log_dir": str(paths["logs"]),
        "library_root": str(paths["library"]),
        "fallback_dir": "其他",
        "path_rules": [
            {"conditions": {"media_type": "movie"}, "template": "电影/{year}/{title_cn}"},
        ],
        "video_extensions": [".mkv", ".mp4"],
        "subtitle_extensions": [".srt", ".ass"],
        "source_policy": {
            "mode": mode,
            "recycle_dir": str(paths["recycle"]),
            "unit_settle_seconds": 0,
        },
        "metadata": {
            "providers": [{"type": "tmdb", "enabled": True, "api_key": "test-key"}],
        },
        "file_watcher": {"enabled": True, "poll_interval": 60},
    }


def test_real_directories_pass_opening_check_and_resolve_inside_library(tmp_path: Path):
    paths = _paths(tmp_path)
    config = _config(paths)

    result = inspect_startup_readiness(
        config,
        provider_probe=lambda _provider: (True, "TMDB 模拟连通成功"),
        llm_probe=lambda _llm: (_ for _ in ()).throw(AssertionError("LLM 不应执行")),
    )

    checks = {item["id"]: item for item in result["checks"]}
    assert result["state"] == "PASS"
    assert {item["role"] for item in result["storage"]["locations"]} == {
        "source", "temp", "recycle", "log", "target",
    }
    assert checks["storage"]["status"] == "PASS"
    assert checks["library"]["status"] == "PASS"
    assert checks["tmdb"]["status"] == "PASS"
    assert checks["llm"]["status"] == "SKIPPED"
    assert checks["automation"]["status"] == "PASS"
    assert not list(tmp_path.rglob(".storage_check_*"))

    target = resolve_library_template(
        str(paths["library"]), "电影/{year}/{title_cn}",
        {"year": "2024", "title_cn": "沙丘2"},
    )
    assert target == str(paths["library"] / "电影" / "2024" / "沙丘2")


def test_preserve_all_performs_no_source_write_on_real_movie_folder(tmp_path: Path):
    paths = _paths(tmp_path)
    movie = paths["source"] / "Oppenheimer.2023.2160p.REMUX"
    video = _sparse(movie / "Oppenheimer.2023.mkv", 2 * 1024 * 1024)
    subtitle = _write(movie / "Oppenheimer.2023.zh-CN.srt", b"1\n00:00:00,000 --> 00:00:01,000\nhello")
    advertisement = _write(movie / "downloaded-from-example.txt")
    before = {path.relative_to(paths["source"]) for path in paths["source"].rglob("*")}

    result = SourceCleanupService(_config(paths, "preserve_all")).cleanup_source_after_import(
        {"task_id": "real-preserve"}, str(video), [str(subtitle)],
    )

    after = {path.relative_to(paths["source"]) for path in paths["source"].rglob("*")}
    assert before == after
    assert advertisement.exists()
    assert "不做任何源目录写入" in result.message
    assert list_recycle_dir(str(paths["recycle"]))["total"] == 0


def test_preserve_media_moves_only_junk_to_recoverable_recycle(tmp_path: Path):
    paths = _paths(tmp_path)
    movie = paths["source"] / "Dune.Part.Two.2024.1080p.BluRay"
    video = _sparse(movie / "Dune.Part.Two.2024.mkv", 2 * 1024 * 1024)
    subtitle = _write(movie / "Dune.Part.Two.2024.zh-CN.srt")
    nfo = _write(movie / "Dune.Part.Two.2024.nfo")
    poster = _write(movie / "Dune.Part.Two.2024.jpg", b"fake-jpeg")
    junk = {
        _write(movie / "RARBG.txt"),
        _write(movie / "广告.url"),
        _write(movie / "promo.exe"),
        _sparse(movie / "Sample" / "Dune.Part.Two.sample.mp4", 128 * 1024),
    }
    config = _config(paths, "preserve_media")
    config["source_cleaner"] = {
        "enabled": True,
        "cleanup_mode": "media_and_related",
        "ai_enabled": False,
        "merge_strategy": "intersection",
        "junk_video_max_size_mb": 1,
        "delete_extensions": [".txt", ".url", ".log", ".bak"],
        "protect_extensions": [".nfo", ".jpg", ".png"],
        "blacklist_patterns": ["RARBG*", "*/Sample/*"],
        "cleanup_empty_dirs": False,
    }

    record = SourceCleaner(config).execute(task_paths={str(video)})

    assert {video, subtitle, nfo, poster} <= {path for path in movie.rglob("*") if path.is_file()}
    assert all(not path.exists() for path in junk)
    assert record["total_files"] == 4
    recycle = list_recycle_dir(str(paths["recycle"]), zone="[清理器-源目录]")
    assert recycle["total"] == 4
    assert {Path(item["original_path"]) for item in recycle["items"]} == junk
    assert all(item["restorable"] for item in recycle["items"])
    assert all(item["reason"].startswith("source_cleaner:") for item in recycle["items"])
    assert paths["source"].is_dir() and movie.is_dir()


def test_successful_download_folder_moves_as_one_recoverable_source_unit(tmp_path: Path):
    paths = _paths(tmp_path)
    movie = paths["source"] / "Forrest.Gump.1994.BluRay"
    video = _sparse(movie / "Forrest.Gump.1994.mkv", 2 * 1024 * 1024)
    _write(movie / "Forrest.Gump.1994.zh-CN.srt")
    _write(movie / "Forrest.Gump.1994.nfo")
    _write(movie / "poster.jpg")
    _write(movie / "tracker-ad.txt")
    conn = init_db(str(tmp_path / "app.db"))
    unit = register_source_unit(conn, str(paths["source"]), str(video))
    task = create_task(conn, str(video), video.name, source_unit_id=unit.unit_id)
    update_task(conn, task["task_id"], status="SUCCESS", stage="DONE", import_success=1)

    result = SourceUnitCoordinator(conn, _config(paths, "recycle_source_unit")).try_recycle(unit.unit_id)

    assert result.state == "RECYCLED"
    assert paths["source"].is_dir() and not movie.exists()
    recycle = list_recycle_dir(str(paths["recycle"]), zone="[源目录]")
    assert recycle["total"] == 1
    item = recycle["items"][0]
    assert item["is_dir"] is True and item["restorable"] is True
    moved = Path(item["recycle_path"])
    assert {path.relative_to(moved) for path in moved.rglob("*") if path.is_file()} == {
        Path("Forrest.Gump.1994.mkv"), Path("Forrest.Gump.1994.zh-CN.srt"),
        Path("Forrest.Gump.1994.nfo"), Path("poster.jpg"), Path("tracker-ad.txt"),
    }
    meta = json.loads(Path(str(moved) + ".dir.meta").read_text(encoding="utf-8"))
    assert meta["source_unit_id"] == unit.unit_id
    assert meta["reason"] == "source_unit_cleanup"


@pytest.mark.parametrize("unsafe_state", ["task_failed", "download_incomplete", "folder_changed"])
def test_uncertain_download_folder_is_never_moved(tmp_path: Path, unsafe_state: str):
    paths = _paths(tmp_path)
    movie = paths["source"] / f"Cloud.Movie.2024.{unsafe_state}"
    video = _sparse(movie / "Cloud.Movie.2024.mkv", 2 * 1024 * 1024)
    if unsafe_state == "download_incomplete":
        _write(movie / "Cloud.Movie.2024.mkv.aria2")
    conn = init_db(str(tmp_path / "app.db"))
    unit = register_source_unit(conn, str(paths["source"]), str(video))
    task = create_task(conn, str(video), video.name, source_unit_id=unit.unit_id)
    if unsafe_state == "task_failed":
        update_task(conn, task["task_id"], status="FAILED", stage="FAILED", import_success=0)
    else:
        update_task(conn, task["task_id"], status="SUCCESS", stage="DONE", import_success=1)
    if unsafe_state == "folder_changed":
        _write(movie / "late-arriving-cloud-file.txt")

    result = SourceUnitCoordinator(conn, _config(paths, "recycle_source_unit")).try_recycle(unit.unit_id)

    assert result.state in {"WAITING", "BLOCKED"}
    assert movie.is_dir() and video.exists()
    assert list_recycle_dir(str(paths["recycle"]))["total"] == 0
