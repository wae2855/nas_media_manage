import os

import pytest

from media_importer.features.import_flow.services import file_operations
from media_importer.features.import_flow.services.file_operations import move_to_import
from media_importer.features.import_flow.utils import PipelineCancelled


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)


def _publish(tmp_path):
    temp = tmp_path / "temp"
    library = tmp_path / "library"
    temp.mkdir(exist_ok=True)
    library.mkdir(exist_ok=True)
    video = temp / "Movie.mkv"
    zh = temp / "Movie.zh.srt"
    en = temp / "Movie.en.srt"
    _write(video, b"video")
    _write(zh, b"zh")
    _write(en, b"en")
    result = move_to_import(
        str(video),
        [str(zh), str(en)],
        str(library),
        {"media_type": "movie"},
        {
            "movie": "ignored.mkv",
            "subtitle": "{video_filename}.{lang}.{ext}",
        },
        [str(temp), str(library)],
        final_filename="Movie (2020).mkv",
        task_id="bundle-task",
        import_roots=[str(library)],
    )
    return temp, library, result


def test_bundle_publishes_subtitles_before_video(tmp_path, monkeypatch):
    order = []
    original_move = file_operations.safe_move

    def recording_move(source, destination, *args, **kwargs):
        if ".bundle.tmp" in source and ".bundle.tmp" not in destination:
            order.append(os.path.basename(destination))
        return original_move(source, destination, *args, **kwargs)

    monkeypatch.setattr(file_operations, "safe_move", recording_move)
    temp, library, result = _publish(tmp_path)

    assert order[-1] == "Movie (2020).mkv"
    assert sorted(path.name for path in library.iterdir()) == [
        "Movie (2020).en.srt",
        "Movie (2020).mkv",
        "Movie (2020).zh.srt",
    ]
    assert result["bundle_committed"] is True
    assert sorted(path.name for path in temp.iterdir()) == [
        "Movie.en.srt", "Movie.mkv", "Movie.zh.srt",
    ]


def test_video_publish_failure_rolls_subtitles_back_to_temp(tmp_path, monkeypatch):
    original_move = file_operations.safe_move

    def fail_video_publish(source, destination, *args, **kwargs):
        if (
            ".bundle.tmp" in source
            and destination.endswith(".mkv")
            and os.path.dirname(destination).endswith("library")
        ):
            return False, "injected video publish failure"
        return original_move(source, destination, *args, **kwargs)

    monkeypatch.setattr(file_operations, "safe_move", fail_video_publish)
    with pytest.raises(IOError, match="video publish failure"):
        _publish(tmp_path)

    library = tmp_path / "library"
    temp = tmp_path / "temp"
    assert list(library.iterdir()) == []
    assert sorted(path.name for path in temp.iterdir()) == [
        "Movie.en.srt", "Movie.mkv", "Movie.zh.srt",
    ]


def test_existing_subtitle_blocks_before_any_bundle_member_moves(tmp_path):
    temp = tmp_path / "temp"
    library = tmp_path / "library"
    temp.mkdir()
    library.mkdir()
    video = temp / "Movie.mkv"
    subtitle = temp / "Movie.zh.srt"
    _write(video, b"video")
    _write(subtitle, b"new-subtitle")
    existing = library / "Movie (2020).zh.srt"
    _write(existing, b"existing-subtitle")

    with pytest.raises(Exception, match="同名文件"):
        move_to_import(
            str(video), [str(subtitle)], str(library), {"media_type": "movie"},
            {"movie": "ignored", "subtitle": "{video_filename}.{lang}.{ext}"},
            [str(temp), str(library)], final_filename="Movie (2020).mkv",
            task_id="bundle-conflict", import_roots=[str(library)],
        )

    assert video.read_bytes() == b"video"
    assert subtitle.read_bytes() == b"new-subtitle"
    assert existing.read_bytes() == b"existing-subtitle"
    assert not (library / "Movie (2020).mkv").exists()


def test_bundle_journal_is_persisted_before_move_and_commits_video_last(tmp_path):
    temp = tmp_path / "temp"
    library = tmp_path / "library"
    temp.mkdir()
    library.mkdir()
    video = temp / "Movie.mkv"
    subtitle = temp / "Movie.zh.srt"
    _write(video, b"video")
    _write(subtitle, b"subtitle")
    events = []

    move_to_import(
        str(video),
        [str(subtitle)],
        str(library),
        {"media_type": "movie"},
        {"movie": "ignored", "subtitle": "{video_filename}.{lang}.{ext}"},
        [str(temp), str(library)],
        final_filename="Movie (2020).mkv",
        task_id="journal-task",
        import_roots=[str(library)],
        journal_callback=lambda state, members: events.append(
            (state, [dict(member) for member in members])
        ),
    )

    assert events[0][0] == "PREPARED"
    assert all(member["state"] == "source" for member in events[0][1])
    assert all(member["fingerprint"] == "" for member in events[0][1])
    staging_events = [members for state, members in events if state == "STAGING"]
    assert all(len(member["fingerprint"]) == 64 for member in staging_events[-1])
    assert events[-1][0] == "COMMITTED"
    assert events[-1][1][0]["kind"] == "video"
    assert events[-1][1][0]["state"] == "published"


def test_direct_source_copy_cancel_removes_target_partial_and_keeps_source(tmp_path):
    source = tmp_path / "source"
    library = tmp_path / "library"
    source.mkdir()
    library.mkdir()
    video = source / "Movie.mkv"
    _write(video, b"v" * (2 * 1024 * 1024))
    events = []

    def stop_during_transfer(phase, completed, _total):
        if phase == "transfer" and completed > 0:
            raise PipelineCancelled("stop")

    with pytest.raises(PipelineCancelled):
        move_to_import(
            str(video), [], str(library), {"media_type": "movie"},
            {"movie": "ignored"}, [str(source), str(library)],
            final_filename="Movie (2020).mkv", task_id="cancel-direct",
            import_roots=[str(library)], phase_callback=stop_during_transfer,
            journal_callback=lambda state, members: events.append(
                (state, [dict(member) for member in members])
            ),
        )

    assert video.stat().st_size == 2 * 1024 * 1024
    assert list(library.iterdir()) == []
    assert events[-1][0] == "ROLLED_BACK"
