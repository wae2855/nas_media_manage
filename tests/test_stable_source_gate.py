from media_importer.monitor.file_watcher import FileWatcher


def _watcher(tmp_path, callback):
    watcher = FileWatcher(
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
    watcher._source_ready_for_scan = lambda: True
    watcher._processing_support_ready = lambda: True
    return watcher


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


# Requirement: REQ-20260831-004019
def test_watcher_stops_before_scan_when_mount_identity_changes(tmp_path, monkeypatch):
    paths = {}
    for name in ("source", "recycle", "library"):
        path = tmp_path / name
        path.mkdir()
        paths[name] = str(path)
    watcher = FileWatcher({
        "source_dir": paths["source"],
        "source_policy": {"recycle_dir": paths["recycle"]},
        "library_roots": [
            {"id": "main", "name": "主片库", "path": paths["library"], "enabled": True},
        ],
        "default_library_root_id": "main",
        "library_root": paths["library"],
        "storage_identities": {
            "source": {
                "realpath": paths["source"],
                "device": -1,
                "mount_source": "stale-mount",
            },
        },
        "file_watcher": {"enabled": True, "poll_interval": 60},
    })
    watcher._source_online = True
    scanned = False

    def forbidden_scan():
        nonlocal scanned
        scanned = True
        return set()

    monkeypatch.setattr(watcher, "_scan_known_files", forbidden_scan)

    watcher._check_changes()

    assert scanned is False
    assert watcher._source_online is False


# Requirement: REQ-20260902-013607
def test_idle_scan_never_checks_processing_support(tmp_path, monkeypatch):
    watcher = _watcher(tmp_path, lambda _files: None)
    watcher._known_files = set()
    watcher._source_online = True
    checks = []
    monkeypatch.setattr(
        watcher,
        "_processing_support_ready",
        lambda: checks.append("support") or True,
    )

    watcher._check_changes()

    assert checks == []


# Requirement: REQ-20260902-013607
def test_blocked_candidate_is_retried_after_support_recovers(tmp_path, monkeypatch):
    callbacks = []
    watcher = _watcher(tmp_path, callbacks.append)
    watcher._known_files = set()
    watcher._source_online = True
    movie = tmp_path / "recover.mkv"
    movie.write_bytes(b"video")
    support_results = iter([False, True])
    monkeypatch.setattr(
        watcher,
        "_processing_support_ready",
        lambda: next(support_results),
    )
    times = iter([0.0, 121.0, 242.0])
    monkeypatch.setattr(
        "media_importer.monitor.file_watcher.time.monotonic",
        lambda: next(times),
    )

    watcher._check_changes()
    watcher._check_changes()
    assert callbacks == []
    assert str(movie) not in watcher._known_files

    watcher._check_changes()

    assert callbacks == [{str(movie)}]
    assert str(movie) in watcher._known_files


# Requirement: REQ-20260902-013607
def test_recycle_maintenance_runs_at_most_once_per_day(tmp_path, monkeypatch):
    watcher = _watcher(tmp_path, lambda _files: None)
    watcher._next_recycle_maintenance = 100.0
    calls = []
    monkeypatch.setattr(
        "media_importer.monitor.file_watcher.recycle_cleanup",
        lambda *args, **kwargs: calls.append((args, kwargs)) or [],
    )
    watcher.config["source_policy"] = {
        "recycle_dir": str(tmp_path),
        "recycle_retention_days": 30,
    }

    watcher._maybe_cleanup_recycle(now=99.0)
    watcher._maybe_cleanup_recycle(now=100.0)
    watcher._maybe_cleanup_recycle(now=101.0)

    assert len(calls) == 1
