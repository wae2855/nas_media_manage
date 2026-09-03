from media_importer.core.db import (
    create_subtitles,
    get_subtitles_by_task,
    init_db,
)
from media_importer.features.import_flow.steps.file import FileStepsMixin


def test_rename_plans_subtitles_for_automatic_flow(tmp_path):
    subtitle_zh = tmp_path / "Movie.zh.srt"
    subtitle_unknown = tmp_path / "Movie.commentary.srt"
    subtitle_zh.write_bytes(b"zh")
    subtitle_unknown.write_bytes(b"unknown")
    conn = init_db(str(tmp_path / "tasks.db"))
    create_subtitles(
        conn,
        "bundle-plan",
        [str(subtitle_zh), str(subtitle_unknown)],
    )

    class TaskManager:
        def __init__(self):
            self.conn = conn

    class Harness(FileStepsMixin):
        config = {
            "filename_templates": {
                "movie": "{title_cn} ({year})",
                "subtitle": "{video_filename}.{lang}.{ext}",
            }
        }
        task_manager = TaskManager()

        def _update_progress(self, *_args, **_kwargs):
            pass

        def _log(self, *_args, **_kwargs):
            pass

    task = {
        "task_id": "bundle-plan",
        "source_path": str(tmp_path / "source.mkv"),
        "source_filename": "source.mkv",
        "scrape_result": {
            "title_cn": "小姐",
            "year": 2016,
            "media_type": "movie",
        },
    }

    Harness()._step_rename(task)

    rows = get_subtitles_by_task(conn, "bundle-plan")
    assert task["final_filename"] == "小姐 (2016).mkv"
    assert [row["planned_filename"] for row in rows] == [
        "小姐 (2016).zh.srt",
        "小姐 (2016).und.srt",
    ]
    assert [row["lang"] for row in rows] == ["zh", "und"]
    assert len({row["member_id"] for row in rows}) == 2
    assert all(row["source_fingerprint"] for row in rows)
    conn.close()
