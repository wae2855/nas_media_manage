import errno
import os
from datetime import datetime

from media_importer.core.config_validator import check_path
from media_importer.core.logger import Logger
from media_importer.features.recycle import move_to_recycle
from media_importer.infrastructure.filesystem import check_write_permission, verified_copy


# Requirement: REQ-20260831-004019
def test_verified_copy_rejects_symlinked_resume_file_without_touching_library(tmp_path):
    source = tmp_path / "incoming.mkv"
    destination = tmp_path / "target" / "NewMovie.mkv"
    victim = tmp_path / "library" / "ExistingMovie.mkv"
    destination.parent.mkdir()
    victim.parent.mkdir()
    source.write_bytes(b"INCOMING")
    victim.write_bytes(b"LIBRARY-MUST-SURVIVE")
    os.symlink(victim, str(destination) + ".copying")

    ok, message = verified_copy(str(source), str(destination), remove_source=True)

    assert ok is False
    assert "断点临时文件" in message
    assert victim.read_bytes() == b"LIBRARY-MUST-SURVIVE"
    assert source.read_bytes() == b"INCOMING"
    assert not destination.exists()


# Requirement: REQ-20260831-004019
def test_verified_copy_never_replaces_destination_created_during_copy(tmp_path):
    source = tmp_path / "incoming.mkv"
    destination = tmp_path / "library" / "Movie.mkv"
    destination.parent.mkdir()
    source.write_bytes(b"N" * (2 * 1024 * 1024))
    created = False

    def create_competing_target(_copied, _total):
        nonlocal created
        if not created:
            destination.write_bytes(b"EXTERNAL-WRITER")
            created = True

    ok, message = verified_copy(
        str(source),
        str(destination),
        remove_source=True,
        progress_callback=create_competing_target,
    )

    assert ok is False
    assert "复制期间出现" in message
    assert destination.read_bytes() == b"EXTERNAL-WRITER"
    assert source.exists()


# Requirement: REQ-20260831-004019
def test_write_permission_checks_ignore_fixed_name_symlink_traps(tmp_path):
    directory = tmp_path / "target"
    victim = tmp_path / "library" / "ExistingMovie.mkv"
    directory.mkdir()
    victim.parent.mkdir()
    victim.write_bytes(b"LIBRARY-MUST-SURVIVE")
    (directory / ".write_test").symlink_to(victim)
    (directory / f".test_write_{int(datetime.now().timestamp())}").symlink_to(victim)

    assert check_write_permission(str(directory))[0] is True
    assert check_path(str(directory), require_write=True)[0] is True
    assert victim.read_bytes() == b"LIBRARY-MUST-SURVIVE"


# Requirement: REQ-20260902-172713
def test_write_permission_cleans_probe_when_fuse_close_reports_bad_descriptor(
    tmp_path, monkeypatch,
):
    directory = tmp_path / "remote-source"
    directory.mkdir()
    real_close = os.close
    raised = False

    def fuse_close(descriptor):
        nonlocal raised
        if not raised:
            raised = True
            real_close(descriptor)
            raise OSError(errno.EBADF, "simulated rclone close result")
        real_close(descriptor)

    monkeypatch.setattr(
        "media_importer.infrastructure.filesystem.safety.os.close",
        fuse_close,
    )

    ok, message = check_write_permission(str(directory))

    assert ok is True, message
    assert list(directory.glob(".write_test_*")) == []


# Requirement: REQ-20260902-172713
def test_write_permission_never_removes_unknown_legacy_probe(tmp_path):
    directory = tmp_path / "source"
    directory.mkdir()
    legacy = directory / ".write_test_ejk3wv_d"
    legacy.write_bytes(b"test")

    assert check_write_permission(str(directory))[0] is True
    assert legacy.read_bytes() == b"test"


# Requirement: REQ-20260831-004019
def test_logger_rejects_symlinked_log_file_without_touching_library(tmp_path):
    log_dir = tmp_path / "logs"
    victim = tmp_path / "library" / "ExistingMovie.mkv"
    log_dir.mkdir()
    victim.parent.mkdir()
    victim.write_bytes(b"LIBRARY-MUST-SURVIVE")
    (log_dir / "media_importer.log").symlink_to(victim)

    logger = Logger(log_dir=str(log_dir))
    logger.info("must-not-enter-victim")

    assert logger._file_handler_enabled is False
    assert victim.read_bytes() == b"LIBRARY-MUST-SURVIVE"


# Requirement: REQ-20260831-004019
def test_recycle_sidecar_symlink_never_receives_metadata(tmp_path):
    source_dir = tmp_path / "source"
    recycle_dir = tmp_path / "recycle"
    victim = tmp_path / "library" / "ExistingMovie.mkv"
    source_dir.mkdir()
    recycle_dir.mkdir()
    victim.parent.mkdir()
    source = source_dir / "Movie.mkv"
    source.write_bytes(b"SOURCE")
    victim.write_bytes(b"LIBRARY-MUST-SURVIVE")
    expected_dir = recycle_dir / datetime.now().strftime("%Y-%m-%d") / "[源目录]"
    expected_dir.mkdir(parents=True)
    (expected_dir / "Movie.mkv.meta").symlink_to(victim)

    ok, recycled_path, _message = move_to_recycle(
        str(source),
        str(recycle_dir),
        source_dir=str(source_dir),
    )

    assert ok is True
    assert recycled_path.endswith("Movie_1.mkv")
    assert victim.read_bytes() == b"LIBRARY-MUST-SURVIVE"
    assert (expected_dir / "Movie.mkv.meta").is_symlink()
