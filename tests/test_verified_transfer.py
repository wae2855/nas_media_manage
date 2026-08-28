from media_importer.infrastructure.filesystem.safety import safe_move, verified_copy


def test_verified_copy_publishes_identical_bytes(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    payload = b"verified-transfer" * 100_000
    source.write_bytes(payload)

    ok, _message = verified_copy(str(source), str(target), remove_source=True)

    assert ok is True
    assert target.read_bytes() == payload
    assert not source.exists()
    assert not (target_dir / "movie.bin.copying").exists()


def test_verified_copy_resumes_only_matching_prefix(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    payload = b"abc123" * 400_000
    source.write_bytes(payload)
    partial = target_dir / "movie.bin.copying"
    partial.write_bytes(payload[:1_100_000])

    ok, _message = verified_copy(str(source), str(target))

    assert ok is True
    assert target.read_bytes() == payload


def test_verified_copy_rebuilds_mismatched_partial(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    payload = b"right" * 300_000
    source.write_bytes(payload)
    (target_dir / "movie.bin.copying").write_bytes(b"wrong" * 50_000)

    ok, _message = verified_copy(str(source), str(target))

    assert ok is True
    assert target.read_bytes() == payload


def test_safe_move_does_not_recreate_missing_mount_path(tmp_path):
    source = tmp_path / "source.bin"
    source.write_bytes(b"data")
    missing_mount = tmp_path / "gone-mount"
    target = missing_mount / "movie.bin"

    ok, message = safe_move(
        str(source),
        str(target),
        allowed_base_dirs=[str(tmp_path), str(missing_mount)],
    )

    assert ok is False
    assert "拒绝自动创建" in message
    assert source.exists()
    assert not missing_mount.exists()


def test_path_boundary_does_not_accept_similar_prefix(tmp_path):
    allowed = tmp_path / "media"
    sibling = tmp_path / "media-other"
    allowed.mkdir()
    sibling.mkdir()
    source = allowed / "source.bin"
    source.write_bytes(b"data")

    ok, message = safe_move(
        str(source),
        str(sibling / "target.bin"),
        allowed_base_dirs=[str(allowed)],
    )

    assert ok is False
    assert "目标路径安全检查失败" in message
    assert source.exists()


def test_file_copier_does_not_create_missing_temp_root(tmp_path):
    from media_importer.infrastructure.filesystem.file_copier import FileCopier

    source = tmp_path / "movie.mkv"
    source.write_bytes(b"video")
    missing_temp = tmp_path / "unmounted-temp"
    copier = FileCopier(str(missing_temp), {".mkv"})

    try:
        copier.copy_to_temp(str(source), [])
    except IOError as exc:
        assert "拒绝自动创建" in str(exc)
    else:
        raise AssertionError("missing temp root must be rejected")
    assert not missing_temp.exists()


def test_source_change_during_copy_keeps_source_and_does_not_publish(tmp_path):
    source = tmp_path / "source.bin"
    target_dir = tmp_path / "target"
    target_dir.mkdir()
    target = target_dir / "movie.bin"
    source.write_bytes(b"a" * (2 * 1024 * 1024))
    changed = False

    def mutate_after_copy(copied, total):
        nonlocal changed
        if copied == total and not changed:
            with source.open("ab") as handle:
                handle.write(b"changed")
            changed = True

    ok, message = verified_copy(
        str(source),
        str(target),
        remove_source=True,
        progress_callback=mutate_after_copy,
    )

    assert ok is False
    assert "源文件发生变化" in message
    assert source.exists()
    assert not target.exists()
