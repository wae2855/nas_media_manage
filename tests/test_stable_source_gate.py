from media_importer.monitor.file_watcher import FileWatcher


def _watcher(tmp_path, callback):
    return FileWatcher(
        {
            "source_dir": str(tmp_path),
            "video_extensions": [".mkv"],
            "subtitle_extensions": [".srt"],
            "file_watcher": {
                "enabled": True,
                "poll_interval": 60,
                "stability_window_seconds": 120,
            },
        },
        on_new_files=callback,
    )


def test_new_file_requires_two_observations_across_window(tmp_path, monkeypatch):
    callbacks = []
    watcher = _watcher(tmp_path, callbacks.append)
    watcher._known_files = set()
    watcher._source_online = True
    movie = tmp_path / "movie.mkv"
    movie.write_bytes(b"video")

    times = iter([0.0, 60.0, 121.0])
    monkeypatch.setattr("media_importer.monitor.file_watcher.time.monotonic", lambda: next(times))

    watcher._check_changes()
    watcher._check_changes()
    assert callbacks == []
    watcher._check_changes()

    assert callbacks == [{str(movie)}]


def test_growing_file_restarts_stability_window(tmp_path, monkeypatch):
    callbacks = []
    watcher = _watcher(tmp_path, callbacks.append)
    watcher._known_files = set()
    watcher._source_online = True
    movie = tmp_path / "movie.mkv"
    movie.write_bytes(b"first")

    times = iter([0.0, 100.0, 221.0])
    monkeypatch.setattr("media_importer.monitor.file_watcher.time.monotonic", lambda: next(times))
    watcher._check_changes()
    movie.write_bytes(b"still-growing")
    watcher._check_changes()
    watcher._check_changes()

    assert callbacks == [{str(movie)}]


def test_offline_scan_keeps_known_files_and_does_not_callback(tmp_path, monkeypatch):
    callbacks = []
    watcher = _watcher(tmp_path, callbacks.append)
    known = str(tmp_path / "known.mkv")
    watcher._known_files = {known}
    watcher._source_online = True
    monkeypatch.setattr(watcher, "_scan_known_files", lambda: None)

    watcher._check_changes()

    assert watcher._known_files == {known}
    assert watcher._source_online is False
    assert callbacks == []
